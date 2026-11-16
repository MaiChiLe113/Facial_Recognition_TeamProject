"""Emotion recognition.  Owner: Minh Thành

Training code: ml/emotion/ (FER2013 or RAF-DB, 7 classes).
"""

CLASSES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]


def predict(face_crop):
    """Return {"label": str, "score": float}. TODO: load the trained model, smooth over a few frames."""
    raise NotImplementedError
