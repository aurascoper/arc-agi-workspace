# ARC-AGI-3 Policy Evolution

## Goal
Evolve `POLICY_CODE` in `target_arc3_agent.py` to solve more ARC-AGI-3 interactive game levels. The agent receives 64x64 grid frames and must choose actions to complete levels efficiently.

## What to optimize
The `POLICY_CODE` string contains the decision-making logic. Key functions to improve:

- `analyze_frame(frame)` — Extracts features from the 64x64 grid: objects, colors, spatial structure. Better analysis = better decisions.
- `detect_pattern_change(prev, curr)` — Compares frames to understand what an action did: object moved, color changed, new object appeared.
- `exploration_strategy(frame, n_actions, action_log, causal_model)` — First phase: probe actions to discover game mechanics. Returns action dict.
- `exploitation_strategy(frame, n_actions, action_log, causal_model)` — Second phase: repeat effective actions, avoid wasteful ones.
- `choose_policy_action(frames, latest_frame, action_log)` — Main entry point. Decides explore vs exploit, calls the strategy functions.

## Action Space
- ACTION1-5: Simple directional actions (game-specific meaning)
- ACTION6: Click at (x, y) coordinates on 64x64 grid — `{"action": "ACTION6", "x": 32, "y": 15}`
- ACTION7: Undo / additional action
- RESET: Restart current level

## Frame Format
Each frame is a 64x64 numpy int8 array. Values 0-15 are color indices. -1 is transparent.

## Game Types
- `keyboard`: Only ACTION1-4/5 (movement games)
- `click`: Only ACTION6 (puzzle/placement games)
- `keyboard_click`: Both types

## Scoring
- Level score = min(1.0, (human_baseline_actions / your_actions))^2
- Later levels weighted more (level 5 = 5x level 1)
- Games have 5-10 levels each
- GAME_OVER exists — bad actions can lose the game

## Strategy Tips
- Objects detected via connected components are clickable targets for ACTION6
- Track which actions cause level advancement and repeat them
- Use undo (ACTION7) to escape dead-ends
- Different games have different mechanics — the agent must discover them through exploration
- Foreground objects (non-background) are usually interactive
- If an action moves an object, it's probably relevant to the solution

## Constraints
- `POLICY_CODE` must remain a valid Python string that can be exec'd
- Keep `choose_policy_action` signature: `(frames, latest_frame, action_log=None) -> dict`
- Return format: `{"action": "ACTION1"}` or `{"action": "ACTION6", "x": int, "y": int}`
- Return `None` to signal done
- Don't import external packages — only numpy is available
- Keep total size under 600 lines
