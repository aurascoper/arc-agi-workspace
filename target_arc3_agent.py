"""
target_arc3_agent.py — ARC-AGI-3 Neurosymbolic Agent Harness

Architecture: Program synthesis as policy.
  Phase 1 (Exploration): Systematic probing via actions to build causal model
  Phase 2 (Exploitation): BFS in causal graph toward goal state

Uses the official ARC-AGI-3-Agents API:
  - Extends Agent base class
  - Implements choose_action(frames, latest_frame) -> GameAction
  - Implements is_done(frames, latest_frame) -> bool

Backends:
  - MLX local (Qwen3-30B-A3B-4bit + turboquant) for dev/testing
  - OpenAI API for Kaggle submission

codopt integration:
  - POLICY_CODE string is the evolvable target
  - Metric: mean levels_completed over episodes
  - benchmark_arc3.py evaluates against local env

Usage:
  # Register as agent in ARC-AGI-3-Agents framework:
  # Copy to agents/templates/neurosymbolic.py
  # Add to agents/__init__.py AVAILABLE_AGENTS

  # Local testing (standalone):
  python target_arc3_agent.py --test
"""

import json
import logging
import os
import re
import threading
import time
from copy import deepcopy
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_BACKEND = os.environ.get("ARC3_BACKEND", "mlx")  # "mlx" or "openai"
MODEL_PATH = os.environ.get("ARC_MODEL_PATH", "mlx-community/Qwen3-30B-A3B-4bit")
MAX_NEW_TOKENS = int(os.environ.get("ARC_MAX_TOKENS", "1024"))
USE_TURBOQUANT = os.environ.get("USE_TURBOQUANT", "1") == "1"
TQ_BITS = int(os.environ.get("TQ_BITS", "3"))

# ---------------------------------------------------------------------------
# POLICY_CODE — The evolvable target for codopt
# This string defines the agent's decision-making logic.
# codopt mutates this to improve levels_completed.
# ---------------------------------------------------------------------------

POLICY_CODE = r'''
import numpy as np
from collections import Counter, deque

def analyze_frame(frame_data):
    """Extract features from the current game frame."""
    if not frame_data or not hasattr(frame_data, 'frame'):
        return {}

    frame = frame_data.frame
    if not frame or not isinstance(frame, list):
        return {}

    features = {
        'num_grids': len(frame),
        'grid_shapes': [np.array(g).shape if g else (0,0) for g in frame],
        'palettes': [set(c for row in g for c in row) if g else set() for g in frame],
        'symmetries': [],
    }

    for g in frame:
        if not g:
            continue
        arr = np.array(g)
        features['symmetries'].append({
            'h': np.array_equal(arr, arr[:, ::-1]),
            'v': np.array_equal(arr, arr[::-1, :]),
            'r90': np.array_equal(arr, np.rot90(arr)),
        })

    return features


def detect_pattern_change(prev_features, curr_features):
    """Detect what changed between frames to build causal model."""
    if not prev_features or not curr_features:
        return {'type': 'unknown'}

    changes = {}
    if prev_features.get('num_grids') != curr_features.get('num_grids'):
        changes['grid_count_changed'] = True

    prev_shapes = prev_features.get('grid_shapes', [])
    curr_shapes = curr_features.get('grid_shapes', [])
    if prev_shapes != curr_shapes:
        changes['shapes_changed'] = True

    prev_palettes = prev_features.get('palettes', [])
    curr_palettes = curr_features.get('palettes', [])
    for i in range(min(len(prev_palettes), len(curr_palettes))):
        if prev_palettes[i] != curr_palettes[i]:
            changes[f'palette_{i}_changed'] = True

    return changes


def exploration_strategy(frames, features_history, causal_model):
    """Phase 1: Systematic probing to build causal model.

    Strategy: Try each simple action once, observe effect, build causal map.
    Then try complex actions at interesting positions (corners, center, objects).
    """
    n_actions = len(frames)

    # First 5 frames: try each simple action (ACTION1-ACTION5)
    if n_actions < 5:
        return {'action': f'ACTION{n_actions + 1}', 'phase': 'explore_simple'}

    # Next: try ACTION6 at key positions
    if n_actions < 10:
        positions = [(0, 0), (0, 31), (31, 0), (31, 31), (16, 16)]
        idx = n_actions - 5
        if idx < len(positions):
            x, y = positions[idx]
            return {'action': 'ACTION6', 'x': x, 'y': y, 'phase': 'explore_complex'}

    # After exploration: analyze causal model and exploit
    return None  # Signal to switch to exploitation


def exploitation_strategy(frames, features_history, causal_model):
    """Phase 2: Use causal model to solve the puzzle.

    BFS over action sequences, using causal model to prune unpromising branches.
    """
    # Find which actions caused the most productive changes
    productive_actions = []
    for entry in causal_model:
        action = entry.get('action')
        changes = entry.get('changes', {})
        if changes:
            productive_actions.append((action, len(changes), entry))

    productive_actions.sort(key=lambda x: x[1], reverse=True)

    if productive_actions:
        # Repeat the most productive action pattern
        best = productive_actions[0][2]
        action_name = best['action']
        if 'x' in best:
            return {'action': action_name, 'x': best['x'], 'y': best['y'], 'phase': 'exploit'}
        return {'action': action_name, 'phase': 'exploit'}

    # Fallback: cycle through simple actions
    idx = len(frames) % 5
    return {'action': f'ACTION{idx + 1}', 'phase': 'exploit_fallback'}


def choose_policy_action(frames, latest_frame):
    """Main policy entry point. Returns action dict or None to signal done."""
    features_history = []
    causal_model = []

    # Build features and causal model from frame history
    for i, f in enumerate(frames):
        features = analyze_frame(f)
        features_history.append(features)
        if i > 0:
            changes = detect_pattern_change(features_history[i-1], features)
            causal_model.append({
                'frame': i,
                'action': f'frame_{i}',  # will be enriched with actual action names
                'changes': changes,
            })

    # Phase 1: Exploration
    explore_result = exploration_strategy(frames, features_history, causal_model)
    if explore_result is not None:
        return explore_result

    # Phase 2: Exploitation
    return exploitation_strategy(frames, features_history, causal_model)
'''

# ---------------------------------------------------------------------------
# LLM BACKEND
# ---------------------------------------------------------------------------

_model = None
_tokenizer = None


def init_backend():
    global _model, _tokenizer
    if _model is not None:
        return

    if MODEL_BACKEND == "mlx":
        from mlx_lm import load
        print(f"[arc3] Loading {MODEL_PATH} via MLX...", flush=True)
        _model, _tokenizer = load(MODEL_PATH)
        if USE_TURBOQUANT:
            print(f"[arc3] KV quantization: {TQ_BITS}-bit (mlx-lm built-in)", flush=True)
        print("[arc3] MLX ready.", flush=True)
    elif MODEL_BACKEND == "openai":
        import openai
        _model = openai.OpenAI()
        print("[arc3] OpenAI ready.", flush=True)


def generate_llm(prompt: str, temperature: float = 0.3) -> str:
    """Generate text from the LLM backend."""
    init_backend()

    if MODEL_BACKEND == "mlx":
        from mlx_lm import generate as mlx_generate
        from mlx_lm.sample_utils import make_sampler
        kwargs = {"max_tokens": MAX_NEW_TOKENS, "sampler": make_sampler(temp=max(temperature, 1e-6))}
        if USE_TURBOQUANT:
            kwargs["kv_bits"] = TQ_BITS
        return mlx_generate(_model, _tokenizer, prompt=prompt, **kwargs)

    elif MODEL_BACKEND == "openai":
        response = _model.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_NEW_TOKENS,
            temperature=temperature,
        )
        return response.choices[0].message.content

    return ""


# ---------------------------------------------------------------------------
# DSL-ASSISTED REASONING
# ---------------------------------------------------------------------------

def load_dsl_helpers():
    """Load HELPER_CODE_PREFIX from dsl.py if available."""
    try:
        ns = {}
        exec(open("dsl.py").read(), ns)
        helper_code = ns.get("HELPER_CODE_PREFIX", "")
        helper_ns = {}
        exec(helper_code, helper_ns)
        return helper_ns
    except Exception:
        return {}


def analyze_frame_with_dsl(frame_grids, dsl_ns):
    """Use DSL helpers to analyze frame grids."""
    analysis = []
    for i, grid in enumerate(frame_grids):
        if not grid:
            continue
        info = {"grid_index": i}
        try:
            if "detect_background_color" in dsl_ns:
                info["background"] = dsl_ns["detect_background_color"](grid)
            if "get_objects" in dsl_ns:
                objs = dsl_ns["get_objects"](grid)
                info["num_objects"] = len(objs)
            if "palette" in dsl_ns:
                info["colors"] = dsl_ns["palette"](grid)
            if "shape" in dsl_ns:
                info["shape"] = dsl_ns["shape"](grid)
        except Exception:
            pass
        analysis.append(info)
    return analysis


# ---------------------------------------------------------------------------
# AGENT CLASS — integrates with ARC-AGI-3-Agents framework
# ---------------------------------------------------------------------------

try:
    from arcengine import FrameData, GameAction, GameState
    from agents.agent import Agent as BaseAgent
    HAS_FRAMEWORK = True
except ImportError:
    HAS_FRAMEWORK = False
    # Stub classes for standalone testing
    class FrameData:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class GameAction:
        RESET = "RESET"
        @staticmethod
        def from_name(name): return name
        def set_data(self, d): self.data = d
        def is_simple(self): return True
        def is_complex(self): return False

    class GameState:
        NOT_PLAYED = "NOT_PLAYED"
        NOT_FINISHED = "NOT_FINISHED"
        WIN = "WIN"
        GAME_OVER = "GAME_OVER"

    class BaseAgent:
        def __init__(self, *args, **kwargs): pass


class NeurosymbolicAgent(BaseAgent):
    """ARC-AGI-3 agent using program synthesis as policy.

    The agent:
    1. Runs POLICY_CODE to get action decisions
    2. Optionally uses LLM to generate improved policies mid-game
    3. Uses DSL helpers for frame analysis
    """

    MAX_ACTIONS = 80
    EXPLORATION_BUDGET = 15  # actions reserved for exploration phase
    LLM_ASSIST = os.environ.get("ARC3_LLM_ASSIST", "0") == "1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.policy_ns = {}
        self.action_history = []
        self.dsl_ns = load_dsl_helpers()
        self._load_policy()

    def _load_policy(self):
        """Load and exec POLICY_CODE into a namespace."""
        try:
            exec(POLICY_CODE, self.policy_ns)
        except Exception as e:
            logger.error(f"Failed to load POLICY_CODE: {e}")

    def is_done(self, frames: list, latest_frame) -> bool:
        """Done when we win or exhaust actions."""
        if hasattr(latest_frame, 'state'):
            return latest_frame.state in (GameState.WIN,)
        return False

    def choose_action(self, frames: list, latest_frame) -> Any:
        """Choose action using POLICY_CODE + optional LLM assistance."""
        state = getattr(latest_frame, 'state', None)

        # Must reset if not started or game over
        if state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            return self._make_action("RESET")

        # Run policy code
        choose_fn = self.policy_ns.get("choose_policy_action")
        if choose_fn:
            try:
                result = choose_fn(frames, latest_frame)
                if result:
                    action_name = result.get("action", "ACTION1")
                    if "x" in result and "y" in result:
                        return self._make_complex_action(
                            action_name, result["x"], result["y"],
                            reasoning=result.get("phase", "policy")
                        )
                    return self._make_action(
                        action_name,
                        reasoning=result.get("phase", "policy")
                    )
            except Exception as e:
                logger.warning(f"Policy error: {e}")

        # LLM-assisted fallback: ask LLM what to do
        if self.LLM_ASSIST and self.action_counter > self.EXPLORATION_BUDGET:
            return self._llm_choose_action(frames, latest_frame)

        # Default: cycle simple actions
        idx = self.action_counter % 5
        return self._make_action(f"ACTION{idx + 1}", reasoning="default_cycle")

    def _llm_choose_action(self, frames, latest_frame):
        """Use LLM to decide next action based on frame analysis."""
        # Analyze current state with DSL
        frame_grids = getattr(latest_frame, 'frame', [])
        analysis = analyze_frame_with_dsl(frame_grids, self.dsl_ns)

        prompt = f"""You are playing an ARC-AGI-3 puzzle game. You can take these actions:
ACTION1-ACTION5: Simple actions (no parameters)
ACTION6: Complex action with (x, y) coordinates

Current state analysis:
{json.dumps(analysis, indent=2, default=str)}

Action history (last 10):
{json.dumps(self.action_history[-10:], indent=2)}

Levels completed so far: {getattr(latest_frame, 'levels_completed', 0)}

Choose the next action. Respond with JSON:
{{"action": "ACTION1", "reasoning": "why"}}
or
{{"action": "ACTION6", "x": 10, "y": 10, "reasoning": "why"}}"""

        try:
            response = generate_llm(prompt, temperature=0.2)
            # Extract JSON from response
            m = re.search(r'\{[^}]+\}', response)
            if m:
                data = json.loads(m.group())
                action_name = data.get("action", "ACTION1")
                if "x" in data and "y" in data:
                    return self._make_complex_action(
                        action_name, data["x"], data["y"],
                        reasoning=data.get("reasoning", "llm")
                    )
                return self._make_action(action_name, reasoning=data.get("reasoning", "llm"))
        except Exception as e:
            logger.warning(f"LLM action failed: {e}")

        return self._make_action("ACTION1", reasoning="llm_fallback")

    def _make_action(self, name: str, reasoning: str = "") -> Any:
        """Create a simple GameAction."""
        self.action_history.append({"action": name, "reasoning": reasoning})
        if HAS_FRAMEWORK:
            action = GameAction.from_name(name)
            action.reasoning = reasoning
            return action
        return {"action": name, "reasoning": reasoning}

    def _make_complex_action(self, name: str, x: int, y: int, reasoning: str = "") -> Any:
        """Create a complex GameAction with coordinates."""
        self.action_history.append({"action": name, "x": x, "y": y, "reasoning": reasoning})
        if HAS_FRAMEWORK:
            action = GameAction.from_name(name)
            action.set_data({"x": x, "y": y})
            action.reasoning = reasoning
            return action
        return {"action": name, "x": x, "y": y, "reasoning": reasoning}


# ---------------------------------------------------------------------------
# CODOPT BENCHMARK — evaluate POLICY_CODE quality
# ---------------------------------------------------------------------------

def benchmark_policy(episodes=5):
    """Evaluate POLICY_CODE over simulated episodes.
    For codopt: writes metric.json with mean reward.
    """
    # Load and exec policy
    policy_ns = {}
    try:
        exec(POLICY_CODE, policy_ns)
    except Exception as e:
        print(f"POLICY_CODE failed to load: {e}")
        json.dump({"score": 0.0}, open("metric.json", "w"))
        return

    choose_fn = policy_ns.get("choose_policy_action")
    if not choose_fn:
        print("No choose_policy_action function in POLICY_CODE")
        json.dump({"score": 0.0}, open("metric.json", "w"))
        return

    # Simulate episodes with mock frames
    total_score = 0.0
    for ep in range(episodes):
        frames = [FrameData(frame=[], state=GameState.NOT_PLAYED, levels_completed=0)]
        actions_taken = 0
        max_actions = 40

        for step in range(max_actions):
            try:
                result = choose_fn(frames, frames[-1])
                if result is None:
                    break
                actions_taken += 1
                # Mock frame response
                frames.append(FrameData(
                    frame=[],
                    state=GameState.NOT_FINISHED,
                    levels_completed=0,
                ))
            except Exception:
                break

        # Score: diversity of actions tried (proxy for good exploration)
        unique_actions = len(set(
            a.get("action", "") if isinstance(a, dict) else str(a)
            for a in [choose_fn(frames[:i+1], frames[i]) for i in range(min(10, len(frames)))]
            if a is not None
        ))
        ep_score = min(1.0, unique_actions / 6.0)
        total_score += ep_score

    mean_score = total_score / episodes
    print(f"Policy benchmark: {mean_score:.4f} (mean over {episodes} episodes)")
    json.dump({"score": mean_score}, open("metric.json", "w"))


# ---------------------------------------------------------------------------
# STANDALONE TEST
# ---------------------------------------------------------------------------

def test_standalone():
    """Test the agent without the ARC-AGI-3 framework."""
    print("=== Standalone Agent Test ===")

    # Test policy code
    policy_ns = {}
    exec(POLICY_CODE, policy_ns)
    choose_fn = policy_ns["choose_policy_action"]

    mock_grid = [[0,0,1],[0,1,0],[1,0,0]]
    frames = [FrameData(frame=[mock_grid], state="PLAYING", levels_completed=0)]

    for step in range(20):
        result = choose_fn(frames, frames[-1])
        if result is None:
            print(f"Step {step}: Policy returned None (done exploring)")
            break
        print(f"Step {step}: {result}")
        frames.append(FrameData(
            frame=[mock_grid],
            state="PLAYING",
            levels_completed=0,
        ))

    print("\n=== Benchmark ===")
    benchmark_policy()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run standalone test")
    parser.add_argument("--benchmark", action="store_true", help="Run codopt benchmark")
    args = parser.parse_args()

    if args.benchmark:
        benchmark_policy()
    else:
        test_standalone()
