# nxopen/export_toollib.py
"""
NXOpen journal to export NX local tool library into a standardized JSON file.
Run this script inside NX's Python environment (File -> Execute -> Journal).
Output: C:\cad-workbench\input\toollib_standard.json (and repo output if repository path available)

Notes:
- NXOpen API varies between versions; this script uses a best-effort approach and falls back to scanning common NX resource files if Tool Manager API isn't available.
- You must run it on the NX machine where the tool library is configured.
"""

import os
import json
import traceback

try:
    import NXOpen
    import NXOpen.Utilities
except Exception:
    NXOpen = None

OUT_LOCAL = r"C:\cad-workbench\input\toollib_standard.json"
# also write to repo output if present (adjust path as needed)
REPO_OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'output', 'toollib_standard.json')


def write_json(obj, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        print('Wrote toollib to', path)
    except Exception as e:
        print('Failed to write', path, e)


def export_via_nxopen():
    the_session = NXOpen.Session.GetSession()
    # Try Tooling API if available
    try:
        # Many NX installations expose a ToolManager or CAM Tooling API under NXOpen.CAM or NXOpen.Tooling
        tools = []
        # Try NXOpen.CAM
        try:
            import NXOpen.CAM
            mgr = NXOpen.CAM.ToolLibraryManager.GetToolLibraryManager(the_session)
            # This API is not guaranteed; placeholder for iteration
            # If available, user should adapt this block for exact API methods
            print('NXOpen.CAM ToolLibraryManager available (placeholder)')
            # Iterate tools (pseudo-code)
            # for t in mgr.GetAllTools():
            #     tools.append(...)
        except Exception:
            print('NXOpen.CAM.ToolLibraryManager not available or different in this NX version')

        # Try NXOpen.Tooling or older API
        try:
            # Example: some NX versions expose Tool classes in NXOpen
            if hasattr(NXOpen, 'Tool'):
                print('NXOpen.Tool exists; attempting to enumerate tools (best-effort).')
                # Pseudocode: actual enumeration depends on API
        except Exception:
            pass

        # If we could fill tools list, return
        if tools:
            return tools
        else:
            raise Exception('No Tool API enumeration implemented for this NX version in this script')
    except Exception as e:
        print('export_via_nxopen failed:', e)
        traceback.print_exc()
        return None


def fallback_scan_resource_files():
    # As a fallback, try to find NX resource folder and parse common 'holder_database.dat' or 'tool_database' files
    possible_roots = []
    # Try to derive from NX installation if available
    try:
        if NXOpen is not None:
            session = NXOpen.Session.GetSession()
            nx_root = session.GetSessionDirectory()
            possible_roots.append(nx_root)
    except Exception:
        pass
    # Common locations
    common = [r"C:\Program Files\Siemens\NX 12.0\MACH\resource\library\tool\english",
              r"C:\Program Files\Siemens\NX 12.0\MACH\resource\library\tool",
              r"C:\Siemens\NX\MACH\resource\library\tool\english"]
    possible_roots.extend(common)
    records = []
    for root in possible_roots:
        try:
            if not os.path.isdir(root):
                continue
            for fname in os.listdir(root):
                if fname.lower().endswith('.dat') or 'tool' in fname.lower():
                    path = os.path.join(root, fname)
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                            data = fh.read()
                        # Basic parse: split by lines and output as raw record lines (best-effort)
                        records.append({'source_file': path, 'content_preview': data[:2000]})
                    except Exception:
                        continue
        except Exception:
            continue
    return records


def main():
    print('NX toollib exporter starting...')
    exported = export_via_nxopen()
    if exported:
        write_json({'tools': exported}, OUT_LOCAL)
        try:
            write_json({'tools': exported}, REPO_OUTPUT)
        except Exception:
            pass
        return
    print('Falling back to scanning resource files...')
    recs = fallback_scan_resource_files()
    if recs:
        write_json({'raw_records': recs}, OUT_LOCAL)
        try:
            write_json({'raw_records': recs}, REPO_OUTPUT)
        except Exception:
            pass
        print('Wrote fallback raw records. Please check and run the normalization script on the machine or paste the output here.')
    else:
        print('No tool data found via fallback. Please export tool library from NX Tool Manager to CSV/XML and place it in C:\\cad-workbench\\input or repo output folder.')


if __name__ == '__main__':
    main()
