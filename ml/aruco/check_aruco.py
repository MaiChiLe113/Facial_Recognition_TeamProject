"""Check whether OpenCV can read every ArUco marker in a camera image (DICT_4X4_50).

Prints, per image, the marker ids found, their size in pixels, and a verdict:
  PASS  every expected id was found (and is big enough to be reliable)
  WARN  all found, but some are small (< --min-side px), may fail on another shot
  FAIL  some expected ids are missing
An annotated copy (<name>_check.png) is written next to each image.

Examples:
  python ml/aruco/check_aruco.py cam_1_aruco.png --expect 3,4,5,6,7
  python ml/aruco/check_aruco.py cam_2_aruco.png --expect 0,2,3,7
  python ml/aruco/check_aruco.py photo.jpg   # no --expect: just list what is found
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

DICT = cv2.aruco.DICT_4X4_50


def make_detector(tuned):
    params = cv2.aruco.DetectorParameters()
    if tuned:  # better for small / slanted markers seen at a low angle
        params.adaptiveThreshWinSizeMin = 3
        params.adaptiveThreshWinSizeMax = 53
        params.adaptiveThreshWinSizeStep = 4
        params.minMarkerPerimeterRate = 0.01
        params.polygonalApproxAccuracyRate = 0.05
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICT), params)


def detect(gray):
    """Run the default detector, then a tuned one and a contrast-boosted pass; merge results."""
    found = {}
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    for name, det, img in (("default", make_detector(False), gray),
                           ("tuned", make_detector(True), gray),
                           ("tuned+contrast", make_detector(True), clahe)):
        corners, ids, _ = det.detectMarkers(img)
        for c, i in zip(corners, [] if ids is None else ids.ravel()):
            found.setdefault(int(i), (c.reshape(4, 2), name))
    return found


def side_px(c):
    """Shortest marker side in the image (pixels): small = far or seen very flat."""
    return min(np.linalg.norm(c[k] - c[(k + 1) % 4]) for k in range(4))


def check(path, expect, min_side):
    img = cv2.imread(str(path))
    if img is None:
        print(f"{path}: cannot read image")
        return "FAIL"
    found = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    h, w = img.shape[:2]
    print(f"\n{path}  ({w}x{h})")
    small = []
    for i in sorted(found):
        c, how = found[i]
        s = side_px(c)
        cx, cy = c.mean(axis=0)
        bottom = (c[2] + c[3]) / 2
        note = "" if s >= min_side else "  <- small"
        if s < min_side:
            small.append(i)
        print(f"  id {i:2d}: centre ({cx:6.1f}, {cy:6.1f})  bottom-mid ({bottom[0]:6.1f}, {bottom[1]:6.1f})"
              f"  shortest side {s:5.1f} px  [{how}]{note}")
        pts = c.astype(int)
        col = (0, 200, 255) if s < min_side else (0, 220, 0)
        cv2.polylines(img, [pts], True, col, 2)
        cv2.circle(img, (int(cx), int(cy)), 3, (0, 0, 255), -1)
        cv2.putText(img, str(i), (int(cx) + 6, int(cy) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)

    missing = sorted(set(expect) - set(found)) if expect else []
    extra = sorted(set(found) - set(expect)) if expect else []
    if not found:
        verdict = "FAIL"
    elif missing:
        verdict = "FAIL"
    elif small:
        verdict = "WARN"
    else:
        verdict = "PASS"
    print(f"  found:    {sorted(found) or 'none'}")
    if expect:
        print(f"  expected: {sorted(expect)}")
        print(f"  missing:  {missing or 'none'}")
        if extra:
            print(f"  extra:    {extra} (not in --expect, check the marker number)")
    if small:
        print(f"  small:    {small} (shortest side < {min_side} px: print bigger, move closer, or stand it up)")
    print(f"  VERDICT:  {verdict}")
    if len(found) < 4:
        print("  note: the homography needs at least 4 markers per camera")

    cv2.putText(img, f"{verdict}  found {sorted(found)}  missing {missing}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if verdict == "FAIL" else (0, 160, 0), 2)
    out = path.with_name(path.stem + "_check.png")
    cv2.imwrite(str(out), img)
    print(f"  annotated: {out}")
    return verdict


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--expect", default="", help="comma-separated marker ids that should be visible, e.g. 3,4,5,6,7")
    ap.add_argument("--min-side", type=float, default=20.0, help="warn below this marker side length in px (default 20)")
    a = ap.parse_args()
    expect = [int(x) for x in a.expect.split(",") if x.strip()]
    verdicts = [check(p, expect, a.min_side) for p in a.images]
    sys.exit(0 if all(v != "FAIL" for v in verdicts) else 1)


if __name__ == "__main__":
    main()
