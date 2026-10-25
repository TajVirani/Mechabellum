# Experiments

## 2026-10-24: tournament replays and fixed winner labels

Data: the whole replay tree, exported after the winner fix (e551ccc, no more `teamRanks`). `fetch-replays --full --versions 2.0.0.1.2324` labelled the one unlabelled tournament replay and downloaded 806 more of that version, so every tournament replay of 2324, 2331 and 2340 has a result file. `export-dataset`: 2,462 replays, 2,005 1v1 matches with a winner, 49 without (2331 ladder matches that did not end by surrender), 13,640 snapshots. `dataset-stats`: no duplicates or parse failures; 463 abnormal (408 not 1v1, 69 no winner, 10 AsyncBattle, 5 fewer than 2 fight_over snapshots, 5 missing round records).

| Usable 1v1 matches | Competition | Normal (ladder) |
| --- | ---: | ---: |
| 2324 (2.0.0.1) | 623 | 0 |
| 2331 (2.0.0.4) | 827 | 1 |
| 2340 (2.0.0.5) | 535 | 17 |

That is 2,003 matches in all; 1,984 of the 1,999 matches that `dataset-stats` counts as usable are on map 1012, the tournament map. Only 6 of the 49 matches behind the 2026-10-23 models still have a known winner, so those models were trained mostly on labels that named the leader one fight before the end.

Settings, seed 20260711, test size 0.25:

- `mecha train --split time --calibration sigmoid` is the new `artifacts/win_model.joblib`. The time split holds out the newest 501 matches, all of them 2340 (484 tournament and 17 ladder); 1,202 matches train it and 300 calibrate it.
- The same model without calibration, and a group split model without calibration (the 2026-10-23 settings), were trained for comparison. Both are kept in `artifacts/variants/`.
- `mecha train-deep` for deepsets, transformer and gnn ran with the earlier settings (group split, 300 epochs, patience 30, advantage weight 0), on CPU. Every run kept epoch 1 and stopped at epoch 31. The 2026-10-23 models are in `artifacts/previous-2026-10-23/`.

`mecha evaluate` on held-out matches, leaving out any match from the 2026-10-23 dataset so the old model is never scored on its own training data. Each test set holds the test matches of the split that trained the new models in its rows. The 2026-10-23 `.pt` models no longer load (they predate the advantage head), so only the old logistic model is rescored.

| Test set | Model | Matches | Accuracy | ROC AUC | Log loss | Brier |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Group split, all versions | Logistic, 2026-10-23 | 499 | 0.551 | 0.576 | 0.735 | 0.261 |
| | Logistic, group | 499 | 0.673 | 0.737 | 0.598 | 0.207 |
| | Deep Sets | 499 | 0.668 | 0.725 | 0.615 | 0.213 |
| | Transformer | 499 | 0.652 | 0.706 | 0.680 | 0.233 |
| | GNN | 499 | 0.670 | 0.731 | 0.634 | 0.217 |
| Group split, 2340 only | Logistic, 2026-10-23 | 139 | 0.582 | 0.619 | 0.692 | 0.245 |
| | Logistic, group | 139 | 0.670 | 0.735 | 0.598 | 0.207 |
| | Deep Sets | 139 | 0.652 | 0.707 | 0.635 | 0.221 |
| | Transformer | 139 | 0.625 | 0.680 | 0.715 | 0.245 |
| | GNN | 139 | 0.639 | 0.706 | 0.672 | 0.230 |
| Time split, newest (all 2340) | Logistic, 2026-10-23 | 496 | 0.572 | 0.600 | 0.711 | 0.251 |
| | Logistic, time + sigmoid | 496 | 0.677 | 0.737 | 0.603 | 0.208 |
| | Logistic, time, uncalibrated | 496 | 0.677 | 0.741 | 0.601 | 0.206 |
| Time split, 2340 ladder only | Logistic, 2026-10-23 | 12 | 0.667 | 0.718 | 0.624 | 0.216 |
| | Logistic, time + sigmoid | 12 | 0.667 | 0.752 | 0.601 | 0.206 |
| | Logistic, time, uncalibrated | 12 | 0.716 | 0.770 | 0.780 | 0.221 |

The 2026-10-23 model is close to chance on tournament matches. Its 0.705 accuracy and 0.78 AUC came from 13 ladder matches with the old labels. The new models gain about 0.1 accuracy and 0.15 AUC.

Tournament data does not hurt 2.0.0.5 overall. The group model scores the same on its 2340 matches as on all versions, and the time-split model reaches 0.68 accuracy on the newest 2340 matches, although only 51 of its 1,502 training and calibration matches are 2340. Ladder matches are another matter. All but one usable ladder match are 2340, and all 17 fall in the time split's test set, so the training set holds no 2340 ladder games. On the 12 unseen ones, the uncalibrated model ranks well but is overconfident: log loss 0.78 and calibration error 0.20. Sigmoid calibration brings that to 0.60 and costs almost nothing on tournament matches, which is why the calibrated model is the default for `live-predict`. Twelve matches are far too few to settle this. Labelling the 2331 ladder replays (`mecha fetch-results`) and collecting more 2340 ladder matches would give a real ladder test set.

Accuracy rises by round, as before: from 0.59 after round 1 to 0.72 to 0.74 in rounds 5 to 7 (time split). With 2,000 matches the token models still keep their first epoch and stay below logistic regression, and the transformer is the worst calibrated. By version, the group model scores 0.65 on 2324, 0.69 on 2331 and 0.67 on 2340.

Before the fix, an export of the same replays had 2,045 usable matches, with the `teamRanks` labels on the ladder and Async matches. On it, the group-split logistic model scored accuracy 0.683, AUC 0.753 and log loss 0.587. The time-split model, uncalibrated, scored 0.676, 0.739 and 0.599.

## 2026-10-23 baseline

Results on the local replay set as of 2026-10-23: 49 usable 1v1 matches (formats 2331 and 2340), random whole-match test split of 13 matches unless noted. The winners came from the final `teamRanks`, which e551ccc found to lag one fight; see above. With this little data every difference below is within noise; the numbers are a baseline to repeat once more replays are collected, not conclusions.

### Win model by feature set and architecture

`mecha train` (logistic regression) and `mecha train-deep`, group split, seed 20260711.

| Model | Accuracy | ROC AUC | Log loss |
| --- | ---: | ---: | ---: |
| Logistic, feature schema 1 (score-based labels, before the fix) | 0.58 | 0.59 | 0.69 |
| Logistic, feature schema 1 (teamRanks labels) | 0.58 | 0.67 | 0.64 |
| Logistic, feature schema 2 | 0.71 | 0.78 | 0.58 |
| Deep Sets | 0.70 | 0.79 | 0.57 |
| Transformer | 0.68 | 0.78 | 0.58 |
| GNN | 0.68 | 0.76 | 0.59 |

On the time split (newest 12 matches held out) logistic regression with feature schema 2 reaches accuracy 0.72, AUC 0.76, log loss 0.65. The token models keep the epoch with the best validation loss, which was the first one in every run: they need far more matches before their capacity helps.

### Round advantage as an auxiliary target

`mecha ablate --architecture deepsets`: one Deep Sets model per advantage loss weight. Card ranking places the offered cards (round r's offer, from the round r - 1 fight_over position) and reports the mean reciprocal rank of the card each player actually picked, split by the match's eventual winner (74 picks) and loser (77 picks). A random order scores about 0.52 with four offered cards.

| Advantage loss weight | Log loss | AUC | Calibration error | Advantage RMSE | Advantage sign accuracy | MRR winner / loser, value = P(win) | MRR winner / loser, + 0.3 × advantage |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 0 | 0.581 | 0.771 | 0.107 | 0.99 | 0.57 | 0.57 / 0.63 | 0.61 / 0.62 |
| 0.1 | 0.583 | 0.770 | 0.104 | 1.02 | 0.49 | 0.57 / 0.59 | 0.63 / 0.59 |
| 0.3 | 0.589 | 0.765 | 0.089 | 1.03 | 0.48 | 0.57 / 0.60 | 0.60 / 0.59 |
| 1.0 | 0.600 | 0.760 | 0.110 | 1.03 | 0.49 | 0.59 / 0.61 | 0.60 / 0.58 |

The auxiliary loss slightly worsens the final-result log loss as its weight grows, and the advantage head does not learn (sign accuracy at chance). Adding the predicted advantage to the ranking value nudges the winners' picks above the losers', but by less than the noise at this sample size. Repeat with more data before choosing a weight; until then the default stays at 0 (final result only).
