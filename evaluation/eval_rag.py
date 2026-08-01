import os
import sys
import json
import re
import argparse
from typing import List, Dict

# Add the project root to python path to resolve service and component imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agentic import StateAgent
from app.config import MEGA_CORPUS, llm

def extract_score(response_text: str) -> float:
    """Helper to parse a float score from the judge's output."""
    match = re.search(r"Score:\s*([0-9.]+)", response_text, re.IGNORECASE)
    if match:
        try:
            return min(1.0, max(0.0, float(match.group(1))))
        except Exception:
            pass
    return 0.0

def get_reasoning(response_text: str) -> str:
    """Helper to parse the explanation reasoning from the judge's output."""
    match = re.search(r"Reasoning:\s*(.*)", response_text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return "No reasoning provided."

def judge_faithfulness(question: str, context: str, answer: str, judge_llm) -> Dict:
    """Judge Faithfulness: Is the answer grounded only in the context?"""
    prompt = (
        "You are an objective evaluation judge auditing a RAG system.\n"
        "Evaluate whether the generated answer is faithful to the retrieved context. "
        "Every claim in the answer must be directly supported by the context without assumptions or extrapolation.\n\n"
        f"Retrieved Context:\n{context}\n\n"
        f"User Question: '{question}'\n"
        f"Generated Answer: '{answer}'\n\n"
        "Rate the faithfulness on a scale from 0.0 to 1.0 (where 1.0 means all facts in the answer are fully supported, and 0.0 means none are).\n"
        "Output format strictly:\n"
        "Score: <float_score>\n"
        "Reasoning: <brief reasoning>"
    )
    try:
        response = judge_llm.invoke(prompt, max_tokens=150).content
        return {"score": extract_score(response), "reason": get_reasoning(response)}
    except Exception as e:
        return {"score": 0.0, "reason": f"Judge failed: {e}"}

def judge_relevance(question: str, answer: str, judge_llm) -> Dict:
    """Judge Answer Relevance: Does the answer directly address the question?"""
    prompt = (
        "You are an objective evaluation judge auditing a RAG system.\n"
        "Evaluate whether the generated answer is relevant to the user's question. "
        "The answer must address the question directly and complete it without unnecessary filler.\n\n"
        f"User Question: '{question}'\n"
        f"Generated Answer: '{answer}'\n\n"
        "Rate the relevance on a scale from 0.0 to 1.0 (where 1.0 means the answer fully and directly addresses the question, and 0.0 means it is irrelevant).\n"
        "Output format strictly:\n"
        "Score: <float_score>\n"
        "Reasoning: <brief reasoning>"
    )
    try:
        response = judge_llm.invoke(prompt, max_tokens=150).content
        return {"score": extract_score(response), "reason": get_reasoning(response)}
    except Exception as e:
        return {"score": 0.0, "reason": f"Judge failed: {e}"}

def judge_recall(question: str, context: str, gold_reference: str, judge_llm) -> Dict:
    """Judge Context Recall: Does the context contain the gold standard facts?"""
    prompt = (
        "You are an objective evaluation judge auditing a RAG system.\n"
        "Evaluate whether the retrieved context successfully recalled the necessary gold reference facts needed to answer the question.\n\n"
        f"Gold Reference Facts:\n{gold_reference}\n\n"
        f"Retrieved Context:\n{context}\n\n"
        f"User Question: '{question}'\n\n"
        "Rate the recall on a scale from 0.0 to 1.0 (where 1.0 means all key gold facts are present in the context, and 0.0 means none are).\n"
        "Output format strictly:\n"
        "Score: <float_score>\n"
        "Reasoning: <brief reasoning>"
    )
    try:
        response = judge_llm.invoke(prompt, max_tokens=150).content
        return {"score": extract_score(response), "reason": get_reasoning(response)}
    except Exception as e:
        return {"score": 0.0, "reason": f"Judge failed: {e}"}

def run_evaluation(limit: int = 5, agent_model: str = None, judge_model: str = None):
    print(f"Loading aligned FinQA evaluation subset (limit: {limit})...")
    eval_set = MEGA_CORPUS[0]["CORPUS"][:limit]
    
    if not eval_set:
        print("[Error] No evaluation data loaded. Aborting.")
        return
        
    print(f"Initializing RAG Agent with model: {agent_model or 'default'}...")
    agent = StateAgent(model=agent_model)

    # Initialize Judge model
    from app.config import LLM_MODEL
    actual_agent_model = agent_model or LLM_MODEL
    actual_judge_model = judge_model or actual_agent_model
    
    if actual_judge_model == actual_agent_model:
        print(f"[Warning] Evaluation is using the SAME model ({actual_judge_model}) for both agent and judge.")
        active_judge_llm = llm
    else:
        print(f"Initializing distinct Judge LLM with model: {actual_judge_model}...")
        from langchain_openai import ChatOpenAI
        from app.config import OPENAI_API_BASE, LLM_TEMPERATURE
        
        # Point to port 11435 on the same API server base if we are querying the separate judge model
        judge_api_base = OPENAI_API_BASE.replace("11434", "11435")
        active_judge_llm = ChatOpenAI(
            model=actual_judge_model,
            openai_api_key="none",
            openai_api_base=judge_api_base,
            temperature=LLM_TEMPERATURE,
            max_tokens=200
        )
    
    results = []
    
    for idx, item in enumerate(eval_set):
        question = item["qa"]["question"]
        print(f"\n[{idx + 1}/{limit}] Evaluating Query: '{question}'")
        
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
        
        # 2. Run Pipeline
        state = agent.run(query=question)
        answer = state.get("final_output", "")
        context = "\n".join(state.get("agent_outputs", []))
        
        # 3. Judge Metrics
        faith = judge_faithfulness(question, context, answer, active_judge_llm)
        relevance = judge_relevance(question, answer, active_judge_llm)
        recall = judge_recall(question, context, gold_ref, active_judge_llm)
        
        results.append({
            "idx": idx + 1,
            "question": question,
            "gold_ref": gold_ref,
            "answer": answer,
            "faithfulness": faith,
            "relevance": relevance,
            "recall": recall
        })
        
        print(f"  > Faithfulness: {faith['score']} ({faith['reason']})")
        print(f"  > Relevance:    {relevance['score']} ({relevance['reason']})")
        print(f"  > Recall:       {recall['score']} ({recall['reason']})")

    # 4. Summarize and Print Aggregate Results
    avg_faith = sum(r["faithfulness"]["score"] for r in results) / len(results)
    avg_relevance = sum(r["relevance"]["score"] for r in results) / len(results)
    avg_recall = sum(r["recall"]["score"] for r in results) / len(results)
    
    print("\n" + "="*50)
    print("📈 AGGREGATE EVALUATION REPORT")
    print("="*50)
    print(f"Total Evaluated Samples: {len(results)}")
    print(f"Agent Model:             {actual_agent_model}")
    print(f"Judge Model:             {actual_judge_model}")
    print(f"Average Faithfulness (Hallucination-free): {avg_faith:.2%}")
    print(f"Average Answer Relevance:                 {avg_relevance:.2%}")
    print(f"Average Context Recall:                    {avg_recall:.2%}")
    print("="*50)
    
    # Save Report to Artifacts
    artifact_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report_path = os.path.join(artifact_dir, "evaluation_report.md")
    
    with open(report_path, "w") as f:
        f.write("# RAG Evaluation Report (FinQA Subset)\n\n")
        f.write(f"- **Total Samples Evaluated**: {len(results)}\n")
        f.write(f"- **Agent Model**: {actual_agent_model}\n")
        f.write(f"- **Judge Model**: {actual_judge_model}\n")
        f.write(f"- **Average Faithfulness**: {avg_faith:.2%}\n")
        f.write(f"- **Average Answer Relevance**: {avg_relevance:.2%}\n")
        f.write(f"- **Average Context Recall**: {avg_recall:.2%}\n\n")
        f.write("## Detailed Evaluation Log\n\n")
        for r in results:
            f.write(f"### Sample {r['idx']}\n")
            f.write(f"**Question**: {r['question']}\n\n")
            f.write(f"**Gold Facts Reference**:\n```\n{r['gold_ref']}\n```\n\n")
            f.write(f"**Generated Answer**: {r['answer']}\n\n")
            f.write(f"**Faithfulness Score**: {r['faithfulness']['score']}  \n*Reasoning*: {r['faithfulness']['reason']}\n\n")
            f.write(f"**Relevance Score**: {r['relevance']['score']}  \n*Reasoning*: {r['relevance']['reason']}\n\n")
            f.write(f"**Context Recall Score**: {r['recall']['score']}  \n*Reasoning*: {r['recall']['reason']}\n\n")
            f.write("---\n\n")
            
    print(f"Full evaluation report saved to: {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG Pipeline using LLM-as-a-judge.")
    parser.add_argument("--limit", type=int, default=5, help="Number of samples to evaluate (1-200)")
    parser.add_argument("--agent-model", type=str, default=None, help="Model name for the RAG agent.")
    parser.add_argument("--judge-model", type=str, default=None, help="Model name for the evaluation judge (must be different).")
    args = parser.parse_args()
    
    run_evaluation(args.limit, args.agent_model, args.judge_model)
