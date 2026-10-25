# Experiments

## 2026-10-25: positioning style labels and role-aware features (feature schema 3)

Question: do community positioning styles (Aggro / Standard / Defense, side-stack, flank, screened carries, and so on) and role-aware positioning features improve win prediction over feature schema 2? Data: `data/match-snapshots.v2.jsonl` as in the 2026-10-24 section (2,003 matches, 13,640 snapshots, 27,280 player rows; 1,985 tournament matches and 18 ladder matches).

**Answer: no.** No variant beats schema 2 by more than the noise floor in any test, and the labels make things slightly worse. Schema 3 is committed as an opt-in (`mecha train --feature-schema 3`), but no schema 3 artifact was saved, and `artifacts/win_model.joblib` is unchanged.

### Board geometry, checked against the data

Sources: qbisi/mechcore @ b2c7804, `config/maps.yaml`, `docs/rules/map.md`, `docs/rules/landing.md` and `config/units/*.yaml` `formation.footprint`.

- **A unit's x/y is its footprint's centre, not a corner.** All 414,506 unit positions are whole metres. In every one, x mod 10 is 5 exactly when half the footprint's width is an odd number of tens, and 0 otherwise; y follows the same rule with the depth. A corner would always sit at 0. The extreme positions match the centre prediction for every unit: a 50 m-wide Crawler ranges over x -275..275 and a 20 m-wide Marksman over -290..290.
- **`is_rotated` turns the footprint 90 degrees.** Width and depth swap: a rotated Crawler ranges over x -290..290 and depth 35..285, so it is 20 m wide and 50 m deep. In the main region, a rotated wide formation is a column ("vertical"). On a flank, which faces sideways, an unrotated formation is already turned (a flank Crawler stands at |x| 310, 20 m wide), so `is_rotated` is relative to the region's facing. Rotation means nothing for the 19 square units. Among the 13 non-square units in the main region, 40% of formations are rotated.
- **Towers:** every map (Desert, Grass, MilitaryBase, and so 1001/1011/1012/1021/1031/1032) puts the four towers at x = ±140, 170 m deep in each side's half. The tower line is at depth 170 everywhere.
- **No round 1 setback.** The minimum main-region depth is 20 m (a 20 m-deep formation against the region's edge at 10 m) in round 1 and in every later round. The 1st and 5th percentiles are also the same (20 and 45-50) from round 1 to round 9.
- **Flank deploys** (depth < 0 and |x| > 300) never occur in round 1 and appear from round 2 (522 formations), peaking in rounds 5 and 6 (about 2,100 each). That matches `active_round: 2` for every region. 22% of tournament player snapshots have a formation on a flank.
- **Bug found: flank formations can flip a player's frame.** `geometry.board_sign` picks the half from the mean y of all units, and flank units stand on the other half. In 408 player snapshots (1.5%, 120 matches), a flank-heavy board outvotes its own main region, and schema 2 sees the board rotated 180 degrees. The seat index always agrees with a vote by main-region units (|x| ≤ 300) only. Schema 3 uses that vote (`unit_tokens(..., main_region_frame=True)`). Schema 2 keeps the old vote, so existing models see exactly the features they were trained on. The fix by itself changes nothing measurable (the "frame fix only" row below).

### Label definitions (final thresholds)

Per player per snapshot, in the owner's frame (`features/style.py`). Statistics are weighted by `sell_supply`. Roles are the primary role from `visualizer/unit_roles.json`. Main formations have depth ≥ 0 and flank formations depth < 0; only main formations count, except for flank share.

| Label | Rule |
| --- | --- |
| Aggro | front depth ≤ 30 and mean depth < 110, or ≥ 50% of main supply at depth < 100 |
| Defense | not Aggro, and ≥ 75% of main supply at depth ≥ 170 (the tower line) |
| Standard | otherwise |
| Side-stack | one side lane (\|x\| > 100) holds ≥ 60% of main supply, or the supply-weighted mean x is beyond ±100 |
| Diagonal | not Side-stack; both side lanes hold ≥ 15%, and their front depths differ by > 100 |
| Balanced | otherwise |
| Flanking / Gospel flank | flank share > 0 / ≥ 25% of all supply |
| Screened / Exposed | screen gap (mean depth of Damage minus mean depth of Chaff + Tank) ≥ 40 / ≤ -20; unknown without both groups |
| Layered | supply-weighted standard deviation of chaff depth > 50; unknown with fewer than two chaff formations |
| Death ball | ≥ 50% of Damage supply within 80 m of the Damage centroid; unknown with fewer than two Damage formations |
| Headbutt | both boards Aggro, with their heaviest lane in the same lane of the board |
| Crossfire | both boards Side-stack, on opposite sides of the board |

The thresholds come from the histograms by round band (1-3, 4-6, 7+):

- **Front depth** has a sharp mode at 20-30, the region's edge: 19% of boards in rounds 1-3 and 41% in rounds 7+. Behind it is a broad hump from 50 to 170, peaking at 130.
- **Mean depth** is unimodal, with a median of 161-171 and no natural break, so Aggro's mean < 110 takes the forward 15-20%.
- **Rear share** has spikes at 0 and at 0.95-1 in rounds 1-3 (10% of boards), with a dip near 0.7. The brief's 0.6 made 30% of boards Defense; 0.75 makes 16-18%.
- **Side share** has a dip at 0.6 in rounds 1-3 (12% of boards at 0.55-0.6, 4% at 0.6-0.65). That moved Side-stack from 0.55 to 0.6, and the mean-x limit to 100.
- **Screen gap** is unimodal around +11 (standard deviation about 55), so the cuts take roughly thirds; Exposed moved from 0 to -20.
- **Chaff layering** has a spike at 0 (one chaff row) and then a mode that moves from 40 to 60 as rounds go on; 50 is its median.
- **Damage compactness** has spikes at 0 and 1 early on.
- **Flank share** is 0 for 76-90% of boards; ≥ 25% is a 2-4% tail.

Label shares, tournament (27,038 rows) vs. ladder (242 rows):

| Source | Aggro | Standard | Defense | Side | Diagonal | Balanced | Screened | Neutral | Exposed | Screen unknown | Flanking |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tournament | 21% | 61% | 17% | 23% | 5% | 72% | 26% | 35% | 25% | 14% | 22% |
| Ladder | 24% | 66% | 10% | 24% | 5% | 71% | 28% | 26% | 31% | 14% | 25% |

### Descriptive win rates

Each player's label is its modal label over the round band. Each (match, band) counts once, and only when the two players' labels differ; a match where both share a label is 50% by construction. Win rate is for the first label, with a 95% Wilson interval.

| Comparison | Rounds 1-3 | Rounds 4-6 | Rounds 7+ |
| --- | --- | --- | --- |
| Aggro over Standard | .471 [.431, .512] n=575 | .486 [.443, .528] n=529 | .524 [.465, .583] n=269 |
| Aggro over Defense | .513 [.435, .591] n=154 | .491 [.398, .584] n=108 | .476 [.334, .623] n=42 |
| Defense over Standard | .506 [.457, .555] n=397 | .500 [.451, .549] n=400 | .482 [.421, .544] n=249 |
| Side-stack vs. other | .520 [.484, .556] n=737 | .469 [.423, .516] n=439 | .405 [.331, .484] n=153 |
| Diagonal vs. other | .592 [.493, .684] n=98 | .571 [.505, .635] n=217 | .556 [.472, .638] n=133 |
| Flanking vs. none | .496 [.436, .556] n=262 | .500 [.461, .539] n=614 | .471 [.424, .518] n=431 |
| Gospel flank vs. other | .438 [.340, .542] n=89 | .435 [.358, .516] n=147 | .468 [.360, .578] n=77 |
| Exposed vs. other | .579 [.534, .623] n=473 | .560 [.523, .595] n=722 | .525 [.476, .573] n=406 |
| Screened vs. other | .448 [.405, .491] n=505 | .479 [.444, .514] n=764 | .514 [.467, .561] n=432 |
| Layered over flat | .499 [.460, .538] n=635 | .505 [.470, .541] n=758 | .545 [.494, .594] n=382 |
| Death ball over spread | .452 [.407, .498] n=456 | .446 [.405, .488] n=556 | .481 [.418, .545] n=235 |

- **Depth style carries no signal.** Aggro, Standard and Defense all win 47-52% against each other, in every band.
- The few departures from 50% are the counterintuitive ones:
  - Damage placed *ahead of* its chaff and tanks ("Exposed") wins 56-58% in rounds 1-6.
  - Screened boards and death balls win about 45% early.
  - Diagonal boards win 55-59%.
  - Side-stacking turns from neutral to losing (.405 in rounds 7+).
- These are associations, not causes. Board strength confounds them: a player who is ahead can push carries forward, and a player who is behind turtles behind chaff. The model already sees the strength.
- **Pairwise styles are rare:** Headbutt in 2-4% of snapshots; Crossfire in 4% of rounds 1-3 snapshots and almost never later. Both are symmetric, so neither has a win rate of its own.

### Does it improve prediction?

Logistic regression as in `mecha train`. The variants are:

- **Schema 2**: the baseline.
- **Frame fix only**: schema 2's features in schema 3's corrected frame.
- **+ labels**: the 18 label features: one-hot differences, masks, Headbutt and Crossfire, and their products with `investment_share_diff`.
- **+ continuous**: the 15 role-aware continuous features: flank, forward and behind-tower shares; side-lane share; lateral offset; rotated share; diagonal front gap; screen depth gap; chaff layering; damage compactness. Each undefined value has a mask.
- **Schema 3**: both groups.

Grouped CV is 5-fold by match with 5 seeds (20260711, 1-4), and C is picked by an inner 3-fold grouped CV from 0.001-0.03; 0.001 or 0.003 won every time. Each Δ is the variant minus schema 2, averaged over seeds, with a paired cluster bootstrap 95% interval over matches (1,000 resamples). A negative Δ log loss or Brier, or a positive Δ AUC or accuracy, is better.

| Test | Variant | Log loss | AUC | Accuracy | Brier | Δ log loss [95% CI] | Δ AUC [95% CI] |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Grouped CV, all 2,003 matches | Schema 2 | 0.5972 | 0.7411 | 0.6744 | 0.2057 | | |
| | Frame fix only | 0.5978 | 0.7405 | 0.6744 | 0.2060 | +0.0006 [-0.0000, +0.0012] | -0.0006 [-0.0013, +0.0001] |
| | + labels | 0.5987 | 0.7393 | 0.6723 | 0.2064 | +0.0015 [+0.0002, +0.0027] | -0.0019 [-0.0034, -0.0003] |
| | + continuous | 0.5969 | 0.7414 | 0.6747 | 0.2056 | -0.0003 [-0.0023, +0.0017] | +0.0003 [-0.0023, +0.0029] |
| | Schema 3 (both) | 0.5977 | 0.7405 | 0.6736 | 0.2060 | +0.0005 [-0.0017, +0.0026] | -0.0007 [-0.0034, +0.0020] |
| Grouped CV, 552 matches of 2340 | Schema 2 | 0.6015 | 0.7344 | 0.6680 | 0.2081 | | |
| | Frame fix only | 0.6027 | 0.7330 | 0.6676 | 0.2086 | +0.0012 [-0.0002, +0.0027] | -0.0014 [-0.0033, +0.0002] |
| | + labels | 0.6042 | 0.7311 | 0.6654 | 0.2092 | +0.0027 [+0.0001, +0.0052] | -0.0033 [-0.0064, -0.0003] |
| | + continuous | 0.6024 | 0.7333 | 0.6700 | 0.2085 | +0.0009 [-0.0029, +0.0051] | -0.0011 [-0.0062, +0.0037] |
| | Schema 3 (both) | 0.6035 | 0.7323 | 0.6698 | 0.2089 | +0.0019 [-0.0022, +0.0063] | -0.0021 [-0.0072, +0.0030] |
| Grouped CV, 18 ladder matches | Schema 2 | 0.6121 | 0.7463 | 0.6868 | 0.2080 | | |
| | + continuous | 0.6072 | 0.7522 | 0.6926 | 0.2055 | -0.0049 [-0.0276, +0.0176] | +0.0059 [-0.0106, +0.0239] |
| | Schema 3 (both) | 0.6119 | 0.7493 | 0.6810 | 0.2070 | -0.0003 [-0.0199, +0.0202] | +0.0031 [-0.0124, +0.0197] |
| Time split, newest 501 (all 2340), sigmoid | Schema 2 | 0.6047 | 0.7349 | 0.6759 | 0.2086 | | |
| | Frame fix only | 0.6060 | 0.7330 | 0.6742 | 0.2092 | +0.0013 [-0.0008, +0.0036] | -0.0019 [-0.0047, +0.0007] |
| | + labels | 0.6075 | 0.7311 | 0.6707 | 0.2099 | +0.0028 [-0.0007, +0.0063] | -0.0038 [-0.0084, +0.0006] |
| | + continuous | 0.6058 | 0.7324 | 0.6675 | 0.2093 | +0.0011 [-0.0039, +0.0063] | -0.0025 [-0.0092, +0.0037] |
| | Schema 3 (both) | 0.6065 | 0.7315 | 0.6707 | 0.2096 | +0.0018 [-0.0034, +0.0075] | -0.0034 [-0.0105, +0.0034] |
| Time split, 17 ladder matches, sigmoid | Schema 2 | 0.6484 | 0.6904 | 0.6333 | 0.2260 | | |
| | + continuous | 0.6479 | 0.6833 | 0.6167 | 0.2265 | -0.0005 [-0.0283, +0.0279] | -0.0071 [-0.0487, +0.0344] |
| | Schema 3 (both) | 0.6520 | 0.6764 | 0.6000 | 0.2282 | +0.0037 [-0.0226, +0.0298] | -0.0140 [-0.0580, +0.0293] |

- **Every change is under the noise floor** (0.005 log loss, 0.01 AUC). The continuous features are the closest to neutral.
- **The labels are slightly worse**: their intervals exclude 0 on grouped CV, but by 0.0015 log loss.
- **By round band** (grouped CV), the continuous features gain at most 0.001 log loss and 0.002 AUC in rounds 1-3, and nothing later.
- **The ladder subsets are too small to read**; their intervals are ±0.02-0.03.
- The time-split schema 2 row reproduces the 2026-10-24 model: 0.605 / 0.735 / 0.676 on the full 501, against 0.603 / 0.737 / 0.677 on its 496 unseen matches.
- The likely reason: schema 2's depth, density, protection, lane and zone features plus the per-unit value counts already carry what these summaries describe, and the style that predicts outcomes is mostly a consequence of who is ahead.

**Unanswered:**

- whether `sell_supply` includes technologies and levels;
- beacon pulls, which coordinates cannot show;
- tech-dependent roles. The role table is fixed per unit, so a Sledgehammer with chaff-clear techs still counts as Tank.

The scripts for this section (`geom.py`, `hist.py`, `winrates.py`, `compare.py` and `report.py`) were in the session scratchpad and are not committed.

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
