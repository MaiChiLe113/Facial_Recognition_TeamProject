"""Person and face detection.  Owner: Mai Chi

Ask the tutor first: may these detectors stay pre-trained? They only find
people/faces, they do not decide identity.
"""


def detect_people(frame):
    """Return [(x, y, w, h, score), ...] in pixels for every person in the frame.

    TODO: YOLOv8n (ultralytics), keep class 0 (person) only.
    """
    raise NotImplementedError


def detect_faces(frame):
    """Return [(x, y, w, h, score), ...] for every face (attendance cam only).

    TODO: RetinaFace / MTCNN / YOLOv8-face.
    """
    raise NotImplementedError
