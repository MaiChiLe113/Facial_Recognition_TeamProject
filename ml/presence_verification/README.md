# Presence verification + door audit (Đức Mạnh)

Individual innovative feature (COS30082, §7 of the brief). Checking in with the right face is not proof of
attendance. This module checks two more things from where people are on the Room 204 floor map:

| | Door audit | Presence verification |
| --- | --- | --- |
| Question | Does every person walking in have a check-in, and every check-in a person walking in? | Did the student who checked in stay in class? |
| Output | Alerts D1 (entered without check-in), D2 (tailgating), D3 (checked in, never entered) | Score 0–1 per student, flagged or not, with reasons (R1–R5, or "unusual pattern") |
| Model | Learned dt model + Hungarian assignment; logistic-regression pair classifier (selected) | IsolationForest vs LogisticRegression vs RandomForest (selected by val AUC) + rules |

Plan, design decisions and what changed while building it: [`PLAN.md`](PLAN.md) (Vietnamese).
Manual test steps with expected results: [`TEST.md`](TEST.md) (Vietnamese).

## Files

| File | What it does |
| --- | --- |
| `pv_common.py` | Paths, readers for `data/tracks/`, `data/calibration/`, `data/ground_truth/` (read only) |
| `trajectories.py` | Box feet → map (homography), valid area per camera, smoothing, zones corridor / door / room |
| `door_audit.py` | Door crossings (in / out), `DtModel`, pair features, assignment with "unmatched" costs, alerts |
| `presence.py` | Per-student features, rules R1–R5, model score and explanation |
| `simulate.py` | Labelled synthetic sessions (normal + 8 kinds of fraud), parameters from the recorded takes |
| `sessions.py` | A recorded take as a session; real dt samples for the dt model |
| `train.py` | Fits everything, writes `presence_verification.joblib` + `outputs/train_report.json` |
| `evaluate.py` | Writes `outputs/eval/report.md`, `report.json`, `presence_roc.png`, `door_f1.png` |
| `infer.py` | API for the backend: `to_map`, `audit_door`, `score_session`, `analyze_take`, `model_info` |
| `pv_metrics.py` | Scoring helpers shared by train and evaluate |
| `tests/` | 19 unit tests (3 need the trained model and skip without it) |

`presence_verification.joblib` and `outputs/` are git-ignored. Rebuild them with the commands below.

## Run (from the repo root, Windows)

```bash
.venv/Scripts/python -m pip install -r requirements.txt        # adds scikit-learn, scipy, joblib
.venv/Scripts/python -m pip install matplotlib                 # only for the figures
.venv/Scripts/python ml/presence_verification/train.py         # ~2 min on a laptop CPU
.venv/Scripts/python ml/presence_verification/evaluate.py      # ~1 min
.venv/Scripts/python ml/presence_verification/trajectories.py --take 1 --plot
.venv/Scripts/python -m unittest discover -s ml/presence_verification/tests -v
```

`train.py --quick` / `evaluate.py --quick` use small sets (a smoke test, the model is worse).
Seeds are fixed, so the same library versions give the same numbers.

In the app: switched on in `backend/pipeline.json` (`"presence_verification": true`), served by
`backend/app/features/presence_verification/`:

- `GET /api/features/presence_verification/take/{take}`: alerts, matches, student scores and map trails of a recorded take
- `GET /api/features/presence_verification/model`: which models were selected, threshold, dt model
- `GET /api/features/presence_verification/live`: check-in events received from the pipeline (live mode is a TODO)

The Demo (MultiCam) page shows it in the **Presence verification** panel and as trails on the room map (red = part of an alert).

## How it works

1. **Map trajectories.** Feet = bottom-centre of each cam_1 / cam_2 box, projected with the team's homographies.
   Points outside the area a camera's homography is valid for are dropped (cam_1 also sees into the room through
   the glass, cam_2 sees a poster in the corridor).
2. **Door crossings.** A door visit of a cam_2 track that comes from the corridor (or starts at the door) and goes
   into the room (or ends there) is an entry, at the moment the track leaves the door area. Room → door → gone is
   an exit. A cam_1 track that walks to the door and disappears corroborates the entry (higher confidence).
3. **Matching.** Every check-in is paired with at most one entry by an optimal assignment (Hungarian) that can also
   leave either side unmatched. The pair cost comes from a logistic-regression classifier on 13 pair features.
   The strongest feature: the attendance camera stands in the doorway, so whoever checked in was at the door at
   that moment, and the right entry's door visit contains the check-in time. Other features: dt likelihood under
   the dt model fitted on the takes, crossing confidence, order at the door, crowding.
4. **Alerts.** Unmatched entry → D1, or D2 when it came within 4 s of a matched entry (tailgating). Unmatched
   check-in → D3. Each alert has a score. Alerts below the minimum score tuned on validation go to `suppressed`.
5. **Presence.** The matched track is the student's track. A student is in class from the entry until an exit
   crossing of one of their tracks (a track disappearing inside the room is not leaving). Features per student:
   lateness, time in room, early leave, exits, double check-ins, speed jumps, two places at once, door match cost,
   recognition similarity, spoof flags. Rules R1–R5 give readable reasons. The model gives a score for the patterns
   no rule describes (for example arriving very late, or waiting a long time before walking in).
6. **Training data.** The 8 recorded takes are too few and too short (6–49 s, no fraud). The models train on
   simulated sessions whose dt distribution, walking speed, coordinate noise and miss rate come from the takes.
   The takes are used for the dt model and for evaluation. A recorded take is scored as the first seconds of a
   90-minute class (`sessions.CLASS_S`): it only films people arriving.

## Results (simulated test set, 500 sessions; real takes)

From `outputs/eval/report.md` of the committed code (regenerate it to get exact numbers):

- **Door audit, entry alerts F1:** fixed 0–15 s window (like `link_names.py`) 0.22 · dt model + Hungarian 0.48 · pair classifier 0.68.
- **Door audit, D3 F1:** 0.08 · 0.18 · 0.23. D3 stays low because the simulated detector misses 4 % of crossings,
  more often than students really skip class. Most D3 alerts are missed crossings, not fraud.
- **Presence ROC-AUC:** rules only 0.71 · IsolationForest 0.79 · LogisticRegression 0.81 · RandomForest 0.86 (model only).
  The model catches 94 % of "very late" students (rules: 8 %). Recall on "loiter" (a long wait before walking in) is still only 0.52.
- **Robustness:** presence AUC 0.87 → 0.77 when the map noise goes from 0.12 m to 0.6 m. Door mean F1 drops by 0.03 under
  ±2 s of camera clock jitter.
- **Recorded takes:** take 1 finds 4/4 entries within 0.7 s of the hand labels and agrees 4/4 with `link_names.py`.
  No alert and nobody flagged on takes 1, 4 and 8. **Take 3 gives a false D3 + D1**: three people stand in the
  doorway for ~10 s and the tracker switches IDs, so the entering track's door visit starts after that person's
  check-in. Takes 5, 6 and 7 give D1 because the attendance camera recognised nobody there. Their scenario is not
  written down yet.

## Limits (say them in the report)

- No recorded fraud yet: every number on fraud comes from the simulator. Record scripted takes (PLAN §8 step 7).
- Identity in the room relies on the door match; people who checked in within a few seconds of each other can be
  swapped (match accuracy ~0.70 in crowded simulated doors). Mai Chi's Re-ID matcher would fix this.
- Homographies are estimates (no floor markers). Map positions far from the door are less reliable.
- Scores are suggestions for the lecturer, never automatic penalties. Only positions and times are stored, never images.
