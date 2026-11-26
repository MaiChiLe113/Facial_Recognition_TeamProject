"""Synthetic face damage for the face-quality training set (Đức Mạnh).

Used by 01_build_labels.ipynb (training data) and 03_evaluate.ipynb (checks). Every function takes a BGR uint8 face
crop and a level in [0, 1] (0 = untouched, 1 = strongest) and returns a crop of the same size.

    damage(img, kind, level, rng)    kind is one of DAMAGES
"""
import cv2
import numpy as np


def _blur(img, t, rng):
    s = 0.3 + 3.2 * t * img.shape[0] / 64
    return cv2.GaussianBlur(img, (0, 0), s)


def _motion(img, t, rng):
    n = max(3, int(round(3 + 14 * t * img.shape[0] / 64)) | 1)
    k = np.zeros((n, n), np.float32)
    k[n // 2] = 1
    rot = cv2.getRotationMatrix2D((n / 2 - 0.5, n / 2 - 0.5), float(rng.uniform(0, 180)), 1)
    k = cv2.warpAffine(k, rot, (n, n))
    return cv2.filter2D(img, -1, k / max(k.sum(), 1e-6))


def _noise(img, t, rng):
    return np.clip(img + rng.normal(0, 4 + 46 * t, img.shape), 0, 255).astype(np.uint8)


def _jpeg(img, t, rng):
    q = int(round(60 - 55 * t))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _downscale(img, t, rng):
    h, w = img.shape[:2]
    f = 1 - 0.85 * t
    small = cv2.resize(img, (max(4, int(w * f)), max(4, int(h * f))), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _gamma(img, g):
    lut = np.clip(((np.arange(256) / 255.0) ** g) * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def _dark(img, t, rng):
    return np.clip(_gamma(img, 1 + 3 * t) * (1 - 0.6 * t), 0, 255).astype(np.uint8)


def _bright(img, t, rng):
    return np.clip(_gamma(img, 1 / (1 + 3 * t)).astype(np.float32) + 120 * t, 0, 255).astype(np.uint8)


def _occlusion(img, t, rng):
    h, w = img.shape[:2]
    out = img.copy()
    area = 0.05 + 0.4 * t
    bh = int(h * np.sqrt(area) * rng.uniform(0.7, 1.3))
    bw = int(min(w, h * w * area / max(bh, 1)))
    y, x = int(rng.uniform(0, h - bh)), int(rng.uniform(0, w - bw))
    out[y:y + bh, x:x + bw] = rng.integers(0, 256, 3) if rng.random() < 0.5 else 0
    return out


def _pose(img, t, rng):
    """Squeeze one side of the face (a cheap stand-in for head yaw) plus a small roll."""
    h, w = img.shape[:2]
    s = 0.45 * t * w
    side = rng.choice((-1, 1))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    if side > 0:
        dst = np.float32([[0, 0], [w - s, s * 0.5], [w - s, h - s * 0.5], [0, h]])
    else:
        dst = np.float32([[s, s * 0.5], [w, 0], [w, h], [s, h - s * 0.5]])
    out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REPLICATE)
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-25, 25) * t), 1)
    return cv2.warpAffine(out, rot, (w, h), borderMode=cv2.BORDER_REPLICATE)


DAMAGES = {"blur": _blur, "motion": _motion, "noise": _noise, "jpeg": _jpeg, "downscale": _downscale,
           "dark": _dark, "bright": _bright, "occlusion": _occlusion, "pose": _pose}


def damage(img, kind, level, rng=None):
    rng = np.random.default_rng() if rng is None else rng
    return DAMAGES[kind](img, float(np.clip(level, 0, 1)), rng)
