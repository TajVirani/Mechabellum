# Mechabellum Analytics

Spectator and player analytics for Mechabellum: reading match state from replays and the running game, and turning it into statistics, win probabilities, and visualizations.

## Language

### Visualizer

**Visualizer**:
The local browser app that presents match data to the Local Player; made of the Stats view and the Current Match view.
_Avoid_: Dashboard (for the whole app), UI, frontend

**Stats view**:
The part of the Visualizer showing the Local Player's own history across their past matches: trends, unit picks, win rates.
_Avoid_: Statistics page, history dashboard, meta stats

**Current Match view**:
The part of the Visualizer showing the match in progress, as it happens, whether the Local Player is playing or spectating it.
_Avoid_: Live dashboard, in-game overlay, live view

**Local Player**:
The person using this app, identified in match data by their stable player id. Their in-game name can change; the player id does not.
_Avoid_: User, me, owner, account

**Match Summary**:
One past match, reduced to what the Stats view needs about it: when it was played, mode, map, opponent, result, and what the Local Player fielded. There is one per replay.
_Avoid_: Stats row, match record, history entry

### Match

**Specialist**:
The specialist a player takes at the start of a match, which shapes their whole game. Distinct from the enhancement and officer cards picked up in later rounds.
_Avoid_: Officer, commander

**Opening**:
The opening lineup a player picks before round 1, such as "3 Arclight + 2 Sledgehammer".
_Avoid_: Advance team, starting comp, build
