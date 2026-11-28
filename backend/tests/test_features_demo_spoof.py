"""The Features demo must not name a face that anti-spoofing rejected."""
import numpy as np

from app.services import features_demo as demo


class Live:
    def check(self, crops):
        score = float(np.mean([c.mean() for c in crops])) / 255
        return {"live": score >= 0.5, "score": score}


class Recognizer:
    def threshold(self):
        return 0.7


def run(monkeypatch, brightness):
    image = np.full((100, 100, 3), brightness, np.uint8)
    monkeypatch.setattr(demo, "_find_faces", lambda img: [(20, 20, 40, 40)])
    monkeypatch.setattr(demo, "load_infer", lambda f: Live() if f == "anti_spoofing" else Recognizer())
    monkeypatch.setattr(demo, "_default_threshold", lambda f: 0.5)
    monkeypatch.setattr(demo.gallery, "load_registered", lambda: None)
    monkeypatch.setattr(demo.gallery, "is_loading", lambda: False)
    monkeypatch.setattr(demo.gallery, "registered_profiles", lambda: (({"s1": [1]}, None), {"s1": "Le Mai Chi"}))
    monkeypatch.setattr(demo.gallery, "identify_face", lambda *a, **k: ("s1", 0.9, 0.7))
    return demo.analyze(image, ["anti_spoofing", "face_recognition"], client="t")["faces"][0]


def test_spoof_is_not_identified(monkeypatch):
    face = run(monkeypatch, 10)
    assert face["live"] is False
    assert face["name"] is None and face["recognition_skipped"] == "spoof"


def test_live_face_is_identified(monkeypatch):
    face = run(monkeypatch, 250)
    assert face["live"] is True and face["name"] == "Le Mai Chi"


class Emotion:
    def reset(self):
        pass

    def predict(self, crop):
        return {"label": "sad", "score": 0.8}


def test_spoof_has_no_emotion(monkeypatch):
    image = np.full((100, 100, 3), 10, np.uint8)
    monkeypatch.setattr(demo, "_find_faces", lambda img: [(20, 20, 40, 40)])
    monkeypatch.setattr(demo, "load_infer", lambda f: Live() if f == "anti_spoofing" else Emotion())
    monkeypatch.setattr(demo, "_default_threshold", lambda f: 0.5)
    face = demo.analyze(image, ["anti_spoofing", "emotion"], client="t2")["faces"][0]
    assert face["live"] is False and "emotion" not in face
