# Face recognition — Owner: Thuận Minh

- [ ] Download the Kaggle dataset into `data/raw/` (git-ignored)
- [ ] `train_classification.py` — ResNet-18 → 512-d → softmax, cross-entropy
- [ ] `train_triplet.py` — same backbone, triplet loss, semi-hard mining
- [ ] `evaluate.py` — ROC/AUC on `verification_pairs_val.txt`, cosine vs Euclidean, pick threshold
- [ ] Export the chosen model for `backend/app/pipeline/recognizer.py`

Results: _TBC_
