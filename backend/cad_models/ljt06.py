import cadquery as cq

def build_part(p: dict):
    # p is a dict of parameters
    bl = p.get("base_length",224.0)
    bw = p.get("base_width",90.0)
    bt = p.get("base_thickness",10.0)

    # base: centered on XY, top at z=0
    base = cq.Workplane("XY").box(bl, bw, bt).translate((0,0,bt/2.0))
    part = base

    # two base holes
    hole_d = p.get("base_hole_dia",35.0) if "base_hole_dia" in p else 35.0
    spacing = p.get("base_hole_spacing",146.0) if "base_hole_spacing" in p else 146.0
    part = part.cut(cq.Workplane("XY").workplane(offset=0).center(spacing/2.0,0).hole(hole_d))
    part = part.cut(cq.Workplane("XY").workplane(offset=0).center(-spacing/2.0,0).hole(hole_d))

    # vertical web
    wt = p.get("web_thickness",28.0)
    ww = p.get("web_width",72.0)
    web_h = p.get("web_center_z",140.0) + p.get("big_cyl_outer_dia",56.0)/2.0
    web = cq.Workplane("XZ").rect(ww, wt).extrude(web_h).translate((0,(bw/2.0 - wt/2.0),0))
    part = part.union(web)

    # big cylinder
    big_r = p.get("big_cyl_outer_dia",56.0)/2.0
    big_inner = p.get("big_cyl_inner_dia",35.0)
    cyl_z = p.get("web_center_z",140.0)
    cyl_y = (bw/2.0 - wt/2.0) + (wt/2.0)
    cyl = cq.Workplane("XY").center(0,cyl_y).workplane(offset=cyl_z).circle(big_r).extrude(10)
    cyl = cyl.cut(cq.Workplane("XY").center(0,cyl_y).workplane(offset=cyl_z).hole(big_inner))
    part = part.union(cyl)

    # lower cylinder (front)
    lower_r = p.get("lower_cyl_outer",28.0)
    lower_inner = p.get("lower_cyl_inner",10.0)
    lower_z = 35.0
    lower_y = - (bw/2.0 - big_r)
    lower = cq.Workplane("XY").center(0, lower_y).workplane(offset=lower_z).circle(lower_r).extrude(14)
    lower = lower.cut(cq.Workplane("XY").center(0, lower_y).workplane(offset=lower_z).hole(lower_inner))
    part = part.union(lower)

    return part
