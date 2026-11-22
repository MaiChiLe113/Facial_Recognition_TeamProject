# Assignment brief (COS30082) — full text, nothing cut

> Source: `Facial Recognition with Emotion and Liveness.pdf` (repo root, 6 pages). This file is a complete transcription of the PDF text, in the original order and wording. It is the **official requirements and marking scheme**. If anything elsewhere in `.agents/` conflicts with this file, this file wins. Do not summarise or trim it.
>
> Transcription notes (not part of the original):
> - The PDF has three figures (Fig. 1, Fig. 2 and a face-embedding diagram) that are images and could not be extracted. Their captions are kept below.
> - In the marking table the PDF layout is garbled in text extraction. See the note under section 12 for exactly what could and could not be recovered.

---

# COS30082 Applied Machine Learning

# Project: Facial Recognition with Emotion & Liveness

## 1 Introduction

Face recognition can be classified into two categories: face classification and face verification. Face classification involves assigning a person's face to the correct face ID, while face verification involves determining whether two face images belong to the same person. Face classification is considered a closed-set problem, where the face IDs are known in advance by the model. In contrast, face verification is an open-set problem, where the model may encounter previously unseen face identities.

In this project, you will implement face verification using a convolutional neural network (CNN) to design an end-to-end face recognition attendance system for an enterprise. You must consider the following scenarios:

- Registering a new face ID when hiring new employees.
- Integrating an anti-spoofing module into your attendance system.
- Integrating an emotion detection module into your attendance system.

Although mature products for face recognition exist, this project focuses on applying machine learning techniques. Instead of using existing tools, you will build your own face recognition system. This hands-on approach allows us to better understand the core principles behind face verification.

In this project, the use of fully pre-trained models without further training is not permitted. However, transfer learning with partial fine-tuning is allowed.

## 2. Face Recognition

The input to your system will be a pair of face images (referred to as a "trial"). Your goal is to produce a numerical score that quantifies the similarity between the faces in the two images. A simple approach is to flatten each image into a vector and then calculate the Euclidean distance between the two vectors, as shown in Fig. 1. A smaller distance indicates greater confidence that the faces in the two images belong to the same person.

*Fig. 1: The concept of face verification* (figure, image only)

In this project, you will explore the following elements to design a face recognition attendance system.

### 2.1 Face Embedding

*Fig 2: Face embedding similarity comparison* (figure, image only)

You are not encouraged to directly compute the distance between two image matrices for two main reasons:

- Flattened images are usually high-dimensional, leading to increased computational costs.
- The features in the original images are not sufficiently discriminative.

Therefore, in this project, your task is to train a convolutional neural network (CNN) to extract compact, low-dimensional features that retain the most important information from the image while remaining discriminative. These compact features will be represented as fixed-length vectors, known as face embeddings. Your end-to-end face verification system will function as follows: Given two images, each image is passed through the CNN to generate its corresponding face embedding. A similarity metric is then applied to the embeddings to produce a similarity score. The end-to-end face verification framework is illustrated in Fig. 2.

There are different approaches to training a convolutional neural network (CNN) to extract discriminative face embeddings. Two common methods are as follows:

- **Metric Learning (Self-Supervised):** Metric learning trains a CNN to map face images into an embedding space where similar faces are close together and different faces are far apart. For example, in the triplet loss method, an image called the anchor is compared to a positive sample (same identity) and a negative sample (different identity). The model learns to minimize the distance between the anchor and the positive, while maximizing the distance between the anchor and the negative.
- **Supervised Learning (Classification-Based):** Supervised learning treats face recognition as a classification problem, training the CNN to assign each image to a known identity class. A softmax layer is used during training, and once the model learns to classify correctly, the representation from the layer before the softmax is used as the face embedding.

In this project, you are expected to implement both approaches and compare their performance.

### 2.2 System Evaluation for Face Verification

The Receiver Operating Characteristic (ROC) curve and Area Under the Curve (AUC) will be used as evaluation metrics to assess model performance.

A threshold is used to decide whether to accept or reject a pair -- that is, a pair is accepted if the similarity score is above the threshold and rejected if it is below. The ROC curve plots the true positive rate (TPR) against the false positive rate (FPR).

The AUC of the ROC curve represents the probability that the classifier will rank a randomly chosen positive pair (same person) higher than a randomly chosen negative pair (different people), based on their similarity scores.

### 2.3 Similarity Distance Metric

You are required to conduct research to select an appropriate distance metric for the face verification task. The two most commonly used distance metrics are cosine similarity and Euclidean distance. Both metrics are capable of achieving state-of-the-art performance. You are encouraged to test and compare both metrics.

## 3. Anti-Spoofing Module

Facial recognition systems are vulnerable to being deceived by spoofed or non-real faces, such as printed photos or images displayed on mobile phones. To enhance the security of these systems, you are required to develop effective methods to detect such counterfeit faces. This process is commonly referred to as liveness detection.

The anti-spoofing process must be seamlessly integrated with the existing facial recognition system. You are required to train your own model.

## 4. Emotion Detection Module

To enhance functionality, you are required to implement an emotion detection module. This module should identify a user's emotional state from facial expressions in real time. The detected emotion can be displayed as icons accompanied by emotion labels. This will enhance user interaction and provide additional insights for enterprise applications, such as workplace sentiment analysis or mental health monitoring.

The use of fully pre-trained models without further training is not permitted. You are required to train your own model using publicly available datasets. The emotion detection process must be seamlessly integrated with the existing facial recognition system.

## 5. Dataset

The dataset used in this project is sourced from Kaggle. The folder structure is as follows:

- `classification_data/` This folder contains three subfolders: `train_data`, `val_data`, and `test_data`. Each subfolder contains images of a single person. The folder name is their ID.
  - `train_data`: Used for training both classification and metric learning models.
  - `val_data`: Used to validate classification accuracy. Not needed for metric learning.
  - `test_data`: Used to test classification accuracy. Also not used for metric learning.
- `verification_data/` This folder contains images used for face verification tasks.
- `verification_pairs_val.txt` This file contains verification trials.
  - The first two columns are image paths.
  - The third column is the label: 1 for the same person, 0 for different people. Your AUC score for face verification should be computed based on this file.

You may use additional data sources to enrich your dataset.

## 6. User Interface

The system uses a webcam to capture a person's face in real time. When a person appears in front of the camera, the system should automatically perform face recognition. If the person has already been registered, their identity (name) should be displayed. If the person is not recognised, the system should prompt for registration and allow a new identity to be added.

At the same time, the system should perform liveness detection (anti-spoofing) and emotion recognition. The detected identity (if available), emotion, and liveness status should be displayed immediately.

You may choose to implement a graphical user interface (GUI) to allow users to interact with the system, including registration and real-time feedback display.

## 7. Individual Innovative Feature

Every student is encouraged to implement one innovative feature. The feature must be relevant to the class attendance facial recognition system and should significantly enhance the system. The feature must be clearly demonstrated in the video and explained in the individual report.

## 8. Project Report (group report, no more than 12 pages)

The report should include at least the following sections: Methodology, Results, and Discussion. It must provide a detailed description of the overall system framework, including the components for face verification, anti-spoofing, and emotion detection. Each model should be described comprehensively, including the training scheme, loss function, hyperparameters, and other relevant details. The report should also compare the performance of different models and justify the selection of the best-performing approach based on the evaluation results.

## 9. Demonstration Video

Each group is required to submit a 5–10-minute video demonstrating all functions of the project. Each member should contribute a similar amount of presentation time. When a member is speaking, their face must be clearly visible on camera. The demonstration must be recorded in a single continuous take (no cuts, edits, or post-production).

Please host your video on a suitable platform (e.g., YouTube, OneDrive) and submit only the video link via Canvas. Ensure that the video is accessible to others.

## 10. Individual Report (no more than 5 pages)

Each student is required to submit an individual report outlining their contributions, key methods used, and challenges encountered and resolved. If applicable, the report should also include a description of the innovative feature, including the rationale for its inclusion, the model or method used, how the model was built and trained.

## 11. Submission

Please submit the following via Canvas by the specified due date:

- Source code (to be submitted by one group member)
- Group report (to be submitted by the same member)
- Demonstration video link (to be submitted by the same member)
- Individual report (to be submitted by each member)
- Peer evaluation form (to be submitted by each member)

## 12. Marking Scheme

Marks are based on the implementation of key components and the students' understanding of the required knowledge and techniques.

| Assessment Criteria | Mark |
| --- | --- |
| **Group Work** | |
| 1) **Face Recognition** — Assessment of the implementation of the two baseline approaches: classification and metric learning for face verification, as well as any additional approaches used. | 5 |
| 2) **Anti-Spoofing** — Assessment of the design and effectiveness of the liveness detection module for identifying spoofed faces (e.g., printed images or screen photos). | 5 |
| 3) **Emotion Detection** — Assessment of the integration and performance of the emotion recognition module in identifying emotional states (e.g., happy, sad, angry) and displaying them appropriately within the user interface. | 5 |
| 4) **User Interface** — Evaluation of the usability, functionality, and completeness of the graphical user interface (GUI), including features for registration, verification, liveness detection, and emotion display. | 5 (see note) |
| 5) **Project Report** — Evaluation of the clarity and completeness of the project report, focusing on how well the Methodology and Results and Discussion sections are presented. Marks will be awarded based on the quality of explanation, organization, and justification of key design decisions. | 5 |
| **Individual work** | |
| 1) **Innovation** — Assessment of innovation and any features that extend beyond the basic requirements. | 10 (see note) |
| 2) **Individual Report** — Evaluation of the clarity of individual contributions and explanation of the key techniques used. | 10 (see note) |
| 3) **Interview** — During the Week 12 tutorial, the tutor will interview you mainly about your project and the methods used in its implementation. | 10 (see note) |
| **Total** | **40** |

Your group mark (system and project report) will be adjusted based on peer evaluation. Your final overall mark may also be adjusted according to your interview performance.

> **Transcription note on the marks column (not part of the original).** In the PDF the numbers are laid out in merged/floating cells, so text extraction does not tie every number to a single row. What the extraction shows: a `5` after each of Face Recognition, Anti-Spoofing, Emotion Detection and Project Report; no number printed directly beside User Interface (likely the merged cell, probably 5); a `10` after Individual Report; a `10` after Interview; no number beside Innovation; Total `40`. The per-row marks above for User Interface, Innovation, Individual Report and Interview are therefore **not certain**, and the printed numbers do not add up cleanly to 40 if read literally (5×5 + 10 + 10 = 45). Treat the Total of 40 and the five group criteria as certain; **check page 6 of the PDF by eye before relying on the individual split.**

---

## Quick checklist of every hard requirement (derived index; the sections above are the authority)

- Face verification with a CNN producing fixed-length embeddings; score a pair of images (a "trial") by similarity. (§1, §2, §2.1)
- No fully pre-trained models without further training; transfer learning with partial fine-tuning is allowed. (§1, §4)
- Implement BOTH metric learning (e.g. triplet loss) AND classification-based (softmax, use layer before softmax as embedding), and compare them. (§2.1)
- Evaluate with ROC and AUC on `verification_pairs_val.txt`. (§2.2, §5)
- Research and compare cosine similarity vs Euclidean distance. (§2.3)
- Anti-spoofing / liveness: train your own model; detect printed photos and phone screens; integrate seamlessly. (§3)
- Emotion detection: real time; train your own model on public datasets; show icons plus labels; integrate seamlessly. (§4)
- Dataset: Kaggle `classification_data/` (train/val/test, one folder per ID), `verification_data/`, `verification_pairs_val.txt` (path, path, label 1/0). Extra data allowed. (§5)
- UI: webcam, automatic recognition, show name if registered, prompt and allow registration if not, show liveness and emotion immediately. GUI optional but graded. (§6)
- One individual innovative feature per student, relevant to attendance, shown in video and explained in the individual report. (§7)
- Group report ≤ 12 pages: Methodology, Results, Discussion; training scheme, loss, hyperparameters; model comparison and justification. (§8)
- Demo video 5–10 min, every member similar speaking time and face visible, single continuous take with no cuts or edits, hosted online, link submitted on Canvas. (§9)
- Individual report ≤ 5 pages. (§10)
- Submit on Canvas: source code, group report, video link (one member); individual report and peer evaluation form (each member). (§11)
- Group mark adjusted by peer evaluation; final mark may be adjusted by the Week 12 interview. (§12)
