"""Anti-spoofing (liveness).  Owner: Hồng Minh

Training code: ml/anti_spoofing/. Must be our own trained / fine-tuned model.
"""


def check(face_crops):
    """Given ~10 recent crops of one face, return {"live": bool, "score": float}.

    TODO: load the trained MobileNetV2 live/spoof classifier, average the score over frames.
    """
    raise NotImplementedError
