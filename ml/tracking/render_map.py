"""Render room204_map.json (+ the calibration floor points) to an SVG for a quick look.

The JSON is the source; the SVG is generated for viewing only, do not edit it by hand.
Run: python ml/tracking/render_map.py
"""
import json
from pathlib import Path

CALIB = Path(__file__).resolve().parents[2] / "data" / "calibration"
W, H, PAD = 920, 520, 40  # same size as the old FigJam drawing
COLORS = {"cam_1": "#e5484d", "cam_2": "#30a46c", "attendance_cam": "#8e4ec6"}


def px(x, y):
    return PAD + x * W, PAD + y * H


def rect(x0, x1, y0, y1, **style):
    (a, b), (c, d) = px(x0, y0), px(x1, y1)
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in style.items())
    return f'<rect x="{a:.1f}" y="{b:.1f}" width="{c - a:.1f}" height="{d - b:.1f}" {attrs}/>'


def text(x, y, s, size=12, **style):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in style.items())
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="sans-serif" {attrs}>{s}</text>'


def render(m):
    out = [
        rect(*m["corridor"]["x"], *m["corridor"]["y"], fill="#f1f0ef", stroke="#888"),
        rect(*m["room"]["x"], *m["room"]["y"], fill="#fff", stroke="#888"),
    ]
    for x, y, w, h in m.get("desks", []):
        out.append(rect(x, x + w, y, y + h, fill="#e8e4dc", stroke="#b5ad9e", rx=4))
    # Corridor / room wall, leaving the door gap
    wx = m["corridor_wall_x"]
    d0, d1 = m["door"]["y"]
    for y0, y1 in [(0, d0), (d1, 1)]:
        out.append(rect(wx - 0.008, wx + 0.008, y0, y1, fill="#555"))
    out.append(text(*px(wx - 0.05, (d0 + d1) / 2), "Door", 11))
    g0, g1 = m["glass_window"]["y"]
    out.append(rect(wx - 0.008, wx + 0.008, g0, g1, fill="#7cc4fa"))
    out.append(text(*px(wx - 0.09, (g0 + g1) / 2), "Glass", 11))
    out.append(text(*px(0.02, 0.04), "Corridor", 14))
    out.append(text(*px(0.6, 0.04), "Room 204", 14))

    # Calibration floor points from cam_*_homography.json
    for f in sorted(CALIB.glob("cam_*_homography.json")):
        h = json.loads(f.read_text(encoding="utf-8"))
        c = COLORS.get(h["cam_id"], "#000")
        for i, (x, y) in enumerate(h["map_points"], 1):
            cx, cy = px(x, y)
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c}"/>')
            out.append(text(cx + 5, cy - 4, str(i), 9, fill=c))

    # Cameras
    for name, cam in m["cameras"].items():
        cx, cy = px(cam["x"], cam["y"])
        c = COLORS.get(name, "#000")
        out.append(f'<rect x="{cx - 8:.1f}" y="{cy - 8:.1f}" width="16" height="16" rx="3" fill="{c}"/>')
        out.append(text(cx + 11, cy + 4, f'{name} ({cam["x"]}, {cam["y"]})', 11, fill=c))

    out.append(text(PAD, H + PAD + 25, "Dots = homography floor points (coloured by camera). "
                    "Coordinates: x 0 left -> 1 right, y 0 top -> 1 bottom.", 11, fill="#666"))
    body = "\n  ".join(out)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * PAD}" height="{H + 2 * PAD + 20}">\n'
            f'  <rect width="100%" height="100%" fill="#fafafa"/>\n  {body}\n</svg>\n')


if __name__ == "__main__":
    m = json.loads((CALIB / "room204_map.json").read_text(encoding="utf-8"))
    dst = CALIB / "room204_map.svg"
    dst.write_text(render(m), encoding="utf-8")
    print(f"Wrote {dst}")
