"""Try backend/app/pipeline/liveness.py on photos AND videos, including tilted faces.

Run from the repo root:

    python ml/anti_spoofing/try_liveness.py test_faces
    python ml/anti_spoofing/try_liveness.py test_faces --save-crops test_crops
    python ml/anti_spoofing/try_liveness.py "D:/Projects/data/AppliedML/video data"
    python ml/anti_spoofing/try_liveness.py a.jpg b.heic clip.webm

What it does for every file:
  1. finds the largest face. It tries a straight face first, then the image rotated by
     +-15, +-30 and +-45 degrees (head tilted to a shoulder), then a side view (profile).
  2. cuts the face out with a margin and calls liveness.check() on it.
  3. prints how the face was found, plus live/score.

For a tilted face it prints two results: "as-is" (the crop exactly as an attendance cam
would hand it over, still tilted) and "upright" (the same face turned upright). If
upright is live but as-is is not, the model itself is weak on tilt.

Videos (.webm .mp4 .mov ...): every --every-th frame is read (up to --max-frames of them),
the face is cut out of each, and check() is run on windows of 10 consecutive crops, the
same way the real pipeline would call it.

All people in the team folders are REAL, so the expected answer is live=True. A False on
a real face is a false rejection.

--all-faces   photos only: judge every face found (e.g. your real face AND the face on
              a phone screen), one line per face, largest first.
--no-crop     the files are already tight face crops: skip the face search.
--save-crops  save the crops fed to the model so you can look at them.

iPhone .HEIC photos need `pip install pillow-heif`. Face search needs `pip install
"opencv-python<5"` (OpenCV 5 has no Haar detector).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

IMG_EXT = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp", ".heic", ".heif"}
VID_EXT = {".webm", ".mp4", ".mov", ".avi", ".mkv", ".m4v"}
ANGLES = [0, 15, -15, 30, -30, 45, -45]  # image rotations tried when looking for a tilted face
WINDOW = 10  # check() gets ~10 recent crops

try:  # lets PIL open iPhone HEIC/HEIF photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_OK = True
except ImportError:
    HEIF_OK = False


def collect(paths):
    files = []
    for a in paths:
        p = Path(a)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in IMG_EXT | VID_EXT)
        else:
            files.append(p)
    return files


def load_bgr(path):
    """Open an image, apply the phone's rotation flag, return HxWx3 uint8 in BGR order."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.ascontiguousarray(np.asarray(img)[..., ::-1])


def square_crop(img, cx, cy, side):
    """Square-ish crop of `side` pixels centred on (cx, cy), clipped to the image."""
    h, w = img.shape[:2]
    half = side / 2.0
    x0, x1 = int(max(0, cx - half)), int(min(w, cx + half))
    y0, y1 = int(max(0, cy - half)), int(min(h, cy + half))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return np.ascontiguousarray(img[y0:y1, x0:x1])


class FaceFinder:
    """Finds the largest face, also when the head is tilted or turned (OpenCV Haar cascades).

    Plan per image: straight face, then the image rotated by ANGLES, then a profile face
    (and its mirror image). The method that worked last time is tried first, so video is fast.
    """

    def __init__(self, margin=0.25):
        import cv2

        if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5.x dropped it from the main package
            raise RuntimeError('This OpenCV has no face detector. Run: pip install "opencv-python<5"')
        self.cv2 = cv2
        self.margin = margin
        self.hint = None  # last (kind, angle) that worked
        here = Path(__file__).parent
        data = getattr(getattr(cv2, "data", None), "haarcascades", "")

        def load(name):
            for p in (here / name, Path(data) / name):  # copy next to this script first
                if p.is_file():  # check first: OpenCV prints a scary ERROR for a missing path
                    c = cv2.CascadeClassifier(str(p))
                    if not c.empty():
                        return c
            return None

        self.frontal = load("haarcascade_frontalface_default.xml")
        self.profile = load("haarcascade_profileface.xml")
        if self.frontal is None:
            raise RuntimeError("Face model not found: keep haarcascade_frontalface_default.xml next to this script")
        if self.profile is None:
            print("note: haarcascade_profileface.xml not found, side views will not be searched")

    def _plan(self):
        plan = [("frontal", a) for a in ANGLES]
        if self.profile is not None:
            plan += [("profile", 0), ("profile-mirror", 0)]
        if self.hint in plan:
            plan.remove(self.hint)
            plan.insert(0, self.hint)
        return plan

    def _all(self, cascade, bgr, neighbors):
        """Every detection as (x, y, w, h) in the pixels of `bgr`, largest first."""
        cv2 = self.cv2
        h, w = bgr.shape[:2]
        s = 640.0 / max(h, w) if max(h, w) > 640 else 1.0  # detect on a smaller copy: faster
        small = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else bgr
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        m = max(24, int(min(gray.shape) * 0.05))  # smallest face: ~5% of the short side
        faces = cascade.detectMultiScale(gray, 1.1, neighbors, minSize=(m, m))
        boxes = [(x / s, y / s, fw / s, fh / s) for x, y, fw, fh in faces]
        return sorted(boxes, key=lambda b: -b[2] * b[3])

    def _largest(self, cascade, bgr, neighbors):
        """Largest detection as (x, y, w, h) in the pixels of `bgr`, or None."""
        boxes = self._all(cascade, bgr, neighbors)
        return boxes[0] if boxes else None

    def find_all(self, bgr, max_faces=6):
        """Every straight-ish face in the picture, largest first: [{"box", "crop"}, ...].
        Used for photos with a real face AND a face on a phone screen or a print."""
        out = []
        for x, y, fw, fh in self._all(self.frontal, bgr, 4)[:max_faces]:
            crop = square_crop(bgr, x + fw / 2, y + fh / 2, max(fw, fh) * (1 + 2 * self.margin))
            if crop is not None:
                out.append({"box": (int(x), int(y), int(fw), int(fh)), "crop": crop})
        return out

    def _rotate(self, bgr, angle):
        """Rotate by `angle` degrees on a bigger canvas (nothing cut off). Returns (image, 2x3 matrix)."""
        cv2 = self.cv2
        h, w = bgr.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        c, s = abs(M[0, 0]), abs(M[0, 1])
        nw, nh = int(h * s + w * c), int(h * c + w * s)
        M[0, 2] += nw / 2 - w / 2
        M[1, 2] += nh / 2 - h / 2
        return cv2.warpAffine(bgr, M, (nw, nh), borderValue=(0, 0, 0)), M

    def find(self, bgr):
        """Returns {"how", "asis", "upright"} or None. asis = crop from the original image
        (still tilted), upright = crop from the rotated copy (face turned upright)."""
        w = bgr.shape[1]
        for kind, ang in self._plan():
            if kind == "frontal":
                img, M = (bgr, None) if ang == 0 else self._rotate(bgr, ang)
                box = self._largest(self.frontal, img, 5 if ang == 0 else 7)
                if box is None:
                    continue
                x, y, fw, fh = box
                cx, cy, side = x + fw / 2, y + fh / 2, max(fw, fh) * (1 + 2 * self.margin)
                upright = square_crop(img, cx, cy, side)
                ox, oy = (cx, cy) if M is None else self.cv2.invertAffineTransform(M) @ np.array([cx, cy, 1.0])
                asis = square_crop(bgr, ox, oy, side)
                how = "frontal" if ang == 0 else f"frontal, tilt {ang:+d} deg"
            else:  # profile, from the left or (mirrored) from the right
                mirror = kind == "profile-mirror"
                src = np.ascontiguousarray(bgr[:, ::-1]) if mirror else bgr
                box = self._largest(self.profile, src, 7)
                if box is None:
                    continue
                x, y, fw, fh = box
                cx, cy, side = x + fw / 2, y + fh / 2, max(fw, fh) * (1 + 2 * self.margin)
                if mirror:
                    cx = w - cx
                asis = upright = square_crop(bgr, cx, cy, side)
                how = "side view"
            if asis is None or upright is None:
                continue
            self.hint = (kind, ang)
            return {"how": how, "asis": asis, "upright": upright}
        return None


def save_crop(img, folder, name):
    Image.fromarray(np.ascontiguousarray(img[..., ::-1])).save(Path(folder) / f"{name}.jpg")


def fmt(r):
    return f"live={r['live']!s:<5} score={r['score']:.4f}"


def run_image(f, name, finder, check, a, tally):
    try:
        bgr = load_bgr(f)
    except Exception as e:  # unreadable file
        print(f"{name:<42} SKIPPED ({e})")
        return
    tally["images"] += 1
    if a.no_crop:
        hit = {"how": "as given", "asis": bgr, "upright": bgr}
    else:
        hit = finder.find(bgr)
        if hit is None:
            print(f"{name:<42} NO FACE FOUND")
            return
    tally["found"] += 1
    r = check([hit["asis"]] * WINDOW)
    tally["live"] += bool(r["live"])
    line = f"{name:<42} {hit['how']:<20} as-is: {fmt(r)}"
    if hit["upright"].shape != hit["asis"].shape or not np.array_equal(hit["upright"], hit["asis"]):
        up = check([hit["upright"]] * WINDOW)
        line += f" | upright: {fmt(up)}"
    print(line)
    if a.save_crops:
        save_crop(hit["asis"], a.save_crops, f.stem)
        if "tilt" in hit["how"]:
            save_crop(hit["upright"], a.save_crops, f.stem + "_upright")


def run_image_all(f, name, finder, check, a, tally):
    """--all-faces: judge EVERY face in the photo on its own line (largest first)."""
    try:
        bgr = load_bgr(f)
    except Exception as e:  # unreadable file
        print(f"{name:<42} SKIPPED ({e})")
        return
    tally["images"] += 1
    faces = finder.find_all(bgr)
    if not faces:
        print(f"{name:<42} NO FACE FOUND")
        return
    tally["found"] += 1
    for k, face in enumerate(faces, 1):
        x, y, w, h = face["box"]
        r = check([face["crop"]] * WINDOW)
        print(f"{name:<42} face {k}/{len(faces)} {w}x{h}px at ({x},{y})  {fmt(r)}")
        if a.save_crops:
            save_crop(face["crop"], a.save_crops, f"{f.stem}_face{k}")


def run_video(f, name, finder, check, a, tally):
    import cv2

    cap = cv2.VideoCapture(str(f))
    if not cap.isOpened():
        print(f"{name:<42} VIDEO CANNOT BE OPENED")
        return
    crops, hows, sampled, i = [], [], 0, 0
    while sampled < a.max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if i % a.every == 0:
            sampled += 1
            hit = finder.find(frame) if not a.no_crop else {"how": "as given", "asis": frame}
            if hit:
                crops.append(hit["asis"])
                hows.append(hit["how"])
        i += 1
    cap.release()
    tally["videos"] += 1
    if sampled == 0:
        print(f"{name:<42} NO FRAMES READ (codec problem?)")
        return
    found = len(crops)
    tally["frames"] += sampled
    tally["frames_found"] += found
    head = f"{name:<42} frames {sampled}, face found {found} ({100 * found // sampled}%)"
    if not found:
        print(head + " -> NO FACE")
        return
    starts = list(range(0, max(1, found - WINDOW + 1), 5))
    res = [check(crops[s : s + WINDOW]) for s in starts]
    n_live = sum(bool(r["live"]) for r in res)
    scores = [r["score"] for r in res]
    tally["windows"] += len(res)
    tally["windows_live"] += n_live
    how_count = {}
    for h in hows:
        how_count[h] = how_count.get(h, 0) + 1
    print(f"{head} | windows live {n_live}/{len(res)} | score mean {np.mean(scores):.3f} min {min(scores):.3f}")
    print("    found by: " + ", ".join(f"{k} x{v}" for k, v in sorted(how_count.items(), key=lambda kv: -kv[1])))
    if a.save_crops:
        for j in np.linspace(0, found - 1, num=min(6, found), dtype=int):
            save_crop(crops[j], a.save_crops, f"{f.stem}_f{j:03d}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="image/video files and/or folders")
    ap.add_argument("--crop", action="store_true", help="(default, kept for old commands)")
    ap.add_argument("--no-crop", action="store_true", help="files are already face crops: skip the face search")
    ap.add_argument("--all-faces", action="store_true", help="photos: judge every face found, not only the largest")
    ap.add_argument("--save-crops", metavar="DIR", help="save the crops fed to the model")
    ap.add_argument("--every", type=int, default=8, help="video: use every N-th frame (default 8)")
    ap.add_argument("--max-frames", type=int, default=100, help="video: sample at most N frames (default 100)")
    a = ap.parse_args()

    files = collect(a.paths)
    if not files:
        raise SystemExit("Nothing found. Images: " + ", ".join(sorted(IMG_EXT)) + " Videos: " + ", ".join(sorted(VID_EXT)))
    if any(f.suffix.lower() in {".heic", ".heif"} for f in files) and not HEIF_OK:
        raise SystemExit("HEIC photos found but pillow-heif is missing. Run: pip install pillow-heif")
    if a.save_crops:
        Path(a.save_crops).mkdir(parents=True, exist_ok=True)

    from app.pipeline.liveness import _weights_path, check

    finder = None if a.no_crop else FaceFinder()
    print("weights:", _weights_path())
    tally = dict(images=0, found=0, live=0, videos=0, frames=0, frames_found=0, windows=0, windows_live=0)
    for f in files:
        name = f"{f.parent.name}/{f.name}"[-42:]
        if f.suffix.lower() in VID_EXT:
            run_video(f, name, finder, check, a, tally)
        elif a.all_faces and not a.no_crop:
            run_image_all(f, name, finder, check, a, tally)
        else:
            run_image(f, name, finder, check, a, tally)

    print("-" * 60)
    if tally["images"] and a.all_faces:
        print(f"images: at least one face found in {tally['found']}/{tally['images']}")
    elif tally["images"]:
        print(f"images: face found {tally['found']}/{tally['images']}, judged live {tally['live']}/{tally['found']}")
    if tally["videos"]:
        print(
            f"videos: {tally['videos']} files, face found in {tally['frames_found']}/{tally['frames']} sampled frames, "
            f"windows judged live {tally['windows_live']}/{tally['windows']}"
        )
    print("Real people should be live=True. 'NO FACE FOUND' is a detector miss, not a liveness verdict.")


if __name__ == "__main__":
    main()