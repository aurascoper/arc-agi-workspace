#!/usr/bin/env python3
"""
run_arc3_baseline.py — Baseline runner for ARC-AGI-3 public environments.

Strategy (simple but not random):
  Phase 1 (Probe): Try each available action once. Record frame deltas.
  Phase 2 (Exploit): Repeat the action that caused the most pixel change.
  Phase 3 (Explore-Exploit): If stuck (no level-up for N steps), try
    different actions including ACTION6 clicks at key positions.
  Uses ACTION7 (undo) if available and last action made things worse
    (frame diverged from a "good" checkpoint).

Caps at MAX_ACTIONS_PER_LEVEL actions per level to avoid infinite loops.
"""

import json
import sys
import time
import traceback
from dataclasses import dataclass, field

import numpy as np

from arc_agi import Arcade
from arcengine import GameAction, GameState

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_ACTIONS_PER_LEVEL = 300      # absolute cap per level
MAX_TOTAL_ACTIONS = 2000         # absolute cap per environment
STUCK_THRESHOLD = 40             # if no level-up after this many steps, switch strategy
CLICK_POSITIONS = [              # positions to try for ACTION6 (click)
    (16, 16), (48, 16), (16, 48), (48, 48),   # quadrants
    (32, 32),                                    # center
    (0, 0), (63, 0), (0, 63), (63, 63),        # corners
    (32, 0), (0, 32), (63, 32), (32, 63),      # edge midpoints
    (8, 8), (24, 24), (40, 40), (56, 56),      # diagonals
    (8, 56), (56, 8), (24, 40), (40, 24),      # anti-diagonals
]


@dataclass
class ActionResult:
    action_id: int
    data: dict
    frame_diff: int       # number of pixels that changed
    levels_before: int
    levels_after: int
    caused_levelup: bool
    caused_gameover: bool


@dataclass
class EnvironmentResult:
    game_id: str
    title: str
    tags: list
    win_levels: int
    levels_completed: int
    total_actions: int
    actions_per_level: list
    baseline_actions: list
    level_scores: list
    env_score: float
    error: str = ""
    observations: str = ""


def frame_distance(f1, f2):
    """Count pixels that differ between two frames."""
    if f1 is None or f2 is None:
        return 0
    return int(np.sum(f1 != f2))


def frame_entropy(frame):
    """Measure visual complexity (unique color count * spatial spread)."""
    if frame is None:
        return 0
    unique = len(np.unique(frame))
    return unique


def run_environment(arc, env_info):
    """Run baseline agent on a single environment. Returns EnvironmentResult."""
    game_id = env_info.game_id
    title = env_info.title or game_id
    tags = env_info.tags or []
    baseline_actions = env_info.baseline_actions or []

    print(f"\n{'='*60}")
    print(f"Environment: {title} ({game_id})")
    print(f"  Tags: {tags}")
    print(f"  Baseline actions: {baseline_actions}")
    print(f"  Levels: {len(baseline_actions)}")
    print(f"{'='*60}")

    try:
        env = arc.make(game_id)
    except Exception as e:
        msg = f"Failed to make environment: {e}"
        print(f"  ERROR: {msg}")
        return EnvironmentResult(
            game_id=game_id, title=title, tags=tags,
            win_levels=len(baseline_actions), levels_completed=0,
            total_actions=0, actions_per_level=[], baseline_actions=baseline_actions,
            level_scores=[], env_score=0.0, error=msg,
        )

    if env is None:
        msg = "arc.make() returned None"
        print(f"  ERROR: {msg}")
        return EnvironmentResult(
            game_id=game_id, title=title, tags=tags,
            win_levels=len(baseline_actions), levels_completed=0,
            total_actions=0, actions_per_level=[], baseline_actions=baseline_actions,
            level_scores=[], env_score=0.0, error=msg,
        )

    obs = env.observation_space
    if obs is None:
        msg = "No initial observation"
        print(f"  ERROR: {msg}")
        return EnvironmentResult(
            game_id=game_id, title=title, tags=tags,
            win_levels=len(baseline_actions), levels_completed=0,
            total_actions=0, actions_per_level=[], baseline_actions=baseline_actions,
            level_scores=[], env_score=0.0, error=msg,
        )

    win_levels = obs.win_levels
    available = obs.available_actions  # list of ints, e.g. [1,2,3,4,5,6]
    has_undo = 7 in available
    has_click = 6 in available
    simple_actions = [a for a in available if a not in (6, 7)]  # keyboard actions
    all_non_undo = [a for a in available if a != 7]

    print(f"  Available actions: {available}")
    print(f"  Simple (keyboard): {simple_actions}")
    print(f"  Has click (ACTION6): {has_click}")
    print(f"  Has undo (ACTION7): {has_undo}")
    print(f"  Win levels: {win_levels}")
    print(f"  Frame shape: {obs.frame[0].shape if obs.frame else 'no frame'}")

    prev_frame = obs.frame[0].copy() if obs.frame else None
    current_levels = obs.levels_completed
    total_actions = 0
    level_action_counts = []  # actions per completed level
    current_level_actions = 0
    observations = []

    # --- Phase 1: Probe each available action ---
    probe_results = {}
    print(f"\n  Phase 1: Probing {len(all_non_undo)} actions...")

    for action_id in all_non_undo:
        if action_id == 6 and has_click:
            # For click, try center
            obs = env.step(GameAction.from_id(action_id), data={"x": 32, "y": 32})
        else:
            obs = env.step(GameAction.from_id(action_id))

        total_actions += 1
        current_level_actions += 1

        if obs is None:
            print(f"    ACTION{action_id}: returned None")
            continue

        diff = frame_distance(prev_frame, obs.frame[0]) if obs.frame else 0
        levelup = obs.levels_completed > current_levels
        gameover = obs.state == GameState.GAME_OVER

        probe_results[action_id] = ActionResult(
            action_id=action_id, data={},
            frame_diff=diff, levels_before=current_levels,
            levels_after=obs.levels_completed,
            caused_levelup=levelup, caused_gameover=gameover,
        )

        tag = ""
        if levelup:
            tag = " ** LEVEL UP **"
            level_action_counts.append(current_level_actions)
            current_level_actions = 0
        if gameover:
            tag = " ** GAME OVER **"

        print(f"    ACTION{action_id}: diff={diff:5d} pixels{tag}")

        current_levels = obs.levels_completed
        prev_frame = obs.frame[0].copy() if obs.frame else None

        # Handle game over during probing
        if gameover:
            obs = env.reset()
            if obs and obs.frame:
                prev_frame = obs.frame[0].copy()
            current_levels = obs.levels_completed if obs else 0
            current_level_actions = 0

        if obs and obs.state == GameState.WIN:
            print(f"    *** WON during probe! ***")
            break

    # --- Rank actions by frame_diff (productive = more change) ---
    ranked_actions = sorted(
        probe_results.values(),
        key=lambda r: (r.caused_levelup, r.frame_diff),
        reverse=True,
    )

    if ranked_actions:
        best_action = ranked_actions[0].action_id
        print(f"\n  Best action from probe: ACTION{best_action} (diff={ranked_actions[0].frame_diff})")
    else:
        best_action = simple_actions[0] if simple_actions else all_non_undo[0]
        print(f"\n  No probe results, defaulting to ACTION{best_action}")

    # --- Phase 2: Exploit + Explore ---
    if obs and obs.state != GameState.WIN:
        print(f"\n  Phase 2: Exploit/Explore (max {MAX_TOTAL_ACTIONS} total actions)...")
        steps_since_levelup = 0
        click_idx = 0
        strategy_mode = "exploit"
        cycle_idx = 0
        checkpoint_frame = prev_frame.copy() if prev_frame is not None else None
        checkpoint_entropy = frame_entropy(prev_frame)

        while total_actions < MAX_TOTAL_ACTIONS and current_level_actions < MAX_ACTIONS_PER_LEVEL:
            # Choose action based on strategy
            if strategy_mode == "exploit":
                # Repeat the best action found during probe
                action_id = best_action
                data = {}
                if action_id == 6 and has_click:
                    data = {"x": 32, "y": 32}

            elif strategy_mode == "explore_cycle":
                # Cycle through all non-undo actions
                action_id = all_non_undo[cycle_idx % len(all_non_undo)]
                cycle_idx += 1
                data = {}
                if action_id == 6 and has_click:
                    pos = CLICK_POSITIONS[click_idx % len(CLICK_POSITIONS)]
                    data = {"x": pos[0], "y": pos[1]}
                    click_idx += 1

            elif strategy_mode == "explore_click":
                # Try clicking at different positions
                if has_click:
                    action_id = 6
                    pos = CLICK_POSITIONS[click_idx % len(CLICK_POSITIONS)]
                    data = {"x": pos[0], "y": pos[1]}
                    click_idx += 1
                else:
                    action_id = all_non_undo[cycle_idx % len(all_non_undo)]
                    cycle_idx += 1
                    data = {}

            else:
                action_id = best_action
                data = {}

            # Execute action
            if data:
                obs = env.step(GameAction.from_id(action_id), data=data)
            else:
                obs = env.step(GameAction.from_id(action_id))

            total_actions += 1
            current_level_actions += 1
            steps_since_levelup += 1

            if obs is None:
                continue

            diff = frame_distance(prev_frame, obs.frame[0]) if obs.frame else 0

            # Check for level up
            if obs.levels_completed > current_levels:
                print(f"    Step {total_actions}: LEVEL UP! levels={obs.levels_completed}/{win_levels} "
                      f"(took {current_level_actions} actions, mode={strategy_mode})")
                level_action_counts.append(current_level_actions)
                current_level_actions = 0
                current_levels = obs.levels_completed
                steps_since_levelup = 0
                strategy_mode = "exploit"
                # Re-probe after level up to find new best action
                checkpoint_frame = obs.frame[0].copy() if obs.frame else None

            # Check for win
            if obs.state == GameState.WIN:
                print(f"    Step {total_actions}: *** WON! *** levels={obs.levels_completed}/{win_levels}")
                break

            # Check for game over
            if obs.state == GameState.GAME_OVER:
                print(f"    Step {total_actions}: GAME OVER at level {current_levels}")
                obs = env.reset()
                if obs and obs.frame:
                    prev_frame = obs.frame[0].copy()
                current_levels = obs.levels_completed if obs else 0
                current_level_actions = 0
                steps_since_levelup = 0
                strategy_mode = "exploit"
                continue

            prev_frame = obs.frame[0].copy() if obs.frame else None

            # Strategy switching: if stuck, try different approaches
            if steps_since_levelup == STUCK_THRESHOLD:
                strategy_mode = "explore_cycle"
                print(f"    Step {total_actions}: Switching to explore_cycle (stuck for {STUCK_THRESHOLD} steps)")
            elif steps_since_levelup == STUCK_THRESHOLD * 2:
                strategy_mode = "explore_click"
                print(f"    Step {total_actions}: Switching to explore_click")
            elif steps_since_levelup == STUCK_THRESHOLD * 3:
                # Try undo if available, then re-exploit
                if has_undo:
                    for _ in range(5):
                        obs = env.step(GameAction.ACTION7)
                        total_actions += 1
                        current_level_actions += 1
                strategy_mode = "exploit"
                steps_since_levelup = 0  # reset counter
                cycle_idx = 0
                click_idx = 0
                print(f"    Step {total_actions}: Reset strategy after {STUCK_THRESHOLD * 3} steps")

    # --- Compute Scores ---
    # For levels we didn't complete, current_level_actions is the count spent
    final_levels = current_levels if obs is None else obs.levels_completed

    # Build per-level scores
    level_scores = []
    for i, baseline_h in enumerate(baseline_actions):
        if i < len(level_action_counts):
            # Level was completed
            a = level_action_counts[i]
            if a > 0:
                score = min(1.0, (baseline_h / a) ** 2)
            else:
                score = 0.0
            level_scores.append(score)
        else:
            # Level not completed
            level_scores.append(0.0)

    # Environment score: weighted average, later levels weight more
    # E = sum(l * S_l) / sum(l) for l = 1..n
    n = len(baseline_actions)
    if n > 0 and any(s > 0 for s in level_scores):
        weighted_sum = sum((l + 1) * level_scores[l] for l in range(n))
        weight_total = sum(l + 1 for l in range(n))
        env_score = weighted_sum / weight_total
    else:
        env_score = 0.0

    # Use SDK's actual scoring if available
    sdk_score = None
    try:
        sc = arc.get_scorecard()
        if sc and sc.environments:
            for env_sc in sc.environments:
                if env_sc.id == game_id:
                    sdk_score = env_sc.score
    except Exception:
        pass

    # Summary
    obs_summary = []
    if has_click and not simple_actions:
        obs_summary.append("click-only game")
    elif not has_click and simple_actions:
        obs_summary.append("keyboard-only game")
    elif has_click and simple_actions:
        obs_summary.append("keyboard+click game")
    obs_str = "; ".join(obs_summary) if obs_summary else ""

    actions_str = ", ".join(str(a) for a in level_action_counts) if level_action_counts else "none"
    print(f"\n  Results for {title}:")
    print(f"    Levels completed: {final_levels}/{win_levels}")
    print(f"    Total actions: {total_actions}")
    print(f"    Actions per level: [{actions_str}]")
    print(f"    Baseline actions:  {baseline_actions}")
    print(f"    Level scores: {[f'{s:.4f}' for s in level_scores]}")
    print(f"    Env score (our calc): {env_score:.4f}")
    if sdk_score is not None:
        print(f"    Env score (SDK):      {sdk_score:.4f}")
    print(f"    Type: {obs_str}")

    return EnvironmentResult(
        game_id=game_id, title=title, tags=tags,
        win_levels=win_levels, levels_completed=final_levels,
        total_actions=total_actions,
        actions_per_level=level_action_counts,
        baseline_actions=baseline_actions,
        level_scores=level_scores,
        env_score=env_score,
        observations=obs_str,
    )


def main():
    print("=" * 70)
    print("ARC-AGI-3 Baseline Runner")
    print("=" * 70)

    t0 = time.time()

    arc = Arcade()
    envs = arc.get_environments()
    print(f"\nFound {len(envs)} environments\n")

    # Sort by game_id for reproducibility
    envs.sort(key=lambda e: e.game_id)

    results = []
    for env_info in envs:
        try:
            result = run_environment(arc, env_info)
            results.append(result)
        except Exception as e:
            print(f"\n  EXCEPTION on {env_info.game_id}: {e}")
            traceback.print_exc()
            results.append(EnvironmentResult(
                game_id=env_info.game_id, title=env_info.title or env_info.game_id,
                tags=env_info.tags or [], win_levels=0, levels_completed=0,
                total_actions=0, actions_per_level=[], baseline_actions=env_info.baseline_actions or [],
                level_scores=[], env_score=0.0, error=str(e),
            ))

        # Get and close the scorecard for this environment's run
        try:
            arc.close_scorecard()
        except Exception:
            pass
        # Create fresh scorecard for next env
        arc._default_scorecard_id = None

    elapsed = time.time() - t0

    # --- Final Summary ---
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    total_levels = 0
    total_completed = 0
    total_actions = 0
    envs_solved = []
    envs_partial = []
    envs_failed = []
    tag_scores = {}

    print(f"\n{'Game ID':<20} {'Title':<6} {'Levels':>10} {'Actions':>8} {'Score':>8}  {'Tags'}")
    print("-" * 80)

    for r in results:
        levels_str = f"{r.levels_completed}/{r.win_levels}"
        print(f"{r.game_id:<20} {r.title:<6} {levels_str:>10} {r.total_actions:>8} {r.env_score:>8.4f}  {r.tags}")

        total_levels += r.win_levels
        total_completed += r.levels_completed
        total_actions += r.total_actions

        if r.levels_completed == r.win_levels and r.win_levels > 0:
            envs_solved.append(r)
        elif r.levels_completed > 0:
            envs_partial.append(r)
        else:
            envs_failed.append(r)

        for tag in r.tags:
            if tag not in tag_scores:
                tag_scores[tag] = []
            tag_scores[tag].append(r.env_score)

    # Overall RHAE
    all_scores = [r.env_score for r in results]
    mean_score = np.mean(all_scores) if all_scores else 0.0

    print(f"\n{'='*70}")
    print(f"Environments: {len(results)} total")
    print(f"  Solved (all levels): {len(envs_solved)}")
    print(f"  Partial (some levels): {len(envs_partial)}")
    print(f"  Failed (no levels): {len(envs_failed)}")
    print(f"\nLevels: {total_completed}/{total_levels}")
    print(f"Total actions: {total_actions}")
    print(f"Mean environment score: {mean_score:.4f}")
    print(f"Time elapsed: {elapsed:.1f}s")

    print(f"\nScores by tag:")
    for tag, scores in sorted(tag_scores.items()):
        print(f"  {tag}: mean={np.mean(scores):.4f} ({len(scores)} envs)")

    if envs_solved:
        print(f"\nSolved environments:")
        for r in envs_solved:
            print(f"  {r.game_id} ({r.title}): {r.levels_completed} levels in {r.total_actions} actions")

    if envs_partial:
        print(f"\nPartially solved:")
        for r in envs_partial:
            print(f"  {r.game_id} ({r.title}): {r.levels_completed}/{r.win_levels} levels")

    # Save results to JSON
    results_dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_environments": len(results),
        "total_levels": total_levels,
        "total_completed": total_completed,
        "total_actions": total_actions,
        "mean_score": float(mean_score),
        "elapsed_seconds": elapsed,
        "environments": [
            {
                "game_id": r.game_id,
                "title": r.title,
                "tags": r.tags,
                "win_levels": r.win_levels,
                "levels_completed": r.levels_completed,
                "total_actions": r.total_actions,
                "actions_per_level": r.actions_per_level,
                "baseline_actions": r.baseline_actions,
                "level_scores": r.level_scores,
                "env_score": r.env_score,
                "error": r.error,
                "observations": r.observations,
            }
            for r in results
        ],
    }

    with open("baseline_results.json", "w") as f:
        json.dump(results_dict, f, indent=2)
    print(f"\nResults saved to baseline_results.json")


if __name__ == "__main__":
    main()
