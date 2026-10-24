# Experiments

Results on the local replay set as of 2026-10-23: 49 usable 1v1 matches (formats 2331 and 2340), random whole-match test split of 13 matches unless noted. With this little data every difference below is within noise; the numbers are a baseline to repeat once more replays are collected, not conclusions.

## Win model by feature set and architecture

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

## Round advantage as an auxiliary target

`mecha ablate --architecture deepsets`: one Deep Sets model per advantage loss weight. Card ranking places the offered cards (round r's offer, from the round r - 1 fight_over position) and reports the mean reciprocal rank of the card each player actually picked, split by the match's eventual winner (74 picks) and loser (77 picks). A random order scores about 0.52 with four offered cards.

| Advantage loss weight | Log loss | AUC | Calibration error | Advantage RMSE | Advantage sign accuracy | MRR winner / loser, value = P(win) | MRR winner / loser, + 0.3 × advantage |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 0 | 0.581 | 0.771 | 0.107 | 0.99 | 0.57 | 0.57 / 0.63 | 0.61 / 0.62 |
| 0.1 | 0.583 | 0.770 | 0.104 | 1.02 | 0.49 | 0.57 / 0.59 | 0.63 / 0.59 |
| 0.3 | 0.589 | 0.765 | 0.089 | 1.03 | 0.48 | 0.57 / 0.60 | 0.60 / 0.59 |
| 1.0 | 0.600 | 0.760 | 0.110 | 1.03 | 0.49 | 0.59 / 0.61 | 0.60 / 0.58 |

The auxiliary loss slightly worsens the final-result log loss as its weight grows, and the advantage head does not learn (sign accuracy at chance). Adding the predicted advantage to the ranking value nudges the winners' picks above the losers', but by less than the noise at this sample size. Repeat with more data before choosing a weight; until then the default stays at 0 (final result only).
