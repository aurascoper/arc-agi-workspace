#!/bin/bash
# setup.sh — Set up the ARC-AGI workspace environment
# Uses the turboquant-mlx venv which has MLX + turboquant + mlx-lm installed

VENV=/Users/aurascoper/Developer/arc_agi/turboquant-mlx/.venv

echo "=== ARC-AGI Workspace Setup ==="
echo "Using venv: $VENV"
echo ""

# Verify venv
if [ ! -f "$VENV/bin/python" ]; then
    echo "ERROR: turboquant venv not found at $VENV"
    echo "Run: cd ~/Developer/arc_agi/turboquant-mlx && python3 -m venv .venv && pip install -e . && pip install mlx-lm"
    exit 1
fi

# Create symlink for convenience
ln -sf "$VENV" .venv 2>/dev/null

echo "Available commands:"
echo "  source .venv/bin/activate"
echo ""
echo "  # Local MLX eval (single task):"
echo "  python target_mlx_arc.py arc_agi_2_data/training/<task>.json"
echo ""
echo "  # Outer evolution loop:"
echo "  python evolve_qwen_arc.py --rounds 3"
echo ""
echo "  # codopt inner loop:"
echo "  ./run_codopt.sh"
echo ""
echo "  # ARC-AGI-3 agent test:"
echo "  python target_arc3_agent.py --test"
echo ""
echo "  # Benchmark DSL:"
echo "  python benchmark_dsl.py"
echo ""
echo "Environment variables:"
echo "  ARC_MODEL_PATH=mlx-community/Qwen3-30B-A3B-4bit  (default)"
echo "  USE_TURBOQUANT=1         (enable KV cache compression)"
echo "  TQ_BITS=3                (3-bit quantization, safe for M4)"
echo "  ARC3_LLM_ASSIST=1        (enable LLM-assisted ARC-3 agent)"
echo ""
echo "Model: Qwen3-30B-A3B-4bit (MoE, 30B total, 3B active, ~7GB)"
echo "Setup complete."
