#!/bin/bash

#SBATCH --job-name=rag_llama3_server
#SBATCH --partition=gpu                  # Adjust to your cluster's GPU partition name
#SBATCH --gres=gpu:1                     # Request 1 GPU
#SBATCH --cpus-per-task=8                # Request 8 CPU cores
#SBATCH --mem=64G                        # Request 64 GB system memory
#SBATCH --time=12:00:00                  # Adjusted runtime
#SBATCH --output=results/job_%j.log       # Stdout log path (%j expands to job ID)
#SBATCH --error=results/job_%j.err        # Stderr log path

# 1. Environment & Paths (SCRIPT_DIR defined FIRST)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load environment variables from .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
  eval $(python3 -c "
with open('$PROJECT_ROOT/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip().strip('\"\'')
            print(f'export {k}=\"{v}\"')
" 2>/dev/null)
fi

export PATH="/home/udaripa/projects/.conda/envs/ush_venv/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT"
export HF_HUB_DISABLE_XET=1

# 2. Configuration & Model Selection
MODEL=$(python3 -c "import app.config as cfg; print(cfg.RETRIEVAL_LLM_MODEL)")
RAG_PORT=11434
HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"

# 3. Helper Functions
cleanup_port() {
  local port=$1
  local pid=$(lsof -t -i:$port)
  if [ -n "$pid" ]; then
    echo "⚠️ Port $port is in use by PID $pid. Killing process..."
    kill -9 $pid
    sleep 2
  fi
}

wait_for_port() {
  local port=$1
  echo "⏳ Waiting for vLLM API on port $port to be ready..."
  while ! curl -s http://localhost:$port/v1/models | grep -q "data"; do
    sleep 5
  done
  echo "✅ Port $port is fully ready!"
}

# 4. Clean previous port & Launch vLLM
cleanup_port $RAG_PORT

echo "================================================================="
echo "  🎯 STARTING MODEL: $MODEL on port $RAG_PORT"
echo "================================================================="

HF_TOKEN=$HF_TOKEN python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port $RAG_PORT \
  --host 0.0.0.0 \
  --gpu-memory-utilization 0.85 \
  --enable-chunked-prefill &
RAG_PID=$!

# Wait for server to become ready
wait_for_port $RAG_PORT

echo "🚀 vLLM server is running (PID: $RAG_PID). Keeping job alive..."
# Keeps the script and SLURM job alive while vLLM runs
wait $RAG_PID
