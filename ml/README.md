# ML training code

One folder per model. Train on Colab/Kaggle GPUs; save weights to Drive (not git) and note the path + metrics in that folder's README.

| Folder | Owner | Model | Data | Report numbers |
| --- | --- | --- | --- | --- |
| `face_recognition/` | Thuận Minh | ResNet-18 embedding: (A) softmax classification, (B) triplet loss. Compare cosine vs Euclidean | Kaggle `classification_data`, `verification_pairs_val.txt` | Accuracy, ROC/AUC per model × metric, chosen threshold |
| `anti_spoofing/` | Hồng Minh | MobileNetV2 live vs spoof | CelebA-Spoof subset / LCC-FASD + our own print & phone spoofs | Accuracy, APCER/BPCER, AUC |
| `emotion/` | Minh Thành | ResNet-18 or small CNN, 7 classes | FER2013 / RAF-DB | Accuracy, macro-F1, confusion matrix |
| `tracking/` | Mai Chi | YOLOv8n + ByteTrack, cross-camera matching | Our 9 recorded takes | ID switches, in/out time error vs ground truth |

Rule from the brief: no fully pre-trained model without further training. Partial fine-tuning is allowed.

`aruco/` (Đức Mạnh) is not a model: it is the floor calibration of `cam_1` / `cam_2` from ArUco markers (see its README).
