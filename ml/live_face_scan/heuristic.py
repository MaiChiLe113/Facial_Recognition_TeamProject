"""Hand-made face-quality baseline (no learning), the comparison for the trained model in 03_evaluate.ipynb.
Also the fallback score in the backend when live_face_scan.pt is missing.

    heuristic_score(face_crop, face_px=None, yaw=0, pitch=0) -> float in [0, 1]

Product of four terms in [0, 1]:
  sharpness  variance of the Laplacian on a 112 px grey copy (log scale; blurry ~ 0, sharp ~ 1)
  exposure   mean brightness inside 70..190 and contrast (std) above 25 score 1, falling off outside
  size       face height in pixels in the original frame (>= 112 px = 1); skipped when face_px is None
  pose       1 for a frontal face, falling to 0 at |yaw| 60 deg / |pitch| 45 deg
"""
import cv2
import numpy as np


def sharpness(grey):
    v = cv2.Laplacian(grey, cv2.CV_64F).var()
    return float(np.clip((np.log10(v + 1) - 1.0) / 1.6, 0, 1))      # var 10 -> 0, ~400 -> 1


def exposure(grey):
    m, s = float(grey.mean()), float(grey.std())
    lo, hi = np.clip((m - 30) / 40, 0, 1), np.clip((230 - m) / 40, 0, 1)
    return float(min(lo, hi) * np.clip(s / 25, 0, 1))


def size_term(face_px):
    return 1.0 if face_px is None else float(np.clip((face_px - 32) / 80, 0, 1))


def pose_term(yaw, pitch):
    return float(np.clip(1 - abs(yaw) / 60, 0, 1) * np.clip(1 - abs(pitch) / 45, 0, 1))


def heuristic_score(face_crop, face_px=None, yaw=0.0, pitch=0.0):
    grey = cv2.cvtColor(cv2.resize(face_crop, (112, 112), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return sharpness(grey) * exposure(grey) * size_term(face_px) * pose_term(yaw, pitch)
