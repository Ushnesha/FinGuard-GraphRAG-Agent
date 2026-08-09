#!/usr/bin/env python3
import os
import json
import glob
import re
import numpy as np
import matplotlib.pyplot as plt

def load_all_model_results(results_dir):
    """Loads query-by-query raw results for all models."""
    pattern = os.path.join(results_dir, "comparison_*.json")
    files = glob.glob(pattern)
    models_data = {}
    
    for f in files:
        # Extract model name from filename
        filename = os.path.basename(f)
        model_name = filename.replace("comparison_", "").replace(".json", "").replace("_", "/").replace("google/", "google/gemma-2-").replace("meta/", "meta-llama/")
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                if data:
                    models_data[model_name] = data
        except Exception as e:
            print(f"[Warning] Failed to load {filename}: {e}")
            
    return models_data

def generate_metrics_trends(models_data, output_dir):
    """Generates a multi-panel line plot comparing Faithfulness, Relevance, and Recall trends."""
    if not models_data:
        print("[Error] No model comparison data available for trend lines.")
        return

    num_models = len(models_data)
    fig, axes = plt.subplots(num_models, 1, figsize=(15, 4.5 * num_models), dpi=300, sharex=True)
    
    # Handle single model edge case for axes index
    if num_models == 1:
        axes = [axes]
        
    plt.style.use('seaborn-v0_8-whitegrid')
    
    colors = {
        "faithfulness": "#00897b",  # Teal
        "relevance": "#5e35b1",     # Purple
        "recall": "#e65100"         # Dark Orange
    }
    
    window = 5
    
    for idx, (model_name, results) in enumerate(sorted(models_data.items())):
        ax = axes[idx]
        
        # Sort by query index
        results = sorted(results, key=lambda x: x["idx"])
        sample_ids = [r["idx"] for r in results]
        faithfulness = [r["faithfulness"] for r in results]
        relevance = [r["relevance"] for r in results]
        recall = [r["recall"] for r in results]
        
        # Plot raw scores with dashed lines & markers
        ax.plot(sample_ids, faithfulness, color=colors["faithfulness"], linestyle="--", linewidth=1.0, alpha=0.35, marker="o", markersize=3)
        ax.plot(sample_ids, relevance, color=colors["relevance"], linestyle="--", linewidth=1.0, alpha=0.35, marker="s", markersize=3)
        ax.plot(sample_ids, recall, color=colors["recall"], linestyle="--", linewidth=1.0, alpha=0.35, marker="^", markersize=3)
        
        # Plot 5-sample Moving Average
        if len(sample_ids) >= window:
            ma_faith = np.convolve(faithfulness, np.ones(window)/window, mode='valid')
            ma_relevance = np.convolve(relevance, np.ones(window)/window, mode='valid')
            ma_recall = np.convolve(recall, np.ones(window)/window, mode='valid')
            ma_x = list(range(window, len(sample_ids) + 1))
            
            ax.plot(ma_x, ma_faith, color=colors["faithfulness"], linestyle="-", linewidth=2.2, alpha=0.9, label="Faithfulness (5-Query MA)")
            ax.plot(ma_x, ma_relevance, color=colors["relevance"], linestyle="-", linewidth=2.2, alpha=0.9, label="Answer Relevance (5-Query MA)")
            ax.plot(ma_x, ma_recall, color=colors["recall"], linestyle="-", linewidth=2.2, alpha=0.9, label="Context Recall (5-Query MA)")

        ax.set_title(f"Model: {model_name}", fontsize=12, fontweight='bold', loc='left', pad=8)
        ax.set_ylabel("Metric Score", fontsize=10)
        ax.set_ylim(-0.05, 1.05)
        ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.grid(True, linestyle=":", alpha=0.5, color="#cccccc")
        
        if idx == 0:
            ax.legend(loc="upper right", frameon=True, framealpha=0.95, facecolor="#ffffff", edgecolor="#dddddd", fontsize=9)
            
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
            
    axes[-1].set_xlabel("Query ID", fontsize=10)
    axes[-1].set_xticks(range(1, len(sample_ids) + 1))
    axes[-1].set_xticklabels(range(1, len(sample_ids) + 1), rotation=0, fontsize=8)
    
    plt.suptitle("RAG Quality Metrics Trend & Moving Averages", fontsize=15, fontweight='bold', y=0.98)
    plt.tight_layout()
    
    output_path = os.path.join(output_dir, "metrics_trends.png")
    plt.savefig(output_path, format="png", bbox_inches="tight")
    plt.close()
    print(f"✅ Quality metrics trends successfully saved to: {output_path}")

def generate_token_utilization(summaries_path, output_dir):
    """Generates a grouped, stacked bar chart comparing prompt/completion tokens across categories."""
    if not os.path.exists(summaries_path):
        print(f"[Warning] All model summaries file not found at {summaries_path}. Skipping token chart.")
        return
        
    with open(summaries_path, "r", encoding="utf-8") as f:
        summaries = json.load(f)
        
    if not summaries:
        print("[Error] Summaries file is empty.")
        return

    # Extract categories and models
    models = sorted(list(summaries.keys()))
    # Standard categories
    categories = ["Math_Calculation", "Comparative_Analysis", "Fact_Lookup", "General/Comparative"]
    
    # Set up matplotlib style
    plt.style.use('seaborn-v0_8-whitegrid')
    
    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
    
    # Width of a single model's bar, and the offset step
    num_models = len(models)
    bar_width = 0.22
    group_spacing = 0.9
    
    # Assign distinct colors to models (dark for prompt, light for completion)
    model_colors = {
        models[i]: c for i, c in enumerate([
            ("#1a73e8", "#8ab4f8"),  # Blue (LLaMA)
            ("#ff6d00", "#ffb74d"),  # Orange (Mistral)
            ("#8e24aa", "#e040fb"),  # Purple (Gemma)
            ("#00897b", "#80cbc4")   # Teal (Alternative)
        ][:num_models])
    }
    
    # Calculate group positions
    indices = np.arange(len(categories)) * group_spacing
    
    for m_idx, model in enumerate(models):
        prompt_heights = []
        comp_heights = []
        
        # Gather heights for each category
        for cat in categories:
            cat_data = summaries[model]["categories"].get(cat, {})
            prompt_heights.append(cat_data.get("prompt_tokens", 0))
            comp_heights.append(cat_data.get("completion_tokens", 0))
            
        # Position offset for the current model's bar
        offsets = indices + (m_idx - (num_models - 1) / 2) * bar_width
        
        p_color, c_color = model_colors[model]
        
        # Plot prompt tokens stack
        ax.bar(offsets, prompt_heights, width=bar_width, color=p_color, label=f"{model} (Prompt Tokens)", edgecolor="none")
        # Plot completion tokens stack on top of prompt tokens
        ax.bar(offsets, comp_heights, width=bar_width, bottom=prompt_heights, color=c_color, label=f"{model} (Completion Tokens)", edgecolor="none")

    # Title & Labels
    ax.set_title("Average Token Utilization per Model across Query Categories", fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel("Average Tokens Used", fontsize=11, labelpad=10)
    ax.set_xticks(indices)
    ax.set_xticklabels([c.replace("_", " ") for c in categories], fontsize=10, fontweight='bold')
    
    # Grid & Legend
    ax.grid(True, linestyle=":", alpha=0.5, color="#cccccc")
    ax.legend(loc="upper right", frameon=True, framealpha=0.95, facecolor="#ffffff", edgecolor="#dddddd", fontsize=9)
    
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
        
    plt.tight_layout()
    
    output_path = os.path.join(output_dir, "token_utilization.png")
    plt.savefig(output_path, format="png", bbox_inches="tight")
    plt.close()
    print(f"✅ Token utilization bar chart successfully saved to: {output_path}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    results_dir = os.path.join(root_dir, "results")
    
    global output_dir
    output_dir = os.path.join(root_dir, "assets")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Load data
    models_data = load_all_model_results(results_dir)
    
    # 2. Generate line plots for metrics trends
    if models_data:
        generate_metrics_trends(models_data, output_dir)
    else:
        print("[Warning] No raw query results found. Complete model evaluations first.")
        
    # 3. Generate stacked bar chart for token usage
    summaries_path = os.path.join(results_dir, "all_model_summaries.json")
    if os.path.exists(summaries_path):
        generate_token_utilization(summaries_path, output_dir)
    else:
        print("[Warning] Summaries index not found. Run model comparison script first.")

if __name__ == "__main__":
    main()
