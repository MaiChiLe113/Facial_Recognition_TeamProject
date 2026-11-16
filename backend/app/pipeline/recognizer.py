"""Face verification against the registered students.  Owner: Thuận Minh

Training code: ml/face_recognition/ (classification + triplet, cosine vs Euclidean, ROC/AUC).
"""


def embed(face_crop):
    """Return an L2-normalised 512-d embedding. TODO: load the chosen model."""
    raise NotImplementedError


def identify(face_crop, gallery, threshold):
    """gallery: {student_id: [embeddings]}. Return (student_id or None, similarity).

    TODO: cosine similarity to every gallery embedding, best match above the ROC threshold.
    """
    raise NotImplementedError
