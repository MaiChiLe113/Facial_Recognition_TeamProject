"""Binary eyeglasses classification on a YuNet face crop (OpenCV BGR)."""
import os
import threading
from pathlib import Path

_DEFAULT_WEIGHTS = Path(__file__).resolve().with_name("glasses_detection.pt")
_lock = threading.Lock()
_state = {}


def _load():
    if _state:
        return _state
    with _lock:
        if _state:
            return _state

        import torch
        from torch import nn
        from torchvision.models import mobilenet_v3_small

        override = os.environ.get("HAWKEYE_GLASSES_DETECTION_WEIGHTS")
        path = Path(override).expanduser() if override else _DEFAULT_WEIGHTS
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if payload.get("architecture") != "mobilenet_v3_small":
            raise ValueError("Expected a MobileNetV3 Small glasses export")
        threshold = float(payload["threshold"])
        if not 0 <= threshold <= 1:
            raise ValueError("Expected a glasses threshold between zero and one")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = mobilenet_v3_small(weights=None)
        model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, 2)
        model.load_state_dict(payload["state_dict"])
        _state.update(
            model=model.to(device).eval(),
            device=device,
            size=int(payload["input_size"]),
            mean=torch.tensor(payload["mean"], device=device).view(1, 3, 1, 1),
            std=torch.tensor(payload["std"], device=device).view(1, 3, 1, 1),
            threshold=threshold,
        )
        return _state


def predict(face_crop):
    """Return the eyeglasses decision and the positive-class score."""
    import cv2
    import torch

    state = _load()
    size = state["size"]
    resized = cv2.resize(face_crop, (size, size), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    image = torch.as_tensor(rgb, device=state["device"]).permute(2, 0, 1).unsqueeze(0) / 255
    with torch.inference_mode():
        logits = state["model"]((image - state["mean"]) / state["std"])
        score = float(logits.softmax(dim=1)[0, 1].item())
    return {"glasses": score >= state["threshold"], "glasses_score": score}
