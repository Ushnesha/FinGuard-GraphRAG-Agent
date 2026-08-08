# 📊 Multi-Model RAG Retrieval & Token Comparison Report

This report compares performance metrics and token utilization on **50 queries** across different retrieval LLM models, using **Qwen/Qwen2.5-7B-Instruct** as the judge.

## 🏆 Overall Performance & Token Summary

| Model Name | Avg Faithfulness | Avg Answer Relevance | Avg Context Recall | Avg Prompt Tokens | Avg Completion Tokens | Avg Total Tokens |
| --- | --- | --- | --- | --- | --- | --- |
| `meta-llama/Meta-Llama-3-8B-Instruct` | **51.66%** | **60.00%** | **50.80%** | 6262.9 | 711.1 | **6974.0** |
| `mistralai/Mistral-7B-Instruct-v0.3` | **49.60%** | **57.50%** | **52.80%** | 8401.4 | 691.6 | **9093.0** |
| `google/gemma-2-9b-it` | **54.94%** | **72.00%** | **32.10%** | 6106.0 | 355.2 | **6461.2** |

---

## 🗂️ Category-Level Performance & Token Breakdown

### 🎯 Model: `meta-llama/Meta-Llama-3-8B-Instruct`

| Query Category | Count | Avg Faithfulness | Avg Relevance | Avg Recall | Avg Prompt Tokens | Avg Comp. Tokens | Avg Total Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Math_Calculation | 30 | 50.77% | 65.00% | 54.00% | 6581.6 | 679.1 | **7260.7** |
| Comparative_Analysis | 16 | 51.25% | 49.37% | 41.25% | 6224.1 | 806.5 | **7030.6** |
| Fact_Lookup | 3 | 53.33% | 60.00% | 60.00% | 3737.7 | 565.0 | **4302.7** |
| General/Comparative | 1 | 80.00% | 80.00% | 80.00% | 4898.0 | 584.0 | **5482.0** |

### 🎯 Model: `mistralai/Mistral-7B-Instruct-v0.3`

| Query Category | Count | Avg Faithfulness | Avg Relevance | Avg Recall | Avg Prompt Tokens | Avg Comp. Tokens | Avg Total Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Math_Calculation | 30 | 49.00% | 55.50% | 59.33% | 9051.0 | 736.6 | **9787.6** |
| Comparative_Analysis | 16 | 44.38% | 59.06% | 41.25% | 8065.7 | 685.2 | **8750.9** |
| Fact_Lookup | 3 | 73.33% | 56.67% | 40.00% | 5061.0 | 388.3 | **5449.3** |
| General/Comparative | 1 | 80.00% | 95.00% | 80.00% | 4308.0 | 353.0 | **4661.0** |

### 🎯 Model: `google/gemma-2-9b-it`

| Query Category | Count | Avg Faithfulness | Avg Relevance | Avg Recall | Avg Prompt Tokens | Avg Comp. Tokens | Avg Total Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Math_Calculation | 30 | 60.23% | 70.33% | 36.83% | 6589.0 | 404.6 | **6993.6** |
| Comparative_Analysis | 16 | 42.50% | 80.00% | 18.75% | 5754.7 | 276.4 | **6031.1** |
| Fact_Lookup | 3 | 66.67% | 43.33% | 40.00% | 3681.3 | 274.7 | **3956.0** |
| General/Comparative | 1 | 60.00% | 80.00% | 80.00% | 4510.0 | 374.0 | **4884.0** |


---

## 💡 Key Architectural & Cost Insights

1. **Token Cost-Benefit Trade-off:** Analyze the average total token count vs. faithfulness. If Gemma-2-9B achieves higher faithfulness but uses significantly more completion tokens, consider the cost implications of deploying it at scale.
2. **Math Node Efficiency:** Check the `Math_Calculation` category. Compare models on token counts. A model that generates concise Python scripts for the `data_analyst` node will use fewer completion tokens while maintaining high accuracy.
3. **Verbosity Control:** Check `Avg Completion Tokens` in `Fact_Lookup`. Models that output long, pre-training biased answers will have higher completion tokens and lower faithfulness scores (penalized for ungrounded details).
