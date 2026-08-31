"""backend/tools/normalize_toollib.py

Normalize extracted NX tool library JSON into a canonical toollib.json used by the PoC.

Input (expected): backend/output/toollib_extracted.json or backend/output/toollib.json
Output: backend/output/toollib_standard.json (canonical schema)

Run locally (from repo root):
  conda activate <env>
  python backend/tools/normalize_toollib.py

This script is defensive: if the input file is missing, it prints instructions.
"""
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
IN_PATHS = [ROOT / 'output' / 'toollib_extracted.json', ROOT / 'output' / 'toollib.json']
OUT_PATH = ROOT / 'output' / 'toollib_standard.json'

# Schema fields we aim for:
# tool_id, record_type, library_reference, description, type, subtype, unit, diameter_mm, length_mm, shank, max_rpm, feed_mm_per_rev, raw_fields

def safe_get(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return default


def parse_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    raw = rec.get('raw_fields', {}) if isinstance(rec.get('raw_fields', {}), dict) else {}
    # Some records may already include numeric fields; try common names
    # default values
    diameter = None
    length = None
    max_rpm = None
    feed = None

    # heuristic: look for Field004/005/006 in raw_fields which often contained numeric dims in preview
    for cand in ['Field004','Field005','Field006','Field007','Field008']:
        if cand in raw:
            val = raw.get(cand)
            if val is None or val == '':
                continue
            try:
                f = float(val)
            except Exception:
                continue
            # heuristics: if value > 1000 it's unlikely; we just map Field006 -> often rpm in preview
            if cand == 'Field006' and (f>0):
                # in preview Field006 often looked like 35.00000 (maybe length or rpm); keep as length by default
                if diameter is None:
                    diameter = None
                if length is None and f>0:
                    length = f
            else:
                # try assignment if diameter is small (<100) and diameter not set
                if diameter is None and 0 < f < 200:
                    diameter = f
    # if record contains explicit 'diameter_mm' name use it
    diameter = rec.get('diameter_mm') or diameter
    length = rec.get('length_mm') or length
    # Build normalized record
    norm = {
        'tool_id': rec.get('library_reference') or rec.get('tool_id') or f"rec_{rec.get('record_number', '')}",
        'record_type': rec.get('record_type'),
        'library_reference': rec.get('library_reference'),
        'description': rec.get('description'),
        'type': rec.get('tool_type_code'),
        'subtype': rec.get('tool_subtype_code'),
        'unit': rec.get('unit'),
        'diameter_mm': diameter,
        'length_mm': length,
        'shank': safe_get(raw, 'shank', 'holder', default=None),
        'max_rpm': max_rpm,
        'feed_mm_per_rev': feed,
        'raw_fields': raw
    }
    return norm


def main():
    in_file = None
    for p in IN_PATHS:
        if p.exists():
            in_file = p
            break
    if in_file is None:
        print('No input toollib JSON found. Place your extracted file as one of:')
        for p in IN_PATHS:
            print('  ', p)
        print('\nIf you have a zip from NX, run the provided convert_toollib.py locally to produce the extracted JSON, then re-run this script.')
        return

    print('Reading toollib from', in_file)
    data = json.loads(in_file.read_text(encoding='utf-8'))
    # assume top-level is a list or dict with 'tools'
    if isinstance(data, dict) and 'tools' in data:
        records = data['tools']
    elif isinstance(data, list):
        records = data
    else:
        # maybe an object with numeric keyed records
        records = data
    normalized = []
    for rec in records:
        try:
            n = parse_record(rec)
            normalized.append(n)
        except Exception as e:
            print('Failed to parse record', rec.get('record_number', '<n>'), e)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({'tools': normalized}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {len(normalized)} normalized records to', OUT_PATH)
    # print preview first 20
    print('\nPreview (first 20):')
    for i, r in enumerate(normalized[:20], start=1):
        print(i, r['tool_id'], r['record_type'], r.get('description') or r.get('library_reference'))

if __name__ == '__main__':
    main()
