"""
benchmark_arc3.py -- Evaluate POLICY_CODE from target_arc3_agent.py against
ARC-AGI-3 public environments.

Used by codopt as: --command "BENCHMARK_MODE=fast .venv/bin/python3 benchmark_arc3.py"

Modes (set via BENCHMARK_MODE env var):
  fast (default) -- 5 games, 100 actions each.  ~30s.
  full           -- all 25 games, 200 actions each.  ~5min.

For codopt: writes metric.json with {"score": <float>, ...}
"""

import json
import os
import random
import signal
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from arc_agi import Arcade
from arcengine import GameAction, GameState

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BENCHMARK_MODE = os.environ.get("BENCHMARK_MODE", "fast")

if BENCHMARK_MODE == "full":
    NUM_GAMES = 25          # all public environments
    MAX_ACTIONS = 200       # per game
    GAME_TIMEOUT = 120      # seconds per game
else:
    NUM_GAMES = 5           # fast iteration for codopt
    MAX_ACTIONS = 100       # per game
    GAME_TIMEOUT = 30       # seconds per game

RANDOM_SEED = 42
METRIC_FILE = "metric.json"

# ---------------------------------------------------------------------------
# Load POLICY_CODE from target_arc3_agent.py
# ---------------------------------------------------------------------------


def load_policy():
    """Load target_arc3_agent.py, extract POLICY_CODE, exec it, return namespace."""
    target_path = Path(__file__).parent / "target_arc3_agent.py"
    try:
        source = target_path.read_text()
    except Exception as e:
        return None, f"Cannot read {target_path}: {e}"

    # exec the whole file to get POLICY_CODE string
    file_ns = {"__file__": str(target_path), "__name__": "__loader__"}
    try:
        exec(compile(source, str(target_path), "exec"), file_ns)
    except Exception as e:
        return None, f"target_arc3_agent.py failed to load: {e}"

    policy_code = file_ns.get("POLICY_CODE")
    if not policy_code:
        return None, "No POLICY_CODE found in target_arc3_agent.py"

    # exec POLICY_CODE into a clean namespace
    policy_ns = {}
    try:
        exec(policy_code, policy_ns)
    except Exception as e:
        return None, f"POLICY_CODE failed to exec: {e}"

    if "choose_policy_action" not in policy_ns:
        return None, "POLICY_CODE has no choose_policy_action function"

    return policy_ns, None


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------


class GameTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise GameTimeout("Game timed out")


def run_game(env, policy_ns, max_actions=200, timeout=30):
    """Run POLICY_CODE against a single ARC-AGI-3 environment.

    The policy's choose_policy_action signature (from target_arc3_agent.py):
        choose_policy_action(frames, latest_frame, action_log=None)
    where:
        frames:       list of FrameDataRaw objects (history)
        latest_frame: the most recent FrameDataRaw
        action_log:   list of dicts with action records

    Returns dict with game results.
    """
    choose_fn = policy_ns["choose_policy_action"]

    # Set up timeout via SIGALRM (Unix only, graceful fallback otherwise)
    old_handler = None
    use_alarm = hasattr(signal, "SIGALRM")
    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)

    try:
        obs = env.reset()
    except Exception as e:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler or signal.SIG_DFL)
        return {
            "levels_completed": 0,
            "win_levels": 0,
            "actions_taken": 0,
            "unique_frames": 0,
            "state": "ERROR",
            "error": f"reset failed: {e}",
        }

    frames_history = [obs]      # list of FrameDataRaw objects for the policy
    action_log = []             # action records for the policy
    frames_seen = set()         # unique frame bytes for exploration metric

    # Record initial frame
    if obs.frame and len(obs.frame) > 0:
        frames_seen.add(obs.frame[-1].tobytes())

    win_levels = obs.win_levels

    try:
        for step in range(max_actions):
            # Terminal state check
            if obs.state in (GameState.WIN, GameState.GAME_OVER):
                break

            # Call the policy
            try:
                result = choose_fn(
                    frames_history, obs, action_log=action_log
                )
            except Exception:
                # POLICY_CODE crashed -- score what we have
                break

            if result is None:
                # Policy signalled "done"
                break

            action_name = result.get("action", "ACTION1")

            # Execute action
            try:
                if action_name == "ACTION6":
                    x = int(result.get("x", 32))
                    y = int(result.get("y", 32))
                    obs = env.step(GameAction.ACTION6, data={"x": x, "y": y})
                else:
                    action_enum = getattr(GameAction, action_name, GameAction.ACTION1)
                    obs = env.step(action_enum)
            except Exception:
                break

            if obs is None:
                break

            # Update tracking
            frames_history.append(obs)
            action_log.append({
                "action": action_name,
                "step": step,
                "x": result.get("x"),
                "y": result.get("y"),
                "levels": obs.levels_completed,
                "state": obs.state.name,
                "phase": result.get("phase", ""),
            })

            # Track unique frames for exploration score
            if obs.frame and len(obs.frame) > 0:
                frames_seen.add(obs.frame[-1].tobytes())

            # Handle GAME_OVER by resetting (give the policy another shot)
            if obs.state == GameState.GAME_OVER:
                try:
                    obs = env.reset()
                    frames_history = [obs]
                    if obs.frame and len(obs.frame) > 0:
                        frames_seen.add(obs.frame[-1].tobytes())
                except Exception:
                    break

    except GameTimeout:
        pass
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler or signal.SIG_DFL)

    return {
        "levels_completed": obs.levels_completed if obs else 0,
        "win_levels": win_levels,
        "actions_taken": len(action_log),
        "unique_frames": len(frames_seen),
        "state": obs.state.name if obs else "ERROR",
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def compute_metrics(game_results, env_infos):
    """Compute aggregate metrics from per-game results.

    Metrics:
      levels_score:      total levels completed / total levels available  (0-1)
      efficiency_score:  RHAE-style score using baseline_actions           (0-1)
      exploration_score: fraction of unique frame states visited           (0-1)
      combined:          weighted blend for codopt
    """
    total_levels_completed = 0
    total_levels_available = 0
    efficiency_scores = []
    exploration_scores = []

    for result, env_info in zip(game_results, env_infos):
        lc = result["levels_completed"]
        wl = result["win_levels"]
        actions = result["actions_taken"]
        unique = result["unique_frames"]

        total_levels_completed += lc
        total_levels_available += wl

        # Efficiency: RHAE-style per completed level
        # Score = (baseline_actions / actual_actions)^2 for each completed level
        # For overall: if we completed L levels out of N, score the completed ones
        baseline = env_info.baseline_actions or []
        if lc > 0 and baseline and actions > 0:
            # Approximate: distribute actions evenly across completed levels
            # then compare against per-level baselines
            level_efficiencies = []
            for i in range(min(lc, len(baseline))):
                b = baseline[i]
                # estimated actions for this level (proportional)
                est_actions = actions / lc
                eff = min(1.0, (b / max(est_actions, 1)) ** 2)
                level_efficiencies.append(eff)
            # Average over ALL levels (0 for uncompleted)
            full_eff = level_efficiencies + [0.0] * (wl - len(level_efficiencies))
            efficiency_scores.append(sum(full_eff) / wl if wl > 0 else 0.0)
        else:
            efficiency_scores.append(0.0)

        # Exploration: unique frames relative to actions taken + 1
        # More unique frames per action = better exploration
        if actions > 0:
            # Normalise: unique/actions, capped at 1.0
            exploration_scores.append(min(1.0, unique / (actions + 1)))
        else:
            exploration_scores.append(0.0)

    # Aggregate
    levels_score = (
        total_levels_completed / total_levels_available
        if total_levels_available > 0
        else 0.0
    )
    efficiency_score = (
        sum(efficiency_scores) / len(efficiency_scores)
        if efficiency_scores
        else 0.0
    )
    exploration_score = (
        sum(exploration_scores) / len(exploration_scores)
        if exploration_scores
        else 0.0
    )

    # Weighted combination
    combined = (
        0.6 * levels_score
        + 0.3 * efficiency_score
        + 0.1 * exploration_score
    )

    return {
        "score": round(combined, 6),
        "levels_score": round(levels_score, 6),
        "efficiency_score": round(efficiency_score, 6),
        "exploration_score": round(exploration_score, 6),
        "total_levels_completed": total_levels_completed,
        "total_levels_available": total_levels_available,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    t0 = time.time()

    print(f"benchmark_arc3.py  mode={BENCHMARK_MODE}  games={NUM_GAMES}  "
          f"max_actions={MAX_ACTIONS}  timeout={GAME_TIMEOUT}s")
    print()

    # --- Load policy ---
    policy_ns, err = load_policy()
    if policy_ns is None:
        print(f"FATAL: {err}")
        json.dump({"score": 0.0}, open(METRIC_FILE, "w"))
        return

    print("POLICY_CODE loaded OK. Found choose_policy_action.")

    # --- Get environments ---
    try:
        arc = Arcade()
        envs = arc.get_environments()
    except Exception as e:
        print(f"FATAL: Cannot init Arcade: {e}")
        json.dump({"score": 0.0}, open(METRIC_FILE, "w"))
        return

    if not envs:
        print("FATAL: No environments found.")
        json.dump({"score": 0.0}, open(METRIC_FILE, "w"))
        return

    # Deterministic selection for reproducibility
    envs.sort(key=lambda e: e.game_id)
    random.seed(RANDOM_SEED)
    if NUM_GAMES < len(envs):
        selected_envs = random.sample(envs, NUM_GAMES)
    else:
        selected_envs = list(envs)

    print(f"Selected {len(selected_envs)} environments.")
    print()

    # --- Run games ---
    game_results = []
    for i, env_info in enumerate(selected_envs):
        gid = env_info.game_id
        title = env_info.title or gid
        n_levels = len(env_info.baseline_actions) if env_info.baseline_actions else 0
        tags = env_info.tags or []

        print(f"[{i+1}/{len(selected_envs)}] {title} ({gid})  "
              f"levels={n_levels}  tags={tags}")

        try:
            env = arc.make(gid)
        except Exception as e:
            print(f"  ERROR making env: {e}")
            game_results.append({
                "levels_completed": 0,
                "win_levels": n_levels,
                "actions_taken": 0,
                "unique_frames": 0,
                "state": "ERROR",
                "error": str(e),
            })
            continue

        try:
            result = run_game(
                env, policy_ns,
                max_actions=MAX_ACTIONS,
                timeout=GAME_TIMEOUT,
            )
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            result = {
                "levels_completed": 0,
                "win_levels": n_levels,
                "actions_taken": 0,
                "unique_frames": 0,
                "state": "ERROR",
                "error": str(e),
            }

        game_results.append(result)
        print(f"  => levels={result['levels_completed']}/{result['win_levels']}  "
              f"actions={result['actions_taken']}  "
              f"unique_frames={result['unique_frames']}  "
              f"state={result['state']}")

    # --- Compute metrics ---
    metrics = compute_metrics(game_results, selected_envs)

    elapsed = time.time() - t0
    print()
    print(f"{'='*50}")
    print(f"RESULTS  ({elapsed:.1f}s)")
    print(f"{'='*50}")
    print(f"  levels_score:      {metrics['levels_score']:.4f}  "
          f"({metrics['total_levels_completed']}/{metrics['total_levels_available']})")
    print(f"  efficiency_score:  {metrics['efficiency_score']:.4f}")
    print(f"  exploration_score: {metrics['exploration_score']:.4f}")
    print(f"  combined (score):  {metrics['score']:.4f}")

    # --- Write metric.json ---
    with open(METRIC_FILE, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nWrote {METRIC_FILE}")


if __name__ == "__main__":
    main()
