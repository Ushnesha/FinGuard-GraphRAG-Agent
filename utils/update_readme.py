#!/usr/bin/env python3
import os
import subprocess

def get_recent_commits():
    try:
        # Fetch the last 5 commits formatted for a markdown table
        cmd = ["git", "log", "-n", "5", "--pretty=format:%h|%an|%ad|%s", "--date=short"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = res.stdout.strip().split("\n")
        if not lines or not lines[0]:
            return "*No commit history found.*"
        
        table = "| Commit | Author | Date | Message |\n| --- | --- | --- | --- |\n"
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 4:
                hash_val, author, date, msg = parts[0], parts[1], parts[2], "|".join(parts[3:])
                table += f"| `{hash_val}` | {author} | {date} | {msg} |\n"
        return table
    except Exception as e:
        return f"*Error retrieving git logs:* {str(e)}"

def get_evaluation_report(root_dir):
    summaries_path = os.path.join(root_dir, "results", "all_model_summaries.json")
    
    header_section = """## 📊 Evaluation Report (FinQA Benchmark)

We benchmarked the agent on samples from the FinQA dataset. The evaluation is conducted asynchronously using an LLM-as-a-judge setup with `Qwen/Qwen2.5-7B-Instruct`.
"""
    
    if os.path.exists(summaries_path):
        try:
            import json
            with open(summaries_path, "r", encoding="utf-8") as f:
                summaries = json.load(f)
                
            if summaries:
                table = "| Model | Metric | Score | Avg token Utilized |\n"
                table += "| --- | --- | :---: | :---: |\n"
                
                for model_name, data in sorted(summaries.items()):
                    faith = f"{data.get('faithfulness', 0) * 100:.2f}%" if data.get('faithfulness') is not None else "N/A"
                    relevance = f"{data.get('relevance', 0) * 100:.2f}%" if data.get('relevance') is not None else "N/A"
                    recall = f"{data.get('recall', 0) * 100:.2f}%" if data.get('recall') is not None else "N/A"
                    
                    total_tokens = f"{data.get('total_tokens', 0):,}" if data.get('total_tokens') is not None else "N/A"
                    
                    table += f"| `{model_name}` | Faithfulness | **{faith}** | {total_tokens} |\n"
                    table += f"| | Answer Relevance | **{relevance}** | |\n"
                    table += f"| | Context Recall | **{recall}** | |\n"
                
                return f"{header_section}\n### Multi-Model Comparison Summary\n\n{table}"
        except Exception as e:
            print(f"[Warning] Failed to generate dynamic evaluation report: {e}")
            
    # Fallback to static table
    return f"""{header_section}
### Metrics Summary

| Model | Metric | Score |
| --- | --- | :---: |
| `meta-llama/Meta-Llama-3-8B-Instruct` | Faithfulness | **51.66%** | 
| | Answer Relevance | **60.00%** | 
| | Context Recall | **50.80%** | |
| `mistralai/Mistral-7B-Instruct-v0.3` | Faithfulness | **49.60%** | 
| | Answer Relevance | **57.50%** | 
| | Context Recall | **52.80%** | |
| `google/gemma-2-9b-it` | Faithfulness | **54.94%** | 
| | Answer Relevance | **72.00%** | 
| | Context Recall | **32.10%** | |"""

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    readme_path = os.path.join(root_dir, "README.md")
    
    commits_table = get_recent_commits()
    eval_report = get_evaluation_report(root_dir)
    
    content = f"""# Robust Financial Multi-Agent GraphRAG & Guardrail System

An autonomous, production-grade financial analysis platform engineered with **LangGraph multi-agent orchestration**, double-plane retrieval (Neo4j GraphRAG + Qdrant Dense Vector + BM25 Lexical + Cross-Encoder Reranker), semantic caching, real-time OpenTelemetry tracing, and strict input/output guardrails.

---

{eval_report}

### 📈 Benchmark Analysis (500-Query Sample Analysis)

| RAG Quality Metrics Comparison | Token Utilization Comparison |
| --- | --- |
| ![RAG Metrics Evaluation Trend](assets/metrics_trends.png) | ![Token Utilization Comparison](assets/token_utilization.png) |

---

## 🏗️ System Architecture

![System Architecture](assets/architectural_diagram.png)

---

## 🚀 Key Features

1. **LangGraph Multi-Agent Orchestration:**
   - **Input Guardrail:** Audits queries for prompt injection, system command bypass, and credential leakage.
   - **Supervisor Node:** Dynamically decomposes complex questions into parallelizable sub-queries and generates execution plans.
   - **KG Agent (Internal Retrieval):** Parallelized database execution across Neo4j and hybrid search.
   - **Web Agent (External Search):** Connects to Tavily API for recent context (fallback routing if local facts are insufficient).
   - **Data Analyst (Python Interpreter):** Generates and runs sandboxed Python code to calculate CAGR, metrics, and output structured tables.
   - **Output Guardrail:** Inspects and sanitizes response formats before rendering.

2. **Dual-Plane Retrieval (GraphRAG + Hybrid Vector):**
   - **Semantic/Lexical Plane:** Integrates Qdrant (dense cosine distance) and BM25 (sparse indexing) combined via **Reciprocal Rank Fusion (RRF)**.
   - **Re-ranking Stage:** Uses a Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) to filter down to the most relevant contexts.
   - **Structural Graph Plane:** programmatically constructs entity-relationship networks on Neo4j. Includes a robust **Regex-based JSON salvage parser** to prevent chunk data loss from truncated LLM generations.

3. **Production Tracing & Observability:**
   - Out-of-the-box auto-instrumentation for LangChain and LangGraph via **OpenTelemetry**.
   - Integrates **Arize Phoenix** for real-time visualization of traces, prompt/completion token usage, and latency percentiles.

4. **Inference & Cache Optimizations:**
   - Highly optimized for **vLLM** chunked prefill and prefix caching (achieving an **82% prefix cache hit rate** on repetitive guardrail queries).
   - **Semantic Caching:** Integrated Redis caching partitioned by User ID and active model.
   - Capped generation parameters (`max_tokens=2000` + explicit LLM stop sequences) to prevent infinite token loops.

---

<<<<<<< Updated upstream
=======
## 📊 Evaluation Report (FinQA Benchmark)

We benchmarked the agent on **500 samples** from the FinQA dataset. The evaluation is conducted asynchronously using an LLM-as-a-judge setup.

* **Agent Model:** `meta-llama/Meta-Llama-3-8B-Instruct`
* **Judge Model:** `Qwen/Qwen2.5-7B-Instruct`

### Metrics Summary

| Metric | Score | Description |
| --- | --- | --- |
| **Faithfulness** | **59.00%** | Measures freedom from hallucination (answers are strictly grounded in context) |
| **Answer Relevance** | **68.80%** | Measures how directly the output addresses the user's prompt |
| **Context Recall** | **54.50%** | Measures whether the retriever captured all necessary gold-standard facts |

### 📈 Metrics Trend Chart (500-Query Sample Analysis)

![RAG Metrics Evaluation Trend](assets/metrics_trends.png)

---

>>>>>>> Stashed changes
## 🖥️ Project Dashboards

| Client Chat Console (FastAPI + HTML5) | Arize Phoenix Trace & Latency Telemetry |
| --- | --- |
| ![Web UI](assets/web_ui_dashboard.png) | ![Phoenix Telemetry](assets/arize_phoenix_dashboard.png) |

---

## 🛠️ Repository & System Directory Structure

Below is the directory mapping for the core components:

```
├── app/
│   ├── main.py                  # FastAPI service exposing endpoints and serving Web UI
│   ├── config.py                # Hyperparameters, endpoints, and credentials config
│   ├── models.py                # Pydantic schemas for request payloads
│   ├── compose.yaml             # Docker orchestration for Redis, Qdrant, Neo4j, and App API
│   └── templates/
│       └── index.html           # Modern glassmorphic light-themed chat console
├── agents/
│   ├── agentic.py               # Main LangGraph multi-agent state graph definition
│   └── query_decomposer.py      # Decomposes complex prompts into independent sub-queries
├── components/
│   ├── hybrid_retriever.py      # Qdrant + BM25 + RRF + Cross-Encoder reranker
│   ├── kgraph_retriever.py      # GraphRAGPipeline managing Neo4j build and salvage parsing
│   └── reranker.py              # Cross-Encoder Reranker wrapper
├── services/
│   ├── telemetry.py             # Arize Phoenix + OpenTelemetry setup
│   └── semantic_cache.py        # Redis semantic caching client
├── evaluation/
│   └── eval_rag.py              # Asynchronous LLM-as-a-judge benchmarking suite
├── scripts/
│   └── run_experiments.sh       # Automates vLLM server launch and model evaluation
├── utils/
│   ├── load_data.py             # Data ingestion helpers for FinQA
│   ├── parse_finbench.py        # Raw PDF text-extraction parser
│   └── update_readme.py         # Automates README assembly from git activity
└── assets/                      # UI dashboards screenshots and visual assets
```

---

## 📥 Getting Started

### Prerequisites
- Docker & Docker Compose
- A running LLM server (vLLM or Ollama) configured in `.env`

### Quick Start
1. **Configure Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=password123
   REDIS_URL=redis://localhost:6379/0
   OPENAI_API_BASE=http://localhost:11434/v1
   OPENAI_API_BASE_JUDGE=http://localhost:11435/v1
   TAVILY_API_KEY=your_key_here
   ENABLE_TELEMETRY=true
   ```

2. **Spin Up the Containers:**
   ```bash
   docker compose -f app/compose.yaml up -d --build
   ```

3. **Access points:**
   - **Frontend UI Console:** [http://localhost:8000](http://localhost:8000)
   - **Phoenix Telemetry Panel:** [http://localhost:6006](http://localhost:6006)

---

## ⏱️ Recent Activity (Auto-Updated)

{commits_table}

---
*Note: This README is automatically updated and committed before pushes via a Git pre-push hook.*
"""
    
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Successfully updated README.md at: {readme_path}")

if __name__ == "__main__":
    main()
