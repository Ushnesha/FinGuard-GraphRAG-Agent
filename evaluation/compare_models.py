import os
import sys
import json
import re
import argparse
import asyncio
from typing import List, Dict
from langchain_openai import ChatOpenAI

# Add the project root to python path to resolve imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agentic import StateAgent
import app.config as cfg

# Import judge logic from existing eval_rag
from evaluation.eval_rag import judge_faithfulness, judge_relevance, judge_recall

async def evaluate_sample_for_model(
    idx: int, 
    item: dict, 
    agent: StateAgent, 
    judge_llm: ChatOpenAI, 
    limit: int, 
    semaphore: asyncio.Semaphore
) -> Dict:
    async with semaphore:
        question = item["qa"]["question"]
        
        # 1. Compile Gold Facts Reference
        gold_facts = []
        gold_inds = item["qa"].get("gold_inds", {})
        if gold_inds:
            for k, v in gold_inds.items():
                gold_facts.append(f"- {v}")
        explanation = item["qa"].get("explanation")
        if explanation:
            gold_facts.append(f"- Explanation: {explanation}")
        gold_facts.append(f"- Target Answer: {item['qa'].get('answer')}")
        gold_ref = "\n".join(gold_facts)
        
        # 2. Run Pipeline in separate executor
        loop = asyncio.get_running_loop()
        state = await loop.run_in_executor(None, lambda: agent.run(query=question))
        answer = state.get("final_output", "")
        context = "\n".join(state.get("agent_outputs", []))
        tokens = state.get("tokens", {"prompt_tokens": 0, "completion_tokens": 0})
        
        # 3. Judge Metrics (run all 3 in parallel)
        faith_task = loop.run_in_executor(None, lambda: judge_faithfulness(question, context, answer, judge_llm))
        relevance_task = loop.run_in_executor(None, lambda: judge_relevance(question, answer, judge_llm))
        recall_task = loop.run_in_executor(None, lambda: judge_recall(question, context, gold_ref, judge_llm))
        
        faith, relevance, recall = await asyncio.gather(faith_task, relevance_task, recall_task)
        
        # 4. Refined Categorization
        question_lower = question.lower()
        
        # Comparative Analysis: deals with changes, margins, comparisons, differences, and exceeds
        if any(w in question_lower for w in ["exceed", "compare", "more than", "less than", "higher", "lower", "difference", "growth", "increase", "decline", "decrease", "than", "change"]):
            category = "Comparative_Analysis"
        # Math Calculation: deals with percentages, averages, quotients, totals, cagr calculations
        elif any(w in question_lower for w in ["percent", "percentage", "cagr", "rate", "calculate", "divide", "sum", "average", "total", "ratio", "fraction", "math"]):
            category = "Math_Calculation"
        # Fact Lookup: direct retrieval of raw numbers or statements
        elif any(w in question_lower for w in ["what was", "what is", "who", "interest expense", "revenue", "asset", "liability", "amount"]):
            category = "Fact_Lookup"
        else:
            category = "General/Comparative"

        return {
            "idx": idx + 1,
            "question": question,
            "category": category,
            "gold_ref": gold_ref,
            "answer": answer,
            "faithfulness": faith["score"],
            "relevance": relevance["score"],
            "recall": recall["score"],
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0)
        }

async def run_model_eval(
    model_name: str, 
    model_port: int, 
    eval_set: List[dict], 
    judge_llm: ChatOpenAI, 
    concurrency: int
) -> List[Dict]:
    print(f"\n🚀 Starting Evaluation for Model: {model_name} on Port: {model_port}...")
    
    # Dynamically update the configuration endpoint before creating the agent
    cfg.OPENAI_API_BASE = f"http://localhost:{model_port}/v1"
    
    agent = StateAgent(llm_model=model_name)
    semaphore = asyncio.Semaphore(concurrency)
    
    tasks = [
        evaluate_sample_for_model(idx, item, agent, judge_llm, len(eval_set), semaphore)
        for idx, item in enumerate(eval_set)
    ]
    
    results = await asyncio.gather(*tasks)
    return results

def main():
    parser = argparse.ArgumentParser(description="Compare multiple retrieval LLM models in RAG.")
    parser.add_argument("--limit", type=int, default=50, help="Number of queries to run (default 50).")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent queries per model.")
    parser.add_argument("--judge-model", type=str, default="Qwen/Qwen2.5-7B-Instruct", help="The model used as judge.")
    parser.add_argument("--judge-port", type=int, default=11435, help="API Port of the Judge model.")
    parser.add_argument(
        "--models", 
        nargs="+", 
        default=[
            "meta-llama/Meta-Llama-3-8B-Instruct:11434",
            "mistralai/Mistral-7B-Instruct-v0.3:11434",
            "google/gemma-2-9b-it:11434"
        ],
        help="List of models to evaluate in 'model_name:port' format."
    )
    args = parser.parse_args()
    
    # 1. Load Evaluation Dataset
    print(f"Loading FinQA dataset from {cfg.FinQA_data_path}...")
    with open(cfg.FinQA_data_path, "r") as f:
        raw_data = json.load(f)
    eval_set = raw_data[:args.limit]
    
    if not eval_set:
        print("[Error] No evaluation data found.")
        return

    # 2. Parse the retrieval models to test and their ports
    models_to_test = []
    for m in args.models:
        if ":" in m:
            name, port = m.rsplit(":", 1)
            models_to_test.append({"name": name, "port": int(port)})
        else:
            print(f"[Warning] Invalid model format: '{m}'. Expected 'model_name:port'. Skipping.")

    # Initialize the Judge LLM
    judge_llm = ChatOpenAI(
        model=args.judge_model,
        openai_api_key="none",
        openai_api_base=f"http://localhost:{args.judge_port}/v1",
        temperature=0.0,
        max_tokens=300
    )

    all_model_summaries = {}
    detailed_reports = []

    # 3. Evaluate each model sequentially
    for model_info in models_to_test:
        results = asyncio.run(run_model_eval(
            model_info["name"], 
            model_info["port"], 
            eval_set, 
            judge_llm, 
            args.concurrency
        ))
        
        # Calculate overall averages
        avg_faith = sum(r["faithfulness"] for r in results) / len(results)
        avg_relevance = sum(r["relevance"] for r in results) / len(results)
        avg_recall = sum(r["recall"] for r in results) / len(results)
        
        avg_prompt_tokens = sum(r["prompt_tokens"] for r in results) / len(results)
        avg_completion_tokens = sum(r["completion_tokens"] for r in results) / len(results)
        avg_total_tokens = avg_prompt_tokens + avg_completion_tokens
        
        # Calculate category averages
        categories = ["Math_Calculation", "Comparative_Analysis", "Fact_Lookup", "General/Comparative"]
        cat_scores = {}
        for cat in categories:
            cat_items = [r for r in results if r["category"] == cat]
            if cat_items:
                cat_faith = sum(r["faithfulness"] for r in cat_items) / len(cat_items)
                cat_relevance = sum(r["relevance"] for r in cat_items) / len(cat_items)
                cat_recall = sum(r["recall"] for r in cat_items) / len(cat_items)
                cat_prompt = sum(r["prompt_tokens"] for r in cat_items) / len(cat_items)
                cat_comp = sum(r["completion_tokens"] for r in cat_items) / len(cat_items)
                
                cat_scores[cat] = {
                    "faithfulness": cat_faith, 
                    "relevance": cat_relevance,
                    "recall": cat_recall, 
                    "prompt_tokens": cat_prompt,
                    "completion_tokens": cat_comp,
                    "count": len(cat_items)
                }
            else:
                cat_scores[cat] = {
                    "faithfulness": 0.0, 
                    "relevance": 0.0,
                    "recall": 0.0, 
                    "prompt_tokens": 0.0,
                    "completion_tokens": 0.0,
                    "count": 0
                }
                
        all_model_summaries[model_info["name"]] = {
            "faithfulness": avg_faith,
            "relevance": avg_relevance,
            "recall": avg_recall,
            "prompt_tokens": avg_prompt_tokens,
            "completion_tokens": avg_completion_tokens,
            "total_tokens": avg_total_tokens,
            "categories": cat_scores
        }
        
        detailed_reports.append((model_info["name"], results))
        
        # Save raw output JSON for tracing
        clean_name = model_info["name"].replace("/", "_").replace("-", "_")
        raw_output_path = f"results/comparison_{clean_name}.json"
        os.makedirs("results", exist_ok=True)
        with open(raw_output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Raw outputs and token counts for {model_info['name']} saved to {raw_output_path}")

    # 4. Generate final Markdown Comparison Report
    summary_index_path = "results/all_model_summaries.json"
    os.makedirs("results", exist_ok=True)
    
    # Load previously completed model runs if any
    existing_summaries = {}
    if os.path.exists(summary_index_path):
        try:
            with open(summary_index_path, "r") as f:
                existing_summaries = json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load existing summaries index: {e}")
            
    # Merge new summaries into the index
    existing_summaries.update(all_model_summaries)
    
    # Save the consolidated index back to disk
    with open(summary_index_path, "w") as f:
        json.dump(existing_summaries, f, indent=2)
        
    report_path = "results/model_comparison_report.md"
    with open(report_path, "w") as f:
        f.write("# 📊 Multi-Model RAG Retrieval & Token Comparison Report\n\n")
        f.write(f"This report compares performance metrics and token utilization on **{args.limit} queries** across different retrieval LLM models, using **{args.judge_model}** as the judge.\n\n")
        
        f.write("## 🏆 Overall Performance & Token Summary\n\n")
        f.write("| Model Name | Avg Faithfulness | Avg Answer Relevance | Avg Context Recall | Avg Prompt Tokens | Avg Completion Tokens | Avg Total Tokens |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for m_name, summary in existing_summaries.items():
            f.write(f"| `{m_name}` | **{summary['faithfulness']:.2%}** | **{summary['relevance']:.2%}** | **{summary['recall']:.2%}** | {summary['prompt_tokens']:.1f} | {summary['completion_tokens']:.1f} | **{summary['total_tokens']:.1f}** |\n")
        
        f.write("\n---\n\n")
        f.write("## 🗂️ Category-Level Performance & Token Breakdown\n\n")
        
        for m_name, summary in existing_summaries.items():
            f.write(f"### 🎯 Model: `{m_name}`\n\n")
            f.write("| Query Category | Count | Avg Faithfulness | Avg Relevance | Avg Recall | Avg Prompt Tokens | Avg Comp. Tokens | Avg Total Tokens |\n")
            f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
            for cat, scores in summary["categories"].items():
                if scores["count"] > 0:
                    tot_tok = scores["prompt_tokens"] + scores["completion_tokens"]
                    f.write(f"| {cat} | {scores['count']} | {scores['faithfulness']:.2%} | {scores['relevance']:.2%} | {scores['recall']:.2%} | {scores['prompt_tokens']:.1f} | {scores['completion_tokens']:.1f} | **{tot_tok:.1f}** |\n")
            f.write("\n")

        f.write("\n---\n\n")
        f.write("## 💡 Key Architectural & Cost Insights\n\n")
        f.write("1. **Token Cost-Benefit Trade-off:** Analyze the average total token count vs. faithfulness. If Gemma-2-9B achieves higher faithfulness but uses significantly more completion tokens, consider the cost implications of deploying it at scale.\n")
        f.write("2. **Math Node Efficiency:** Check the `Math_Calculation` category. Compare models on token counts. A model that generates concise Python scripts for the `data_analyst` node will use fewer completion tokens while maintaining high accuracy.\n")
        f.write("3. **Verbosity Control:** Check `Avg Completion Tokens` in `Fact_Lookup`. Models that output long, pre-training biased answers will have higher completion tokens and lower faithfulness scores (penalized for ungrounded details).\n")

    print(f"\n🎉 Comparison complete! Comparative report saved to: {report_path}")

if __name__ == "__main__":
    main()
