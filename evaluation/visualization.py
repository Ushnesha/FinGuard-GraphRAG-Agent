#!/usr/bin/env python3
import os
import re
import matplotlib.pyplot as plt

def main():
    # Setup paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    report_path = os.path.join(root_dir, "results", "evaluation_report_01.md")
    output_dir = os.path.join(root_dir, "assets")
    output_img_path = os.path.join(output_dir, "visualization.png")
    
    # Ensure assets directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Read evaluation report
    if not os.path.exists(report_path):
        print(f"Error: Evaluation report not found at {report_path}")
        return
        
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Split content by sample blocks
    samples = content.split("### Sample ")
    samples = samples[1:] # Skip header
    
    sample_ids = []
    faithfulness_scores = []
    relevance_scores = []
    recall_scores = []
    
    # Extract metrics for each sample
    for idx, sample in enumerate(samples):
        # Extract sample number
        num_match = re.match(r"^(\d+)", sample.strip())
        s_id = int(num_match.group(1)) if num_match else (idx + 1)
        
        # Regex search for the scores
        faith_match = re.search(r"\*\*Faithfulness Score\*\*:\s*([0-9.]+)", sample)
        relevance_match = re.search(r"\*\*Relevance Score\*\*:\s*([0-9.]+)", sample)
        recall_match = re.search(r"\*\*Context Recall Score\*\*:\s*([0-9.]+)", sample)
        
        if faith_match and relevance_match and recall_match:
            sample_ids.append(s_id)
            faithfulness_scores.append(float(faith_match.group(1)))
            relevance_scores.append(float(relevance_match.group(1)))
            recall_scores.append(float(recall_match.group(1)))
        else:
            print(f"Warning: Skipping Sample {s_id} due to missing score(s).")
            
    if not sample_ids:
        print("Error: No evaluation metrics could be extracted.")
        return
        
    print(f"Extracted metrics for {len(sample_ids)} evaluation queries successfully.")
    
    # Apply a modern clean style
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Create figure with high DPI and wide layout
    fig, ax = plt.subplots(figsize=(15, 6), dpi=300)
    
    # Plotting each metric with professional color palette and distinct markers (dashed for raw scores)
    ax.plot(sample_ids, faithfulness_scores, label="Faithfulness (Raw)", color="#1f77b4", linewidth=1.2, linestyle="--", marker="o", markersize=4, alpha=0.5)
    ax.plot(sample_ids, relevance_scores, label="Answer Relevance (Raw)", color="#9467bd", linewidth=1.2, linestyle="--", marker="s", markersize=4, alpha=0.5)
    ax.plot(sample_ids, recall_scores, label="Context Recall (Raw)", color="#ff7f0e", linewidth=1.2, linestyle="--", marker="^", markersize=4, alpha=0.5)
    
    # Adding moving averages/trends (solid lines for MAs)
    window = 5
    if len(sample_ids) >= window:
        import numpy as np
        # Simple moving averages
        ma_faith = np.convolve(faithfulness_scores, np.ones(window)/window, mode='valid')
        ma_relevance = np.convolve(relevance_scores, np.ones(window)/window, mode='valid')
        ma_recall = np.convolve(recall_scores, np.ones(window)/window, mode='valid')
        ma_x = list(range(window, len(sample_ids) + 1))
        
        ax.plot(ma_x, ma_faith, color="#1f77b4", linestyle="-", linewidth=2.5, alpha=0.9, label="Faithfulness (5-Sample MA)")
        ax.plot(ma_x, ma_relevance, color="#9467bd", linestyle="-", linewidth=2.5, alpha=0.9, label="Relevance (5-Sample MA)")
        ax.plot(ma_x, ma_recall, color="#ff7f0e", linestyle="-", linewidth=2.5, alpha=0.9, label="Recall (5-Sample MA)")

    # Title & Labels
    ax.set_title("Multi-Agent GraphRAG Metric Evaluation (50 Queries Benchmark)", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Query Sample ID", fontsize=11, labelpad=10)
    ax.set_ylabel("Metric Score (0.0 to 1.0)", fontsize=11, labelpad=10)
    
    # Configure axes limits and ticks
    ax.set_xlim(0.5, len(sample_ids) + 0.5)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(range(1, len(sample_ids) + 1))
    ax.set_xticklabels(range(1, len(sample_ids) + 1), rotation=0, fontsize=8)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    
    # Grid customization
    ax.grid(True, linestyle=":", alpha=0.6, color="#cccccc")
    
    # Premium Legend placement
    ax.legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="#ffffff", edgecolor="#dddddd", fontsize=9.5)
    
    # Remove top and right spines for a clean look
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
        
    plt.tight_layout()
    
    # Save the premium visualization image
    plt.savefig(output_img_path, format="png", bbox_inches="tight")
    plt.close()
    
    print(f"Premium visualization successfully created and saved to: {output_img_path}")

if __name__ == "__main__":
    main()
