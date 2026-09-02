"""nxopen/generate_cam_from_selection.py

Attempt to create CAM operations in NX (more aggressive builders usage).
This version tries to populate common builder properties (ToolName, Depth,
StepDown, StepOver, SpindleSpeed, FeedRate) when available, then commit the
builders to create actual NX CAM operations. All calls are guarded with
try/except so the journal is safe to run in installs where parts of the API
are missing.

Run inside NX: File -> Execute -> Journal -> select this file -> Run

Outputs written to repo/output/:
 - nx_cam_plan.json   (detailed planned operations)
 - nx_cam_summary.json
 - nx_cam_journal_run.log
 - generated_gcode.nc (if post runs)

Note: Builder attribute names vary across NX versions. This script uses
getattr/setattr and checks for common property names. If a property isn't
available the script logs and continues. After running, open the part in NX
CAM and inspect the created operations carefully, then run Simulation and
Post with your Fanuc Oi post.
"""

import os
import json
import traceback
from pathlib import Path

REPO_ROOT = Path(os.path.join(os.path.dirname(__file__), '..')).resolve()
SELECTED_PATH = REPO_ROOT / 'output' / 'selected_tools.json'
CANDIDATES_PATH = REPO_ROOT / 'input' / 'candidates.json'
TOOLLIB_PATH = REPO_ROOT / 'output' / 'toollib_standard.json'
LOG_PATH = REPO_ROOT / 'output' / 'nx_cam_journal_run.log'
PLAN_PATH = REPO_ROOT / 'output' / 'nx_cam_plan.json'
SUMMARY_PATH = REPO_ROOT / 'output' / 'nx_cam_summary.json'
GCODE_OUT = REPO_ROOT / 'output' / 'generated_gcode.nc'


def write_log(msg: str):
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        write_log(f'Failed to load {path}: {e}')
        return None


def safe_get_tool_record(toollib, tool_id):
    if not toollib:
        return None
    for t in toollib.get('tools', []) if isinstance(toollib, dict) else toollib:
        if t.get('id') == tool_id or t.get('tool_id') == tool_id or t.get('library_reference') == tool_id:
            return t
    return None


def build_plan(selected, candidates, toollib, defaults):
    plan = []
    for feat in candidates:
        fid = feat.get('id')
        entry = next((s for s in selected if s.get('feature_id') == fid), None)
        chosen_tool_id = entry.get('selected') if entry else None
        tool_rec = safe_get_tool_record(toollib, chosen_tool_id)
        ftype = feat.get('feature_type')
        geom = feat.get('geom', {})
        if ftype == 'hole':
            diameter = geom.get('diameter_mm')
            depth = geom.get('depth_mm')
            op = {
                'feature_id': fid,
                'feature_type': ftype,
                'operation': 'drilling',
                'tool_id': chosen_tool_id,
                'tool_candidates': entry.get('candidates') if entry else [],
                'stepdown_mm': None,
                'stepover_mm': None,
                'rpm': defaults['rpm_for_material'],
                'feed_mm_min': defaults['feed_for_material'],
                'safety_status': 'requires_nx_cam_simulation',
                'notes': []
            }
            if tool_rec:
                nc = tool_rec.get('numeric_candidates', {})
                lengths = [v for v in nc.values() if v > 1]
                if lengths:
                    ol = max(lengths)
                    if ol < (depth + defaults['safety_mm']):
                        op['notes'].append('tool length may be insufficient: check flute/overall length')
            plan.append(op)
        elif ftype in ('pocket', 'slot', 'profile'):
            depth = geom.get('depth_mm', 0.0)
            width = geom.get('width_mm') or geom.get('slot_width_mm') or geom.get('length_mm')
            stepdown = min((tool_rec.get('diameter_mm') if tool_rec and tool_rec.get('diameter_mm') else (width or 5))/2, defaults['max_stepdown_mm']) if 'tool_rec' in locals() else defaults['max_stepdown_mm']
            op = {
                'feature_id': fid,
                'feature_type': ftype,
                'operation': 'milling',
                'tool_id': chosen_tool_id,
                'tool_candidates': entry.get('candidates') if entry else [],
                'stepdown_mm': round(stepdown,3) if stepdown else defaults['max_stepdown_mm'],
                'stepover_mm': round((defaults['stepover_percent'] * (tool_rec.get('diameter_mm') if tool_rec and tool_rec.get('diameter_mm') else (width or 5))),3) if 'tool_rec' in locals() else defaults['stepover_percent'] * (width or 5),
                'rpm': defaults['rpm_for_material'],
                'feed_mm_min': defaults['feed_for_material'],
                'safety_status': 'requires_nx_cam_simulation',
                'notes': []
            }
            if tool_rec and tool_rec.get('diameter_mm') and width:
                if tool_rec.get('diameter_mm') > width:
                    op['notes'].append('tool diameter > feature width: will not fit; choose smaller tool or adjust')
            plan.append(op)
        else:
            plan.append({'feature_id': fid, 'operation': 'unknown', 'notes': ['Unknown feature type - manual creation required']})
    return plan


def set_builder_attr(builder, attr, value):
    """Set attribute on builder if present. Return True if set."""
    try:
        if hasattr(builder, attr):
            setattr(builder, attr, value)
            return True
        # Some builders use property methods like SetX / SetY
        set_method = 'Set' + attr
        if hasattr(builder, set_method):
            getattr(builder, set_method)(value)
            return True
    except Exception as e:
        write_log(f'Failed to set builder.{attr} = {value}: {e}')
    return False


def attempt_create_ops_in_nx(plan):
    try:
        import NXOpen
        import NXOpen.CAM
    except Exception as e:
        write_log('NXOpen.CAM not importable: ' + str(e))
        return {'created': False, 'reason': 'NXOpen.CAM import failed'}

    try:
        session = NXOpen.Session.GetSession()
        work_part = session.Parts.Work
        write_log('NX session detected. Work part: ' + (work_part.Name if work_part else 'None'))

        try:
            cam_session = NXOpen.CAM.CAMSession.GetSession(work_part)
        except Exception:
            try:
                cam_session = NXOpen.CAM.CAMSession.GetSession()
            except Exception as e:
                write_log('CAMSession could not be acquired: ' + str(e))
                cam_session = None
        if cam_session is None:
            return {'created': False, 'reason': 'CAMSession unavailable'}

        created_ops = []
        for op in plan:
            try:
                if op['operation'] == 'drilling':
                    write_log(f"Creating drill operation for {op['feature_id']} with tool {op['tool_id']}")
                    try:
                        builder = None
                        # try common builder names
                        for name in ('DrillBuilder','StandardDrillBuilder','DrillCycleBuilder'):
                            if hasattr(NXOpen.CAM, name):
                                BuilderClass = getattr(NXOpen.CAM, name)
                                try:
                                    builder = BuilderClass(work_part)
                                    write_log(f'Instantiated {name}')
                                    break
                                except Exception:
                                    builder = None
                        if builder is None:
                            write_log('No Drill builder available in this NX API; marking planned')
                            created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'planned'})
                        else:
                            # Set common properties if present
                            set_builder_attr(builder, 'ToolName', op['tool_id'])
                            set_builder_attr(builder, 'Depth', float(op.get('depth_mm') or 0))
                            set_builder_attr(builder, 'SpindleSpeed', int(op.get('rpm')))
                            set_builder_attr(builder, 'FeedRate', float(op.get('feed_mm_min') or 0))
                            set_builder_attr(builder, 'PeckDepth', float(op.get('stepdown_mm') or 0))
                            # commit if method exists
                            if hasattr(builder, 'Commit'):
                                try:
                                    builder.Commit()
                                    write_log(f'Drill operation committed for {op["feature_id"]}')
                                    created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'created'})
                                except Exception as e:
                                    write_log('Failed to commit drill builder: ' + str(e))
                                    created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'planned'})
                            else:
                                write_log('Builder has no Commit method; operation left as planned')
                                created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'planned'})
                    except Exception:
                        write_log('Exception during drill creation:')
                        write_log(traceback.format_exc())
                        created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'error'})

                elif op['operation'] == 'milling':
                    write_log(f"Creating mill operation for {op['feature_id']} with tool {op['tool_id']}")
                    try:
                        builder = None
                        for name in ('MillBuilder','RoughMillBuilder','ContourBuilder','PlanarMachiningBuilder'):
                            if hasattr(NXOpen.CAM, name):
                                BuilderClass = getattr(NXOpen.CAM, name)
                                try:
                                    builder = BuilderClass(work_part)
                                    write_log(f'Instantiated {name}')
                                    break
                                except Exception:
                                    builder = None
                        if builder is None:
                            write_log('No Mill builder available in this NX API; marking planned')
                            created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'planned'})
                        else:
                            set_builder_attr(builder, 'ToolName', op['tool_id'])
                            set_builder_attr(builder, 'StepDown', float(op.get('stepdown_mm') or 0))
                            set_builder_attr(builder, 'StepOver', float(op.get('stepover_mm') or 0))
                            set_builder_attr(builder, 'SpindleSpeed', int(op.get('rpm')))
                            set_builder_attr(builder, 'FeedRate', float(op.get('feed_mm_min') or 0))
                            if hasattr(builder, 'Commit'):
                                try:
                                    builder.Commit()
                                    write_log(f'Mill operation committed for {op["feature_id"]}')
                                    created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'created'})
                                except Exception as e:
                                    write_log('Failed to commit mill builder: ' + str(e))
                                    created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'planned'})
                            else:
                                write_log('Builder has no Commit method; operation left as planned')
                                created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'planned'})
                    except Exception:
                        write_log('Exception during mill creation:')
                        write_log(traceback.format_exc())
                        created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'error'})
                else:
                    write_log('Unknown operation type: ' + str(op.get('operation')))
                    created_ops.append({'feature_id': op.get('feature_id'), 'op':'unknown', 'status':'skipped'})
            except Exception:
                write_log('Unexpected exception in op loop:')
                write_log(traceback.format_exc())
                created_ops.append({'feature_id': op.get('feature_id'), 'op':'unknown', 'status':'error'})
        return {'created': True, 'created_ops': created_ops}
    except Exception as e:
        write_log('Unexpected exception in attempt_create_ops_in_nx: ' + str(e))
        write_log(traceback.format_exc())
        return {'created': False, 'reason': str(e)}


def run():
    write_log('=== NX CAM generation journal (aggressive) started ===')
    selected = load_json(SELECTED_PATH) or []
    candidates = load_json(CANDIDATES_PATH) or []
    toollib = load_json(TOOLLIB_PATH) or {}

    defaults = {
        'safety_mm': 5.0,
        'max_stepdown_mm': 3.0,
        'stepover_percent': 0.5,
        'rpm_for_material': 2000,
        'feed_for_material': 300
    }

    plan = build_plan(selected, candidates, toollib, defaults)
    try:
        PLAN_PATH.write_text(json.dumps({'plan': plan}, ensure_ascii=False, indent=2), encoding='utf-8')
        write_log('Wrote CAM plan to ' + str(PLAN_PATH))
    except Exception as e:
        write_log('Failed to write CAM plan: ' + str(e))

    try:
        res = attempt_create_ops_in_nx(plan)
        write_log('attempt_create_ops_in_nx result: ' + str(res))
    except Exception:
        write_log('Exception calling attempt_create_ops_in_nx:')
        write_log(traceback.format_exc())

    summary = {
        'status': 'plan_attempted',
        'message': 'CAM plan created. Some operations may have been created in NX. Inspect NX CAM and simulate before post-processing.',
        'plan_path': str(PLAN_PATH),
        'selected_summary': selected
    }
    try:
        SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        write_log('Wrote summary to ' + str(SUMMARY_PATH))
    except Exception as e:
        write_log('Failed to write summary: ' + str(e))

    write_log('=== NX CAM generation journal (aggressive) finished ===')


if __name__ == '__main__':
    run()
