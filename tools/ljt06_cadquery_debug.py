# tools/ljt06_cadquery_debug.py
import os, sys
from cad_models.ljt06 import build_part
from cadquery import exporters

# 参数（你可以在这里修改以测试不同数值）
params = {
    "base_length": 224.0,
    "base_width": 90.0,
    "base_thickness": 10.0,
    "big_cyl_outer_dia": 56.0,
    "big_cyl_inner_dia": 35.0,
    "web_thickness": 28.0,
    "web_width": 72.0,
    "web_center_z": 140.0,
    "lower_cyl_outer": 28.0,
    "lower_cyl_inner": 10.0,
    "lower_cyl_center_z": 35.0,
    # threads: list of thread descriptors. We will add an M18 thread as requested.
    "threads": [
        {
            "name": "big_hole_thread",
            "center": (0.0,  (90.0/2.0 - 28.0/2.0)),
            "start_z": 140.0 - 5.0,  # starting a little below center to create internal thread along hole
            "length": 40.0,
            "diameter": 18.0,
            "minor_d": 16.0,
            "pitch": 2.5,
            "right_hand": True
        }
    ]
}

print("Using params:")
for k,v in params.items():
    print(f"  {k}: {v}")

print("\nComputed helpers (expected):")
bw = params["base_width"]
wt = params["web_thickness"]
big_r = params["big_cyl_outer_dia"]/2.0
cyl_center_y = (bw/2.0 - wt/2.0)
web_total_height = params["web_center_z"] + big_r
print(f"  cyl_center_y = {cyl_center_y}")
print(f"  web_total_height = {web_total_height}")
print(f"  expected bbox X span ~ +/- {params['base_length']/2.0}")
print(f"  expected bbox Y span ~ +/- {params['base_width']/2.0}")

print("\nBuilding part...")
part = build_part(params)

# try to get bounding box
try:
    shape = part.val()
    bb = shape.BoundingBox()
    print("\nBounding box:")
    print(f"  xmin: {bb.xmin:.3f}, xmax: {bb.xmax:.3f}")
    print(f"  ymin: {bb.ymin:.3f}, ymax: {bb.ymax:.3f}")
    print(f"  zmin: {bb.zmin:.3f}, zmax: {bb.zmax:.3f}")
except Exception as e:
    print("Failed to read bounding box:", e)

# export files
out_step = os.path.abspath("ljt06_debug_step_thread.step")
out_stl = os.path.abspath("ljt06_debug_thread.stl")
print("\nExporting STEP to", out_step)
try:
    exporters.export(part, out_step)
    print("Exported STEP OK")
except Exception as e:
    print("STEP export failed:", e)

print("Exporting STL to", out_stl)
try:
    exporters.export(part, out_stl)
    print("Exported STL OK")
except Exception as e:
    print("STL export failed:", e)

print("\nDone. Files saved in current directory.")
