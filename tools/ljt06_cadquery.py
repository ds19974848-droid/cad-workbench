# Standalone CadQuery runner - generates ljt06.step and ljt06.stl
# Run this script in a conda environment with cadquery installed
from cad_models.ljt06 import build_part
from cadquery import exporters

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
    "lower_cyl_inner": 10.0
}

part = build_part(params)
exporters.export(part, "ljt06.step")
exporters.export(part, "ljt06.stl")
print("Exported ljt06.step and ljt06.stl")
