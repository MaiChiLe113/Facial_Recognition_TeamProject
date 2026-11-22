"""Try ml/anti_spoofing/infer.py (the runtime liveness check) on face images.

Run from the repo root:

    python ml/anti_spoofing/try_liveness.py test_faces
    python ml/anti_spoofing/try_liveness.py test_faces --crop --save-crops test_crops
    python ml/anti_spoofing/try_liveness.py a.jpg b.heic

--crop         find the largest face with OpenCV and cut it out first. Use this for
               normal photos (whole head and shoulders), because the model was trained
               on face CROPS. Skip it if your images are already tight face crops.
--save-crops   also save the crops it feeds the model, so you can look at them.

iPhone .HEIC photos work if `pip install pillow-heif` is done. The same image is
repeated 10 times to imitate the ~10 recent frames that check() receives.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

EXT = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp", ".heic", ".heif"}

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
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in EXT) if p.is_dir() else [p]
    return files


def load_bgr(path):
    """Open an image, apply the phone's rotation flag, return HxWx3 uint8 in BGR order."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.ascontiguousarray(np.asarray(img)[..., ::-1])


def crop_face(bgr, margin=0.25):
    """Largest frontal face (OpenCV Haar cascade) plus a margin, or None if no face found."""
    import cv2

    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5.x dropped it from the main package
        raise RuntimeError('This OpenCV has no face detector. Run: pip install "opencv-python<5"')
    h, w = bgr.shape[:2]
    scale = 800.0 / max(h, w) if max(h, w) > 800 else 1.0  # detect on a smaller copy: faster
    small = cv2.resize(bgr, None, fx=scale, fy=scale) if scale < 1 else bgr
    # Prefer the copy bundled next to this script (newer OpenCV wheels may not ship the file).
    local = Path(__file__).with_name("haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(str(local))
    if cascade.empty():
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        raise RuntimeError("Face model not found: keep haarcascade_frontalface_default.xml next to this script")
    faces = cascade.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, fw, fh = [v / scale for v in max(faces, key=lambda f: f[2] * f[3])]
    x0, y0 = int(max(0, x - fw * margin)), int(max(0, y - fh * margin))
    x1, y1 = int(min(w, x + fw * (1 + margin))), int(min(h, y + fh * (1 + margin)))
    return bgr[y0:y1, x0:x1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="image files and/or folders")
    ap.add_argument("--crop", action="store_true", help="detect and cut out the face first")
    ap.add_argument("--save-crops", metavar="DIR", help="save the images fed to the model")
    a = ap.parse_args()

    files = collect(a.paths)
    if not files:
        raise SystemExit("No images found (sub-folders included). Supported: " + ", ".join(sorted(EXT)))
    if any(f.suffix.lower() in {".heic", ".heif"} for f in files) and not HEIF_OK:
        raise SystemExit("HEIC photos found but pillow-heif is missing. Run: pip install pillow-heif")
    if a.save_crops:
        Path(a.save_crops).mkdir(parents=True, exist_ok=True)

    from infer import _weights_path, check

    print("weights:", _weights_path())
    for f in files:
        name = f"{f.parent.name}/{f.name}"[-45:]
        try:
            bgr = load_bgr(f)
        except Exception as e:  # unreadable file
            print(f"{name:<45} SKIPPED ({e})")
            continue
        if a.crop:
            bgr = crop_face(bgr)
            if bgr is None:
                print(f"{name:<45} no face found, skipped")
                continue
        if a.save_crops:
            Image.fromarray(np.ascontiguousarray(bgr[..., ::-1])).save(Path(a.save_crops) / (f.stem + ".jpg"))
        r = check([bgr] * 10)
        print(f"{name:<45} {bgr.shape[1]}x{bgr.shape[0]}  live={r['live']!s:<5} score={r['score']:.4f}")


if __name__ == "__main__":
    main()