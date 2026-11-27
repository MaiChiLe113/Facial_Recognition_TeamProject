"""Face mask detection for the Add person face scan (no trained weights: a colour heuristic on YuNet landmarks).

A mask covers the nose tip, mouth and chin, so the lower face stops looking like the person's own skin. The check
compares two patches placed from the 5 YuNet landmarks (right eye, left eye, nose, right mouth corner, left mouth
corner):

    upper patch: the forehead just above the eyes (never covered by a mask)
    lower patch: between the mouth corners, from below the nose to the chin

Both patches go to YCrCb, and the score mixes
    - the chroma distance between the patches' median (Cr, Cb), scaled by CHROMA_FULL, and
    - how much less "skin like" the lower patch is than the upper one (pixels within SKIN_TOL of the upper median).
score is 0..1 (higher = more likely a mask); mask = score >= THRESHOLD.

Limits (to be measured on team scans, logs/enrol_frames.jsonl "mask_score"): a mask close to the person's skin colour
can pass, and a beard or a strong shadow on the lower face raises the score. Replace with a trained classifier
(ml/mask_detection/mask_detection.pt) if the logged scores of masked and bare scans overlap.

    check(image, marks) -> {"mask": bool, "score": float} or {"mask": None, "score": None} when a patch is unusable
"""
import numpy as np

THRESHOLD = 0.5
CHROMA_FULL = 18.0      # (Cr, Cb) distance that counts as a full colour change
SKIN_TOL = 10.0         # a lower-patch pixel is "skin" within this (Cr, Cb) distance of the upper median
MIN_PATCH_PX = 40       # fewer pixels than this in a patch: no decision


def _patch(ycc, x0, y0, x1, y1):
    h, w = ycc.shape[:2]
    x0, x1 = max(0, int(round(min(x0, x1)))), min(w, int(round(max(x0, x1))))
    y0, y1 = max(0, int(round(min(y0, y1)))), min(h, int(round(max(y0, y1))))
    p = ycc[y0:y1, x0:x1, 1:3].reshape(-1, 2).astype(np.float32)
    return p if len(p) >= MIN_PATCH_PX else None


def patches(image, marks):
    """The (upper, lower) (Cr, Cb) pixel arrays, or None for a patch outside the image / too small."""
    import cv2

    (rex, rey), (lex, ley), (nx, ny), (rmx, rmy), (lmx, lmy) = [tuple(map(float, m)) for m in marks[:5]]
    eye_y, eye_d = (rey + ley) / 2, max(1.0, abs(lex - rex))
    ex, mx, my = (rex + lex) / 2, (rmx + lmx) / 2, (rmy + lmy) / 2
    ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    upper = _patch(ycc, ex - 0.35 * eye_d, eye_y - 0.55 * eye_d, ex + 0.35 * eye_d, eye_y - 0.2 * eye_d)
    half = max(abs(lmx - rmx) / 2, 0.25 * eye_d)
    lower = _patch(ycc, mx - half, ny + 0.15 * (my - ny), mx + half, my + 0.45 * eye_d)
    return upper, lower


def check(image, marks):
    upper, lower = patches(image, marks)
    if upper is None or lower is None:
        return {"mask": None, "score": None}
    ref = np.median(upper, axis=0)
    chroma = float(np.linalg.norm(np.median(lower, axis=0) - ref))
    skin_lower = float(np.mean(np.linalg.norm(lower - ref, axis=1) <= SKIN_TOL))
    skin_upper = float(np.mean(np.linalg.norm(upper - ref, axis=1) <= SKIN_TOL)) or 1.0
    covered = max(0.0, 1.0 - skin_lower / skin_upper)
    score = 0.5 * min(1.0, chroma / CHROMA_FULL) + 0.5 * covered
    return {"mask": score >= THRESHOLD, "score": round(score, 4)}
