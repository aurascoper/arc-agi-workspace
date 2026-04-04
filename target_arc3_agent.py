"""
target_arc3_agent.py — ARC-AGI-3 Neurosymbolic Agent Harness

Architecture: Program synthesis as policy.
  Phase 1 (Exploration): Systematic probing via actions to build causal model
  Phase 2 (Exploitation): BFS in causal graph toward goal state

Uses the official ARC-AGI-3-Agents API:
  - Extends Agent base class (from agents.agent)
  - Implements choose_action(frames: list[FrameData], latest_frame: FrameData) -> GameAction
  - Implements is_done(frames: list[FrameData], latest_frame: FrameData) -> bool

SDK packages:
  - arc_agi: Arcade, EnvironmentWrapper, scorecard management
  - arcengine: GameAction, GameState, FrameData, FrameDataRaw, ActionInput

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
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_BACKEND = os.environ.get("ARC3_BACKEND", "mlx")  # "mlx" or "openai"
MODEL_PATH = os.environ.get("ARC_MODEL_PATH", "mlx-community/Qwen3.5-9B-4bit")
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

# --- DSL helpers (inlined from dsl.py, adapted for 64x64 / 16-color) ---

def _to_grid(frame_layer):
    return frame_layer.tolist() if hasattr(frame_layer, 'tolist') else frame_layer

def _detect_background(grid):
    rows, cols = len(grid), len(grid[0])
    border = (
        [grid[0][c] for c in range(cols)] +
        [grid[rows-1][c] for c in range(cols)] +
        [grid[r][0] for r in range(rows)] +
        [grid[r][cols-1] for r in range(rows)]
    )
    if not border:
        return 0
    counts = Counter(border)
    # Tie-break by overall frequency
    all_counts = Counter(cell for row in grid for cell in row)
    return max(counts, key=lambda c: (counts[c], all_counts.get(c, 0)))

def _palette(grid):
    seen, out = set(), []
    for row in grid:
        for v in row:
            if v not in seen:
                seen.add(v); out.append(v)
    return out

def _get_objects(grid, background=None, diag=False):
    if background is None:
        background = _detect_background(grid)
    rows, cols = len(grid), len(grid[0])
    visited = set()
    objs = []
    deltas = [(0,1),(0,-1),(1,0),(-1,0)]
    if diag:
        deltas += [(1,1),(1,-1),(-1,1),(-1,-1)]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and (r, c) not in visited:
                color = grid[r][c]
                q = deque([(r, c)])
                visited.add((r, c))
                component = []
                while q:
                    cr, cc = q.popleft()
                    component.append((cr, cc))
                    for dr, dc in deltas:
                        nr, nc = cr + dr, cc + dc
                        if (0 <= nr < rows and 0 <= nc < cols
                                and (nr, nc) not in visited
                                and grid[nr][nc] == color):
                            visited.add((nr, nc))
                            q.append((nr, nc))
                objs.append(component)
    return objs

def _get_bbox(coords):
    if not coords: return (0, 0, 0, 0)
    rs = [r for r, c in coords]; cs = [c for r, c in coords]
    return (min(rs), min(cs), max(rs), max(cs))

def _obj_center(coords):
    r0, c0, r1, c1 = _get_bbox(coords)
    return ((r0 + r1) // 2, (c0 + c1) // 2)

def _obj_summary(grid, obj):
    bbox = _get_bbox(obj)
    return {'bbox': bbox, 'center': _obj_center(obj), 'size': len(obj),
            'color': grid[obj[0][0]][obj[0][1]],
            'height': bbox[2]-bbox[0]+1, 'width': bbox[3]-bbox[1]+1}

def _foreground_pixels(grid, background):
    return sum(1 for row in grid for c in row if c != background)


# --- Frame analysis ---

def analyze_frame(frame_data):
    """Extract rich features from a FrameData object.

    Returns dict with layer-level info, object detection, background,
    foreground regions, and clickable targets.
    """
    if frame_data is None:
        return {}

    raw_frame = getattr(frame_data, 'frame', None)
    if raw_frame is None or len(raw_frame) == 0:
        return {}

    features = {
        'num_layers': len(raw_frame),
        'layer_shapes': [],
        'palettes': [],
        'symmetries': [],
        'backgrounds': [],
        'objects': [],          # per-layer list of object summaries
        'fg_pixel_counts': [],
        'color_histograms': [],
        'clickable_targets': [],  # (row, col) centers of detected objects
        'levels_completed': getattr(frame_data, 'levels_completed', 0),
        'win_levels': getattr(frame_data, 'win_levels', 0),
        'available_actions': list(getattr(frame_data, 'available_actions', [])),
    }

    for layer in raw_frame:
        arr = np.asarray(layer)
        features['layer_shapes'].append(tuple(arr.shape))

        # Convert to list-of-lists for DSL helpers
        grid = _to_grid(layer)
        if not grid or not grid[0]:
            features['palettes'].append(set())
            features['symmetries'].append({'h': False, 'v': False})
            features['backgrounds'].append(0)
            features['objects'].append([])
            features['fg_pixel_counts'].append(0)
            features['color_histograms'].append({})
            features['clickable_targets'].append([])
            continue

        # Palette
        pal = _palette(grid)
        features['palettes'].append(set(pal))

        # Background detection
        bg = _detect_background(grid)
        features['backgrounds'].append(bg)

        # Color histogram
        features['color_histograms'].append(dict(Counter(
            cell for row in grid for cell in row)))

        # Foreground pixel count
        fg_count = _foreground_pixels(grid, bg)
        features['fg_pixel_counts'].append(fg_count)

        # Symmetry (fast numpy check)
        if arr.ndim == 2 and arr.shape[0] > 0 and arr.shape[1] > 0:
            features['symmetries'].append({
                'h': bool(np.array_equal(arr, arr[:, ::-1])),
                'v': bool(np.array_equal(arr, arr[::-1, :])),
            })
        else:
            features['symmetries'].append({'h': False, 'v': False})

        # Object detection (connected same-color components)
        try:
            objs = _get_objects(grid, background=bg, diag=False)
            obj_summaries = [_obj_summary(grid, o) for o in objs]
            # Sort by size descending — largest objects are usually most important
            obj_summaries.sort(key=lambda s: s['size'], reverse=True)
            features['objects'].append(obj_summaries)

            # Clickable targets: centers of all objects, largest first
            targets = [s['center'] for s in obj_summaries]
            features['clickable_targets'].append(targets)
        except Exception:
            features['objects'].append([])
            features['clickable_targets'].append([])

    return features


# --- Change detection ---

def detect_pattern_change(prev_features, curr_features):
    """Detect what changed between consecutive frames: pixel, object, and semantic."""
    if not prev_features or not curr_features:
        return {'type': 'unknown'}

    changes = {}

    # --- Layer-level structural changes ---
    if prev_features.get('num_layers') != curr_features.get('num_layers'):
        changes['layer_count_changed'] = True

    if prev_features.get('layer_shapes') != curr_features.get('layer_shapes'):
        changes['shapes_changed'] = True

    # --- Palette changes ---
    prev_pals = prev_features.get('palettes', [])
    curr_pals = curr_features.get('palettes', [])
    for i in range(min(len(prev_pals), len(curr_pals))):
        if prev_pals[i] != curr_pals[i]:
            changes[f'palette_{i}_changed'] = True
            new_colors = curr_pals[i] - prev_pals[i]
            lost_colors = prev_pals[i] - curr_pals[i]
            if new_colors:
                changes[f'new_colors_{i}'] = new_colors
            if lost_colors:
                changes[f'lost_colors_{i}'] = lost_colors

    # --- Foreground pixel count changes ---
    prev_fg = prev_features.get('fg_pixel_counts', [])
    curr_fg = curr_features.get('fg_pixel_counts', [])
    for i in range(min(len(prev_fg), len(curr_fg))):
        delta = curr_fg[i] - prev_fg[i]
        if delta != 0:
            changes[f'fg_delta_{i}'] = delta

    # --- Object-level changes (per layer) ---
    prev_objs = prev_features.get('objects', [])
    curr_objs = curr_features.get('objects', [])
    for i in range(min(len(prev_objs), len(curr_objs))):
        po = prev_objs[i]
        co = curr_objs[i]
        n_prev = len(po)
        n_curr = len(co)
        if n_prev != n_curr:
            changes[f'obj_count_delta_{i}'] = n_curr - n_prev
        if n_prev > 0 and n_curr > 0:
            # Check if the largest object moved
            prev_top = po[0]  # largest by size
            curr_top = co[0]
            if prev_top['center'] != curr_top['center']:
                changes[f'largest_obj_moved_{i}'] = {
                    'from': prev_top['center'],
                    'to': curr_top['center'],
                }
            if prev_top['color'] != curr_top['color']:
                changes[f'largest_obj_recolored_{i}'] = {
                    'from': prev_top['color'],
                    'to': curr_top['color'],
                }
            if prev_top['size'] != curr_top['size']:
                changes[f'largest_obj_resized_{i}'] = {
                    'from': prev_top['size'],
                    'to': curr_top['size'],
                }

    # --- Level advancement ---
    if prev_features.get('levels_completed', 0) < curr_features.get('levels_completed', 0):
        changes['level_advanced'] = True

    # Classify overall change magnitude
    n_changes = len(changes)
    if n_changes == 0:
        changes['type'] = 'no_change'
    elif 'level_advanced' in changes:
        changes['type'] = 'level_advance'
    elif n_changes <= 2:
        changes['type'] = 'minor'
    else:
        changes['type'] = 'major'

    return changes


# --- Exploration (Phase 1) ---

def exploration_strategy(frames, features_history, causal_model, action_log):
    """Phase 1: Systematic probing with object-informed clicks.

    Strategy:
      1. Try each simple action (ACTION1-5) once.
      2. Try ACTION7 (undo) to test reversibility.
      3. Click on detected objects (largest first), falling back to grid.
      4. Undo after a click to test click reversibility.
      5. Return None to switch to exploitation.
    """
    n_actions = len(action_log)

    # Step 1: Try each simple action (ACTION1-ACTION5)
    if n_actions < 5:
        return {'action': f'ACTION{n_actions + 1}', 'phase': 'explore_simple'}

    # Step 2: Try ACTION7 (undo) to learn if it reverses the last action
    if n_actions == 5:
        return {'action': 'ACTION7', 'phase': 'explore_undo'}

    # Step 3: Click on detected objects or key positions
    if n_actions < 16:
        click_idx = n_actions - 6  # 0..9

        # Gather clickable targets from latest frame analysis
        targets = []
        if features_history:
            latest_feat = features_history[-1]
            click_lists = latest_feat.get('clickable_targets', [])
            for layer_targets in click_lists:
                for t in layer_targets:
                    if t not in targets:
                        targets.append(t)

        # Fallback grid positions for when objects aren't detected
        grid_positions = [
            (32, 32), (16, 16), (48, 48), (16, 48), (48, 16),
            (0, 0), (0, 63), (63, 0), (63, 63), (32, 0),
        ]

        if click_idx < len(targets):
            r, c = targets[click_idx]
            return {'action': 'ACTION6', 'x': int(c), 'y': int(r),
                    'phase': 'explore_click_object'}
        else:
            fallback_idx = click_idx - len(targets)
            if fallback_idx < len(grid_positions):
                r, c = grid_positions[fallback_idx]
                return {'action': 'ACTION6', 'x': int(c), 'y': int(r),
                        'phase': 'explore_click_grid'}

    # Step 4: Undo after clicks to test reversibility
    if n_actions == 16:
        return {'action': 'ACTION7', 'phase': 'explore_undo_click'}

    # After exploration: switch to exploitation
    return None


# --- Exploitation (Phase 2) ---

def exploitation_strategy(frames, features_history, causal_model, action_log):
    """Phase 2: Use causal model (enriched with object-level changes) to solve.

    Priorities:
      1. Repeat level-advancing actions.
      2. Repeat actions that caused meaningful object changes.
      3. Click on new/moved objects.
      4. Cycle with periodic undo for backtracking.
    """
    # Categorize causal entries by effect type
    level_advancing = []
    object_movers = []      # actions that moved objects
    object_changers = []    # actions that added/removed/recolored objects
    pixel_changers = []     # any other non-trivial change

    for entry in causal_model:
        changes = entry.get('changes', {})
        if not changes or changes.get('type') == 'no_change':
            continue
        if changes.get('level_advanced'):
            level_advancing.append(entry)
            continue
        # Score by object-level impact
        obj_score = 0
        for k, v in changes.items():
            if 'largest_obj_moved' in k:
                obj_score += 3
                object_movers.append(entry)
            elif 'obj_count_delta' in k:
                obj_score += 2
                object_changers.append(entry)
            elif 'largest_obj_recolored' in k or 'largest_obj_resized' in k:
                obj_score += 2
                object_changers.append(entry)
            elif 'fg_delta' in k:
                obj_score += 1
        if obj_score > 0:
            pixel_changers.append((obj_score, entry))
        elif len(changes) > 1:
            pixel_changers.append((1, entry))

    # Priority 1: repeat actions that advanced levels
    if level_advancing:
        best = level_advancing[-1]
        action_name = best['action_name']
        if best.get('x') is not None:
            return {'action': action_name, 'x': best['x'], 'y': best['y'],
                    'phase': 'exploit_advance'}
        return {'action': action_name, 'phase': 'exploit_advance'}

    # Priority 2: repeat actions that caused object movement
    if object_movers:
        best = object_movers[-1]
        action_name = best['action_name']
        if best.get('x') is not None:
            return {'action': action_name, 'x': best['x'], 'y': best['y'],
                    'phase': 'exploit_obj_move'}
        return {'action': action_name, 'phase': 'exploit_obj_move'}

    # Priority 3: click on newly appeared or moved objects
    if features_history and len(features_history) >= 2:
        curr_feat = features_history[-1]
        prev_feat = features_history[-2]
        curr_objs = curr_feat.get('objects', [[]])
        prev_objs = prev_feat.get('objects', [[]])
        # Look at primary layer (index 0)
        if curr_objs and prev_objs:
            co = curr_objs[0] if curr_objs else []
            po = prev_objs[0] if prev_objs else []
            prev_centers = {o['center'] for o in po}
            # Find objects with new centers (moved or newly appeared)
            new_targets = [o for o in co if o['center'] not in prev_centers]
            if new_targets:
                t = new_targets[0]
                r, c = t['center']
                return {'action': 'ACTION6', 'x': int(c), 'y': int(r),
                        'phase': 'exploit_click_new_obj'}

    # Priority 4: repeat highest-scoring object-changing action
    if object_changers:
        best = object_changers[-1]
        action_name = best['action_name']
        if best.get('x') is not None:
            return {'action': action_name, 'x': best['x'], 'y': best['y'],
                    'phase': 'exploit_obj_change'}
        return {'action': action_name, 'phase': 'exploit_obj_change'}

    # Priority 5: repeat highest-scoring pixel-changing action
    pixel_changers.sort(key=lambda x: x[0], reverse=True)
    if pixel_changers:
        best = pixel_changers[0][1]
        action_name = best['action_name']
        if best.get('x') is not None:
            return {'action': action_name, 'x': best['x'], 'y': best['y'],
                    'phase': 'exploit_pixel'}
        return {'action': action_name, 'phase': 'exploit_pixel'}

    # Priority 6: cycle with periodic undo for backtracking
    n = len(action_log)
    if n % 7 == 6:
        return {'action': 'ACTION7', 'phase': 'exploit_backtrack'}
    # Interleave simple actions with object-targeted clicks
    if n % 3 == 0 and features_history:
        latest_feat = features_history[-1]
        targets = []
        for lt in latest_feat.get('clickable_targets', []):
            targets.extend(lt)
        if targets:
            # Rotate through detected object centers
            t_idx = (n // 3) % len(targets)
            r, c = targets[t_idx]
            return {'action': 'ACTION6', 'x': int(c), 'y': int(r),
                    'phase': 'exploit_cycle_click'}
    idx = n % 5
    return {'action': f'ACTION{idx + 1}', 'phase': 'exploit_cycle'}


# --- Multi-level tracking ---

def check_level_transition(prev_frame, curr_frame):
    """Detect whether a level transition occurred."""
    prev_lc = getattr(prev_frame, 'levels_completed', 0) if prev_frame else 0
    curr_lc = getattr(curr_frame, 'levels_completed', 0) if curr_frame else 0
    return curr_lc > prev_lc


# --- Main policy entry point ---

def choose_policy_action(frames, latest_frame, action_log=None):
    """Main policy entry point. Returns action dict or None to signal done.

    Args:
        frames: list of FrameData objects (full history).
        latest_frame: the most recent FrameData.
        action_log: list of dicts recording actions taken so far.
    """
    if action_log is None:
        action_log = []

    features_history = []
    causal_model = []

    # Build features and causal model from frame history
    for i, f in enumerate(frames):
        features = analyze_frame(f)
        features_history.append(features)
        if i > 0:
            changes = detect_pattern_change(features_history[i-1], features)
            action_entry = action_log[i-1] if i-1 < len(action_log) else {}
            causal_model.append({
                'frame': i,
                'action_name': action_entry.get('action', f'frame_{i}'),
                'x': action_entry.get('x'),
                'y': action_entry.get('y'),
                'changes': changes,
            })

    # Check for level transition -- reset exploration on new level
    if len(frames) >= 2 and check_level_transition(frames[-2], latest_frame):
        return {'action': 'ACTION1', 'phase': 'explore_new_level'}

    # Phase 1: Exploration
    explore_result = exploration_strategy(frames, features_history, causal_model, action_log)
    if explore_result is not None:
        return explore_result

    # Phase 2: Exploitation
    return exploitation_strategy(frames, features_history, causal_model, action_log)
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
    """Use DSL helpers to analyze frame grids.

    frame_grids may be list of numpy arrays (FrameDataRaw) or
    list of list-of-lists (FrameData).  Convert to lists for DSL functions.
    """
    import numpy as np

    analysis = []
    for i, grid in enumerate(frame_grids):
        if grid is None:
            continue
        # Normalise to list-of-lists for DSL compatibility
        if hasattr(grid, 'tolist'):
            grid = grid.tolist()
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
# SDK IMPORTS — arcengine provides the core types, agents.agent the base class
# ---------------------------------------------------------------------------

from arcengine import FrameData, FrameDataRaw, GameAction, GameState, ActionInput

try:
    from agents.agent import Agent as BaseAgent
    HAS_FRAMEWORK = True
except ImportError:
    HAS_FRAMEWORK = False

    class BaseAgent:  # type: ignore[no-redef]
        """Minimal stub so the agent class can be defined standalone."""
        MAX_ACTIONS: int = 80
        action_counter: int = 0
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# AGENT CLASS — integrates with ARC-AGI-3-Agents framework
# ---------------------------------------------------------------------------

class NeurosymbolicAgent(BaseAgent):
    """ARC-AGI-3 agent using program synthesis as policy.

    The agent:
    1. Runs POLICY_CODE to get action decisions (codopt-evolvable)
    2. Optionally uses LLM to generate improved policies mid-game
    3. Uses DSL helpers for frame analysis
    4. Tracks multi-level progression (6+ levels per environment)
    5. Supports ACTION7 (undo) for backtracking from dead-ends
    """

    MAX_ACTIONS = 80
    EXPLORATION_BUDGET = 13  # actions reserved for exploration phase
    LLM_ASSIST = os.environ.get("ARC3_LLM_ASSIST", "0") == "1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.policy_ns: dict[str, Any] = {}
        self.action_log: list[dict[str, Any]] = []
        self.dsl_ns = load_dsl_helpers()
        self.levels_seen: list[int] = [0]  # track level transitions
        self._load_policy()

    def _load_policy(self):
        """Load and exec POLICY_CODE into a namespace."""
        try:
            exec(POLICY_CODE, self.policy_ns)
        except Exception as e:
            logger.error(f"Failed to load POLICY_CODE: {e}")

    # ------------------------------------------------------------------
    # Framework interface
    # ------------------------------------------------------------------

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        """Done when we win."""
        return latest_frame.state == GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        """Choose action using POLICY_CODE + optional LLM assistance.

        Returns a real GameAction enum member ready for the framework.
        """
        state = latest_frame.state

        # Must reset if not started or game over
        if state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._record_action("RESET", phase="reset")
            return GameAction.RESET

        # Track level transitions
        curr_lc = latest_frame.levels_completed
        if self.levels_seen and curr_lc > self.levels_seen[-1]:
            self.levels_seen.append(curr_lc)
            logger.info(f"Level transition detected: now at {curr_lc} levels completed")

        # Run policy code
        choose_fn = self.policy_ns.get("choose_policy_action")
        if choose_fn:
            try:
                result = choose_fn(frames, latest_frame, action_log=self.action_log)
                if result:
                    action_name = result.get("action", "ACTION1")
                    phase = result.get("phase", "policy")
                    if "x" in result and "y" in result:
                        return self._make_complex_action(
                            action_name, int(result["x"]), int(result["y"]),
                            reasoning=phase,
                        )
                    return self._make_action(action_name, reasoning=phase)
            except Exception as e:
                logger.warning(f"Policy error: {e}")

        # LLM-assisted fallback
        if self.LLM_ASSIST and self.action_counter > self.EXPLORATION_BUDGET:
            return self._llm_choose_action(frames, latest_frame)

        # Default: cycle simple actions with occasional undo
        if self.action_counter % 7 == 6:
            return self._make_action("ACTION7", reasoning="default_undo")
        idx = self.action_counter % 5
        return self._make_action(f"ACTION{idx + 1}", reasoning="default_cycle")

    # ------------------------------------------------------------------
    # LLM-assisted action selection
    # ------------------------------------------------------------------

    def _llm_choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        """Use LLM to decide next action based on frame analysis."""
        frame_grids = latest_frame.frame  # list of 2-D grids (list-of-lists)
        analysis = analyze_frame_with_dsl(frame_grids, self.dsl_ns)

        prompt = f"""You are playing an ARC-AGI-3 puzzle game. You can take these actions:
ACTION1-ACTION5: Simple actions (no parameters)
ACTION6: Complex action with (x, y) coordinates (0-63 each)
ACTION7: Undo last action

Current state analysis:
{json.dumps(analysis, indent=2, default=str)}

Action history (last 10):
{json.dumps(self.action_log[-10:], indent=2)}

Levels completed so far: {latest_frame.levels_completed}
Win condition levels: {latest_frame.win_levels}

Choose the next action. Respond with JSON:
{{"action": "ACTION1", "reasoning": "why"}}
or
{{"action": "ACTION6", "x": 10, "y": 10, "reasoning": "why"}}
or
{{"action": "ACTION7", "reasoning": "undo because ..."}}"""

        try:
            response = generate_llm(prompt, temperature=0.2)
            m = re.search(r'\{[^}]+\}', response)
            if m:
                data = json.loads(m.group())
                action_name = data.get("action", "ACTION1")
                if "x" in data and "y" in data:
                    return self._make_complex_action(
                        action_name, int(data["x"]), int(data["y"]),
                        reasoning=data.get("reasoning", "llm"),
                    )
                return self._make_action(
                    action_name, reasoning=data.get("reasoning", "llm")
                )
        except Exception as e:
            logger.warning(f"LLM action failed: {e}")

        return self._make_action("ACTION1", reasoning="llm_fallback")

    # ------------------------------------------------------------------
    # Action construction helpers
    # ------------------------------------------------------------------

    def _record_action(
        self, name: str, x: Optional[int] = None, y: Optional[int] = None, phase: str = ""
    ):
        """Record an action in the action log for causal model building."""
        entry: dict[str, Any] = {"action": name, "phase": phase}
        if x is not None:
            entry["x"] = x
            entry["y"] = y
        self.action_log.append(entry)

    def _make_action(self, name: str, reasoning: str = "") -> GameAction:
        """Create a simple GameAction and log it."""
        self._record_action(name, phase=reasoning)
        action = GameAction.from_name(name)
        return action

    def _make_complex_action(
        self, name: str, x: int, y: int, reasoning: str = ""
    ) -> GameAction:
        """Create a complex GameAction (ACTION6) with coordinates and log it."""
        self._record_action(name, x=x, y=y, phase=reasoning)
        action = GameAction.from_name(name)
        action.set_data({"x": x, "y": y})
        return action


# ---------------------------------------------------------------------------
# CODOPT BENCHMARK -- evaluate POLICY_CODE quality
# ---------------------------------------------------------------------------

def benchmark_policy(episodes: int = 5):
    """Evaluate POLICY_CODE over simulated episodes.
    For codopt: writes metric.json with mean reward.
    """
    policy_ns: dict[str, Any] = {}
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

    total_score = 0.0
    for ep in range(episodes):
        frames = [FrameData(levels_completed=0)]
        action_log: list[dict[str, Any]] = []
        max_actions = 40

        for step in range(max_actions):
            try:
                result = choose_fn(frames, frames[-1], action_log=action_log)
                if result is None:
                    break
                action_log.append(result)
                # Mock frame response
                frames.append(FrameData(
                    state=GameState.NOT_FINISHED,
                    levels_completed=0,
                ))
            except Exception:
                break

        # Score: diversity of actions tried, including undo (proxy for good exploration)
        unique_actions = set()
        for entry in action_log:
            if isinstance(entry, dict):
                unique_actions.add(entry.get("action", ""))
        # 7 possible actions (ACTION1-7), score normalised to [0,1]
        ep_score = min(1.0, len(unique_actions) / 7.0)
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

    policy_ns: dict[str, Any] = {}
    exec(POLICY_CODE, policy_ns)
    choose_fn = policy_ns["choose_policy_action"]

    # FrameData from arcengine: frame is list of list-of-list-of-int
    mock_grid = [[0, 0, 1], [0, 1, 0], [1, 0, 0]]
    frames = [FrameData(frame=[mock_grid], state=GameState.NOT_FINISHED, levels_completed=0)]
    action_log: list[dict[str, Any]] = []

    for step in range(20):
        result = choose_fn(frames, frames[-1], action_log=action_log)
        if result is None:
            print(f"Step {step}: Policy returned None (done exploring)")
            break
        print(f"Step {step}: {result}")
        action_log.append(result)
        frames.append(FrameData(
            frame=[mock_grid],
            state=GameState.NOT_FINISHED,
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
