#!/bin/bash

#SBATCH --job-name=rag_llm_comparison
#SBATCH --partition=gpu                  # Adjust to your cluster's GPU partition name
#SBATCH --gres=gpu:1                     # Request 1 GPU
#SBATCH --cpus-per-task=8                # Request 8 CPU cores
#SBATCH --mem=64G                        # Request 64 GB system memory
#SBATCH --time=03:00:00                  # 3 hours max execution time
#SBATCH --output=results/job_%j.log       # Stdout log path (%j expands to job ID)
#SBATCH --error=results/job_%j.err        # Stderr log path

# Prepend virtual environment path to ensure the correct python is used
export PATH="/home/udaripa/projects/.conda/envs/ush_venv/bin:$PATH"
export PYTHONPATH="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HF_HUB_DISABLE_XET=1
MODEL=$(python3 -c "import app.config as cfg; print(cfg.RETRIEVAL_LLM_MODELS[0])")
RAG_PORT=11434
HF_TOKEN="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"
LIMIT=50
CONCURRENCY=5

# Models to test sequentially
# MODELS=(
#   "meta-llama/Meta-Llama-3-8B-Instruct"
#   "mistralai/Mistral-7B-Instruct-v0.3"
#   "google/gemma-2-9b-it"
# )

# Function to check if a port is in use and kill the process using it
cleanup_port() {
  local port=$1
  local pid=$(lsof -t -i:$port)
  if [ -n "$pid" ]; then
    echo "⚠️ Port $port is in use by PID $pid. Killing process..."
    kill -9 $pid
    sleep 2
  fi
}

# Function to wait for a port's /v1/models endpoint to return HTTP 200
wait_for_port() {
  local port=$1
  echo "⏳ Waiting for vLLM API on port $port to be ready..."
  while ! curl -s http://localhost:$port/v1/models | grep -q "data"; do
    sleep 5
  done
  echo "✅ Port $port is fully ready!"
}

# Ensure ports 11434 and 11435 are clean before starting
cleanup_port $RAG_PORT

# 1. Start the Judge model (kept running throughout the entire experiment)
# No judge model needed for this experiment

# Wait for the judge model to start
# No judge model to wait for

# 2. Iterate and evaluate each model sequentially on port 11434
echo "================================================================="
echo "  🎯 STARTING MODEL: $MODEL"
echo "================================================================="

# Clean up the port from previous run if any
cleanup_port $RAG_PORT

echo "🚀 Launching vLLM server for $MODEL on port $RAG_PORT..."
# Allocating 0.45 VRAM allows plenty of KV cache space for a single model on an 80GB card
HF_TOKEN=$HF_TOKEN python -m vllm.entrypoints.openai.api_server \
  --model $MODEL \
  --port $RAG_PORT \
  --host 0.0.0.0 \
  --gpu-memory-utilization 0.45 \
  --enable-chunked-prefill &
RAG_PID=$!

# Wait for this RAG model to initialize
wait_for_port $RAG_PORT

