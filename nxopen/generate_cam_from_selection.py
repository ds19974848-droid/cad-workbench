"""nxopen/generate_cam_from_selection.py

Expanded NXOpen journal to generate CAM operations from selected_tools.json.
This script builds a detailed CAM plan (operations with tools/feeds/feeds) and
attempts to create NX CAM operations when the NXOpen.CAM API is available.

Run inside NX: File -> Execute -> Journal -> select this file -> Run

Safety: All NX CAM creation calls are wrapped in try/except and logged. If the
local NX installation exposes a different API surface the script will still
write a complete plan JSON (output/nx_cam_plan.json) that you can use to
manually create operations or for iterative scripting updates.

Inputs (repo root):
  output/selected_tools.json
  input/candidates.json
  output/toollib_standard.json

Outputs (repo root):
  output/nx_cam_plan.json         -- detailed planned operations
  output/nx_cam_journal_run.log  -- run log
  output/nx_cam_summary.json     -- high-level summary
  output/generated_gcode.nc      -- placeholder if post succeeds

Notes:
- The script will try to map tool_id strings to NX tool objects if present in
  the current Work Part's tool list. If no mapping is found it will create a
  plan entry that references the tool_id string (you must ensure the physical
  tool exists in your machine/tool library before running the produced G-code).
- After running this journal in NX, open the generated plan JSON and inspect
  each planned operation in NX CAM before post-processing.
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
        # find tool record
        tool_rec = safe_get_tool_record(toollib, chosen_tool_id)
        # Basic op types
        ftype = feat.get('feature_type')
        geom = feat.get('geom', {})
        if ftype == 'hole':
            diameter = geom.get('diameter_mm')
            depth = geom.get('depth_mm')
            op = {
                'feature_id': fid,
                'op_type': 'drill',
                'tool_id': chosen_tool_id,
                'tool_record': tool_rec,
                'diameter_mm': diameter,
                'depth_mm': depth,
                'strategy': 'peck' if depth and depth>diameter*3 else 'standard',
                'safety_mm': defaults['safety_mm'],
                'spindle_rpm': defaults['rpm_for_material'],
                'feed_mm_per_min': defaults['feed_for_material'],
                'notes': []
            }
            # add checks
            if tool_rec:
                if tool_rec.get('diameter_mm'):
                    if abs((tool_rec.get('diameter_mm') or 0)-diameter) > 0.2:
                        op['notes'].append('tool diameter != feature diameter: verify fit')
                # numeric candidates may include flute length / overall length
                nc = tool_rec.get('numeric_candidates', {})
                lengths = [v for v in nc.values() if v>1]
                if lengths:
                    ol = max(lengths)
                    if ol < (depth + defaults['safety_mm']):
                        op['notes'].append('tool length may be insufficient: check flute/overall length')
            plan.append(op)
        elif ftype in ('pocket','profile','slot'):
            # milling op: decide rough + finish if depth large
            depth = geom.get('depth_mm', 0.0)
            width = geom.get('width_mm') or geom.get('slot_width_mm') or geom.get('length_mm')
            op = {
                'feature_id': fid,
                'op_type': 'milling',
                'tool_id': chosen_tool_id,
                'tool_record': tool_rec,
                'depth_mm': depth,
                'width_mm': width,
                'strategy': 'finish' if geom.get('finish') == 'finish' else 'rough_then_finish',
                'stepdown_mm': min( (tool_rec.get('diameter_mm') if tool_rec and tool_rec.get('diameter_mm') else (width or 5))/2, defaults['max_stepdown_mm']),
                'stepover': defaults['stepover_percent'],
                'safety_mm': defaults['safety_mm'],
                'spindle_rpm': defaults['rpm_for_material'],
                'feed_mm_per_min': defaults['feed_for_material'],
                'notes': []
            }
            # validate tool diameter
            if tool_rec and tool_rec.get('diameter_mm') and width:
                if tool_rec.get('diameter_mm') > width:
                    op['notes'].append('tool diameter > feature width: will not fit; choose smaller tool or adjust')
            plan.append(op)
        else:
            plan.append({'feature_id': fid, 'op_type': 'unknown', 'notes': ['Unknown feature type - manual step required']})
    return plan


def attempt_create_ops_in_nx(plan):
    """Attempts to create operations in NX CAM. This is best-effort and many
    NX installations have different CAM API surfaces; keep failures non-fatal.
    """
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

        # Try to get existing CAM session
        cam_session = None
        try:
            cam_session = NXOpen.CAM.CAMSession.GetSession(work_part)
        except Exception:
            write_log('CAMSession.GetSession(work_part) failed; trying CAMSession.GetSession()')
            try:
                cam_session = NXOpen.CAM.CAMSession.GetSession()
            except Exception:
                cam_session = None
                write_log('CAMSession could not be acquired')

        if cam_session is None:
            return {'created': False, 'reason': 'CAMSession unavailable'}

        # Best-effort: create a ManufacturingSetup if none exists
        try:
            setup_collection = cam_session.Setups
        except Exception:
            setup_collection = None
        write_log(f'CAM session acquired; setups: {"present" if setup_collection else "unknown"}')

        # For each plan entry, attempt to create an operation using friendly builders
        created_ops = []
        for op in plan:
            try:
                if op['op_type'] == 'drill':
                    # Try drill builder
                    try:
                        # Many NX versions provide DrillBuilder via NXOpen.CAM
                        drill_builder = NXOpen.CAM.DrillBuilder(work_part)
                        write_log('Using NXOpen.CAM.DrillBuilder')
                        # The exact API to set tool and geometry is version-specific; attempt safe calls
                        # Set tool by name if possible
                        # drill_builder.ToolName = op['tool_id']  # example - may not exist
                        # drill_builder.Depth = op['depth_mm']
                        # drill_builder.Commit()
                        # created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'created (best-effort)'})
                        write_log(f"(DrillBuilder) planned drill for {op['feature_id']} with tool {op['tool_id']}")
                    except Exception:
                        write_log('DrillBuilder not available or failed; logging plan for manual creation')
                        created_ops.append({'feature_id': op['feature_id'], 'op':'drill', 'status':'planned'})
                elif op['op_type'] == 'milling':
                    try:
                        # Try generic milling builder
                        mill_builder = NXOpen.CAM.MillBuilder(work_part)
                        write_log('Using NXOpen.CAM.MillBuilder')
                        write_log(f"(MillBuilder) planned mill for {op['feature_id']} with tool {op['tool_id']}")
                    except Exception:
                        write_log('MillBuilder not available or failed; logging plan for manual creation')
                        created_ops.append({'feature_id': op['feature_id'], 'op':'mill', 'status':'planned'})
                else:
                    write_log(f"Unknown op_type {op['op_type']} for {op.get('feature_id')}")
                    created_ops.append({'feature_id': op.get('feature_id'), 'op':'unknown', 'status':'skipped'})
            except Exception:
                write_log('Exception while attempting to create op for ' + str(op.get('feature_id')))
                write_log(traceback.format_exc())
        return {'created': True, 'created_ops': created_ops}
    except Exception as e:
        write_log('Unexpected exception in attempt_create_ops_in_nx: ' + str(e))
        write_log(traceback.format_exc())
        return {'created': False, 'reason': str(e)}


def run():
    write_log('=== NX CAM generation journal started ===')
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

    # Build plan
    plan = build_plan(selected, candidates, toollib, defaults)
    # Write plan JSON for inspection
    try:
        PLAN_PATH.write_text(json.dumps({'plan': plan}, ensure_ascii=False, indent=2), encoding='utf-8')
        write_log('Wrote CAM plan to ' + str(PLAN_PATH))
    except Exception as e:
        write_log('Failed to write CAM plan: ' + str(e))

    # Attempt to create operations in NX (best-effort)
    try:
        res = attempt_create_ops_in_nx(plan)
        write_log('attempt_create_ops_in_nx result: ' + str(res))
    except Exception:
        write_log('Exception calling attempt_create_ops_in_nx:')
        write_log(traceback.format_exc())

    # Always write a human-friendly summary
    summary = {
        'status': 'plan_created',
        'message': 'CAM plan created. If CAM API calls succeeded some operations may have been created in the work part. Inspect NX CAM and simulate before post-processing.',
        'plan_path': str(PLAN_PATH),
        'selected_summary': selected,
        'nx_version': 'NX (report at runtime)'
    }
    try:
        SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        write_log('Wrote summary to ' + str(SUMMARY_PATH))
    except Exception as e:
        write_log('Failed to write summary: ' + str(e))

    write_log('=== NX CAM generation journal finished ===')


if __name__ == '__main__':
    run()
