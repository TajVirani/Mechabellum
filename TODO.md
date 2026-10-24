# TODO

## P0: Spectator win probability baseline

- [x] Generate winner labels from the final `teamRanks` of 1v1 replays (the last `FightReport` describes the second-to-last fight)
- [x] Sample each round at `fight_over`, matching what replays record, and exclude the `round 0` opening selection state
- [x] Split training and test sets by whole `battleId`
- [x] Extract aggregate features for core, supply, formations, levels, experience, equipment, technologies, and positioning
- [x] Train a player-symmetric probability baseline and support `live-predict` inference
- [x] Time-split training (`--split time`) and probability calibration (`--calibration sigmoid|isotonic`)
- [ ] Accumulate at least 5,000 same-version 1v1 matches so time-split calibration has enough data
- [x] Add evaluation reports broken down by round, map, rank tier, and version (`mecha evaluate`; replays carry no rating, so rank tiers need live recordings)
- [x] Read live player phase and predict once per round when both players reach `FightOver`
- [x] Add a stable JSONL recorder for live snapshots, with timestamps (`mecha live-record`)

## P1A: Complete data collection

- [x] Parse replay `actionRecords`: purchases, unlocks, upgrades, technologies, moves, equipment, and abilities (`roundActions`)
- [x] Output each round's dealt card candidates `reinforceItems` and the player's final choice `PAD_ChooseReinforceItem`
- [x] Output specialists, commander abilities, shop unlocks, and building state
- [x] Output the opening lineup choice (`openingLineup`, from the round 0 `PAD_ChooseAdvanceTeam`)
- [x] Read the current round's candidate and chosen cards from the live `ReinforcementManager`
- [x] Map live blueprint ids to the values replays record (verified against a 2.0.0.5 match)
- [ ] Map live energy tower skill ids to the values replays record (memory flags each skill used this round; replays list a subset by an unknown rule)
- [x] Build ID-to-name/cost tables for cards, technologies, equipment, and specialists (`collector/game_names.json`, from qbisi/mechcore for 2.0.0.4 with mech-data 1.8.0.3 as fallback; every id in our Normal 1v1 replays is named, AsyncBattle ids are not)

## P1B: Complete position description

- [x] Represent each formation as an independent token: unit ID, level, experience, value, specific technologies, specific equipment, exact X/Y, orientation, and side
- [x] Normalize both players' coordinate directions, express front-to-back depth relative to the battlefield midline, and preserve left/right lane position (`features/geometry.py`)
- [x] Express relative positions between units: front/back line, neighbor distance, protection relationships, density, left/right lane coverage, and expected engagement order
- [x] Express matchups and counter interactions between opposing units, not just independent per-unit counts (lane matchup features; cross-army attention and GNN edges)
- [x] Add both players' core, max core, remaining supply, current round income, cumulative investment, unlock state, and unspent economy
- [x] Add specific technologies, equipment, specialists, opening lineup, dealt card candidates, final card choice, and commander abilities/cooldowns
- [x] Add towers, energy towers, blueprints, devices, buildings, and enhancement state
- [x] Add previous round battle score, surviving formations, core damage, win/loss history, and economy/core change sequences
- [x] Add map, game mode, game version, balance patch, and available unit pool (token model context; they cancel in the difference features)
- [x] Preserve raw values and explicit masks for missing, unknown, and version-new IDs; never silently treat them as 0
- [x] First implement a fixed grid/zone coordinate baseline, then Deep Sets / Transformer / graph neural network (GNN) models over formation tokens (`mecha train-deep`; they need far more matches to beat the linear model)
- [x] Version the base position schema and keep replay training data and live spectator snapshot fields consistent

## P1C: Round value targets

- [x] Construct normalized round advantage labels from `FightReport.Score`, both players' core changes, and surviving formation value (`training/targets.py`)
- [x] Use final win/loss as the primary target and per-round net core damage / net HP won as auxiliary regression or ranking targets to train a multi-task position value model (`train-deep --advantage-weight`)
- [x] Define "final win/loss primary reward + discounted round advantage auxiliary reward" for action recommendation; normalize and clip round rewards so large local wins do not mask a final loss (`RewardConfig`)
- [x] Use ablation experiments to compare the effect of final win/loss only, adding round advantage, and different reward weights on probability calibration and action ranking (`mecha ablate`; results in docs/experiments.md, no measurable gain yet)

## P2: Action recommendation and self-play

- [x] Implement ranking of candidate purchase, upgrade, technology, and deployment actions on top of the win probability model (`mecha recommend`; static model judgement, no simulated fight)
- [x] Investigate whether `ReplaySimulateMatch` / `ReplayAIMatch` can customize positions, run headless at accelerated speed, and run in batches (read-only findings and design in docs/self-play.md; confirming needs MelonLoader)
- [ ] If an internal simulation entry point is available, wrap it as an AI-vs-AI self-play environment
- [ ] Implement a reproducible batch AI-vs-AI match and `.grbr` replay generator that records random seeds, both strategy versions, game build, and complete results
- [x] Build version indexing, deduplication, abnormal match filtering, and distribution statistics for generated data, and evaluate generalization on a test set of real player replays only (`mecha dataset-stats`, `mecha evaluate`)
- [ ] Investigate sampling ratios, sample weights, and curriculum learning strategies for real replays vs. self-play data
- [ ] Continuously calibrate the simulation environment against real replays so results do not only hold in an approximate simulator
