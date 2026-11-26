"""Draw the Room 204 measuring plan, one picture per part of MEASURING.md:
figures/plan_A.png (preparation), _B (markers), _C (desks), _D (cameras).

The tape lines and their step numbers are read from result.yaml ("# --- X." = part,
"# N." = step), so the pictures follow the yaml. Never edit the PNGs by hand: change
MEASURING.md, mirror it in result.yaml, then run  python ml/aruco/draw_plan.py
"""
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = HERE / "data" / "result.yaml"

# ---- geometry of the base drawing (fractions of the 920x520 room204_map.png)
Wp, Hp = 920, 520
cols = [(340, 540), (645, 845)]
rows = [(117, 153), (194, 231), (268, 305), (343, 380)]
DESKS = [[a / Wp, r0 / Hp, (b - a) / Wp, (r1 - r0) / Hp] for (r0, r1) in rows for (a, b) in cols] \
    + [[773 / Wp, 434 / Hp, 94 / Wp, 36 / Hp]]
WALL = 280 / Wp
DOOR0, DOOR1 = 380 / Hp, 468 / Hp
GLASS0, GLASS1 = 0.40, 0.634
SX, SY = 0.0875, 0.143            # map units per metre (room204_map.json scale_per_m)
# Real camera positions / headings (hand-fitted camera models, checked on AppliedML/video data):
# CAM 1 looks south-east at the room wall; CAM 2 looks west along the south aisle to the door.
CAMS = {
    "cam_1": dict(x=0.078, y=0.347, head=45, half=40, near=1.5, col=(209, 47, 47)),
    "cam_2": dict(x=0.755, y=0.795, head=185, half=41, near=1.7, col=(26, 138, 74)),
}
MARKERS = {0: (0.42, 0.82), 2: (0.50, 0.95), 3: (0.31, 0.77), 7: (0.31, 0.86),
           4: (0.25, 0.47), 5: (0.15, 0.60), 6: (0.22, 0.70)}
WALLPTS = {"glass_top": GLASS0, "glass_bottom": GLASS1, "door_top": DOOR0, "door_bottom": DOOR1}

PTS = {"O": (CAMS["cam_1"]["x"], CAMS["cam_1"]["y"]), "P0": (WALL, CAMS["cam_1"]["y"]),
       "P0_in": (WALL + 0.02, CAMS["cam_1"]["y"]), "CAM2": (CAMS["cam_2"]["x"], CAMS["cam_2"]["y"])}
for k, yy in WALLPTS.items():
    PTS[k] = (WALL - 0.004, yy)
    PTS[k + "_in"] = (WALL + 0.02, yy)
for n, xy in MARKERS.items():
    PTS[f"M{n}"] = xy
for i in (1, 3, 5, 7):
    PTS[f"D{i}"] = tuple(DESKS[i - 1][:2])

# ---- drawing setup
S = 1.5
OX, OY = 110, 130
base = Image.open(REPO / "data/calibration/room204_map.png").convert("RGB")
MW, MH = int(base.size[0] * S), int(base.size[1] * S)
CW, CH = MW + OX + 240, MH + OY + 230
F = lambda s, b=False: ImageFont.truetype(r"C:\Windows\Fonts\segoeui%s.ttf" % ("b" if b else ""), s)
f12, f14, f16, f20, f14b, f16b = F(12), F(14), F(16), F(20), F(14, True), F(16, True)
BLUE, RED, GREEN, ORANGE, GREY, PURPLE, DKGREEN = \
    "#1f5fd1", "#d12f2f", "#1a8a4a", "#e07b00", "#555", (122, 47, 208), (20, 100, 60)
img = d = None


def P(x, y):
    return OX + x * MW, OY + y * MH


def label(xy, s, font=f14b, fill=BLUE, anchor="la", bg=True):
    if bg:
        l, t, r, b = d.textbbox(xy, s, font=font, anchor=anchor)
        d.rectangle((l - 3, t - 2, r + 3, b + 2), fill=(255, 255, 255))
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


def arrow(a, b, col=BLUE, w=2):
    d.line([a, b], fill=col, width=w)
    for p, q in ((a, b), (b, a)):
        dx, dy = q[0] - p[0], q[1] - p[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1
        ux, uy = dx / n, dy / n
        for sgn in (1, -1):
            d.line([p, (p[0] + ux * 10 - sgn * uy * 5, p[1] + uy * 10 + sgn * ux * 5)], fill=col, width=w)


def dashed(a, b, col=GREY, step=7):
    n = max(1, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / step))
    for i in range(0, n, 2):
        p = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
        q = (a[0] + (b[0] - a[0]) * (i + 1) / n, a[1] + (b[1] - a[1]) * (i + 1) / n)
        d.line([p, q], fill=col, width=1)


def ray_end(c, ang):
    """Walk a ray (in metres) until it leaves the floor the camera can see."""
    X, Y = c["x"] / SX, c["y"] / SY
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    r = 0.0
    while r < 15:
        r += 0.02
        x, y = (X + dx * r) * SX, (Y + dy * r) * SY
        if not (0 <= x <= 1 and 0 <= y <= 1):
            break
        crossing = (c is CAMS["cam_1"] and x > WALL) or (c is CAMS["cam_2"] and x < WALL)
        if crossing and (not (DOOR0 <= y <= DOOR1) or abs(x - WALL) > 0.05):
            break
        if c is CAMS["cam_2"] and y < DOOR0 and x > WALL:   # first desk row hides the floor behind it
            break
    return r


def to_px(c, ang, r):
    X, Y = c["x"] / SX, c["y"] / SY
    a = math.radians(ang)
    return P((X + math.cos(a) * r) * SX, (Y + math.sin(a) * r) * SY)


def read_yaml_plan():
    """result.yaml -> {key: (part letter, step number)} from its '# --- X.' and '# N.' headers."""
    plan, part, step = {}, None, None
    for line in RESULT.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"#\s*---\s*([A-Z])\.", line):
            part = m.group(1)
        elif m := re.match(r"#\s*(\d+)\.", line):
            step = int(m.group(1))
        elif m := re.match(r"([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)?)\s*:", line):
            plan[m.group(1)] = (part, step)
    return plan


def new_canvas(title, sub):
    """Base map + view cones + cameras + desks + markers (no labels of other parts)."""
    global img, d
    img = Image.new("RGB", (CW, CH), "white")
    img.paste(base.resize((MW, MH), Image.LANCZOS), (OX, OY))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((OX + 24 * S, OY + 70 * S, OX + 104 * S, OY + 108 * S), 10, fill="white")
    d.rounded_rectangle((OX + 662 * S, OY + 434 * S, OX + 742 * S, OY + 472 * S), 10, fill=(206, 243, 212))
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for c in CAMS.values():
        angs = [c["head"] - c["half"] + i for i in range(0, 2 * c["half"] + 1, 2)]
        outer = [to_px(c, a, ray_end(c, a)) for a in angs]
        inner = [to_px(c, a, c["near"]) for a in reversed(angs)]
        od.polygon(outer + inner, fill=c["col"] + (45,), outline=c["col"] + (160,))
    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    d = ImageDraw.Draw(img)
    for k, c in CAMS.items():
        p = P(c["x"], c["y"])
        for a in (c["head"] - c["half"], c["head"] + c["half"]):
            dashed(p, to_px(c, a, c["near"]), "#%02x%02x%02x" % c["col"])
        d.rounded_rectangle((p[0] - 34, p[1] - 14, p[0] + 34, p[1] + 14), 10, fill=(110, 110, 110))
        d.text(p, "CAM " + k[-1], font=f14b, fill="white", anchor="mm")
    for i, (x, y, w, h) in enumerate(DESKS, 1):
        (a, b), (cc, e) = P(x, y), P(x + w, y + h)
        used = i in (1, 3, 5, 7)
        label(((a + cc) / 2, (b + e) / 2), f"D{i}" if used else f"D{i} (skip)",
              f14b if used else f12, GREEN if used else GREY, "mm", bg=False)
    d.text((OX, 16), title, font=f20, fill="black")
    d.text((OX, 48), sub, font=f12, fill=GREY)
    d.text((OX, 66), "Origin O = floor under CAM 1.  Shaded = floor each camera really sees (cameras are not 360).  "
           "Numbers in [ ] = step in MEASURING.md and '# N.' in result.yaml.", font=f12, fill=GREY)


def draw_markers(note=None):
    for n, (x, y) in MARKERS.items():
        px_, py_ = P(x, y)
        s = 14
        d.rectangle((px_ - s, py_ - s, px_ + s, py_ + s), fill="black")
        d.rectangle((px_ - s + 4, py_ - s + 4, px_ + s - 4, py_ + s - 4), fill="white")
        d.text((px_, py_), str(n), font=f14b, fill="black", anchor="mm")
        if note:
            label((px_ + s + 4, py_), note(n), f12, PURPLE, "lm")


def dot(name, col, text=None, anchor="ls", off=(8, -8), r=5, font=f12):
    p = P(*PTS[name])
    d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=col)
    if text:
        label((p[0] + off[0], p[1] + off[1]), text, font, col, anchor)


def tape_lines(plan, part, col):
    steps = {}
    for k, (pt, st) in plan.items():
        if pt != part or "-" not in k:
            continue
        a, b = k.split("-", 1)
        c = DKGREEN if "CAM2" in k else col
        d.line([P(*PTS[a]), P(*PTS[b])], fill=c, width=2)
        steps.setdefault(st, set()).update((a, b))
    return steps


def target_steps(plan, part):
    """Step number of each point measured in this part = first step where it is the 2nd name of 'A-B'."""
    out = {}
    for k, (pt, st) in plan.items():
        if pt == part and "-" in k:
            out.setdefault(k.split("-", 1)[1], st)
    return out


def legend(items, foot):
    ly = OY + MH + 24
    d.line([(OX, ly - 10), (OX + MW, ly - 10)], fill="#ccc")
    for i, (c, s_) in enumerate(items):
        yy = ly + i * 24
        d.rectangle((OX, yy + 3, OX + 14, yy + 17), fill=c)
        d.text((OX + 24, yy), s_, font=f14, fill="black")
    d.text((OX, ly + len(items) * 24 + 8), foot, font=f12, fill=GREY)


def save(part):
    out = HERE / "figures" / f"plan_{part}.png"
    img.save(out)
    print("wrote", out.name)


def part_A(plan):
    new_canvas("A. Preparation  [steps 1-6]",
               "Mark O and P0, measure x_wall, wall_thickness, and the y of the 4 wall edges. Tape the 7 markers inside the shading.")
    o, p0 = P(*PTS["O"]), P(*PTS["P0"])
    dot("O", RED, "[1] O = plumb line from CAM 1", "ls", (-100, -26), 7, f14b)
    arrow((o[0] + 10, o[1]), (p0[0] - 6, p0[1]), BLUE, 2)
    label(((o[0] + p0[0]) / 2, o[1] - 6), "[2] x_wall (right angle to the wall)", f14b, BLUE, "ms")
    dot("P0", BLUE, "P0", "ls", (10, -10), 7, f14b)
    xa = p0[0] - 14
    arrow((xa, p0[1]), (xa, P(0, DOOR1)[1]), ORANGE, 2)
    label((xa - 6, P(0, 0.53)[1]), "[4] one tape from P0 along the wall", f12, ORANGE, "rm")
    for k in WALLPTS:
        q = P(WALL, WALLPTS[k])
        d.ellipse((q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5), fill=ORANGE)
        label((q[0] + 30, q[1]), f"[4] {k}: y = reading", f12, ORANGE, "lm")
    dm = P(WALL, (DOOR0 + DOOR1) / 2)
    label((dm[0] - 30, dm[1] - 30), "[3] wall_thickness (in the doorway)", f12, BLUE, "rm")
    draw_markers()
    legend([(RED, "[1] O = floor point under CAM 1 (plumb line), tape mark"),
            (BLUE, "[2] x_wall = tape O -> wall at a right angle (check 3-4-5); the spot on the wall = P0 (K)"),
            (ORANGE, "[4] y of glass_top, glass_bottom, door_top, door_bottom = ONE tape laid from P0 along the wall base"),
            (PURPLE, "[5] tape markers: 4, 5, 6 in the red shading; 3, 7 in the doorway; 0, 2 in the green shading"),
            (GREY, "[6] check_aruco.py on a photo of each camera until PASS (CAM 1: 3,4,5,6,7   CAM 2: 0,2,3,7)")],
           "Steps 2-4 fix the axes for everything else: P0 must be a real right angle, the step-4 tape must stay on the wall base.")
    save("A")


def part_B(plan):
    new_canvas("B. Markers  [steps 7-13]",
               "Each purple line = one straight tape from a known point to a marker CENTRE. survey.py computes x, y.")
    tape_lines(plan, "B", PURPLE)
    dot("O", RED, "O", "rs", (-10, -10), 7, f14b)
    dot("P0", BLUE, "P0", "ls", (10, -10), 6, f14b)
    for k in ("door_top", "door_bottom"):
        dot(k, ORANGE, k, "rm", (-10, 0))
    dot("door_bottom_in", ORANGE)
    ts = target_steps(plan, "B")
    draw_markers(lambda n: f"[{ts.get(f'M{n}', '')}] M{n}")
    legend([(PURPLE, "Purple line = tape distance named 'A-B' in result.yaml (e.g. O-M4 = from O to the centre of marker 4)"),
            (RED, "O, P0 and the door edges are the known points from part A"),
            (GREY, "[13] when done: nobody in the frame, one 1280x720 photo per camera -> cam_1_aruco.png, cam_2_aruco.png")],
           "Order: 4, 5, 6 (from O, P0)  ->  3, 7 (from O and the door edges)  ->  0, 2 (from 3, 7, the wall and each other).")
    save("B")


def part_C(plan):
    new_canvas("C. Desks D1, D3, D5, D7  [steps 15-19]",
               "Each green line = one straight tape to the top-left corner of a tabletop (near the room wall, far from the door).")
    tape_lines(plan, "C", GREEN)
    for k in ("glass_top_in", "glass_bottom_in", "door_top_in", "P0_in"):
        dot(k, ORANGE, k, "rm", (-12, 0))
    draw_markers()
    for n, st in target_steps(plan, "C").items():
        if n.startswith("D"):
            dot(n, GREEN, f"[{st}] {n}", "rs", (-8, -8), 6, f14b)
    x, y, w, h = DESKS[0]
    (a, b), (cc, e) = P(x, y), P(x + w, y + h)
    arrow((a, b - 22), (cc, b - 22), GREEN, 1)
    label(((a + cc) / 2, b - 24), "[15] desk_L", f12, GREEN, "ms")
    arrow((cc + 10, b), (cc + 10, e), GREEN, 1)
    label((cc + 14, (b + e) / 2), "[15] desk_W", f12, GREEN, "lm")
    legend([(GREEN, "Green line = tape distance named 'A-B' in result.yaml (e.g. M3-D7 = from marker 3 to the corner of desk D7)"),
            (ORANGE, "'_in' = the same wall edge on the ROOM side of the wall"),
            (GREY, "[15] desk_L, desk_W once (all desks the same).  D2, D4, D6, D8, D9: no camera sees them, skip")],
           "Order: D7 (from 3, 0, door)  ->  D5  ->  D3  ->  D1, each one from the desk before it and the wall edges.")
    save("C")


def part_D(plan):
    new_canvas("D. Cameras  [step 20]",
               "Dark green lines = tape from markers 0, 2 and glass_top_in to the floor point under CAM 2 (plumb line).")
    tape_lines(plan, "D", DKGREEN)
    draw_markers()
    dot("O", RED, "O", "rs", (-10, -10), 7, f14b)
    dot("CAM2", DKGREEN, "[20] CAM2 = plumb line under CAM 2", "ls", (40, 30), 7, f14b)
    legend([(DKGREEN, "[20] glass_top_in-CAM2, M2-CAM2, M0-CAM2"),
            (RED, "Optional, any time: desk_height, cam1_height, cam2_height (from the floor)")],
           "Then [21]: run python ml/aruco/survey.py and re-measure every line it marks '<- check this one'.")
    save("D")


if __name__ == "__main__":
    plan = read_yaml_plan()
    for f in (part_A, part_B, part_C, part_D):
        f(plan)
