import os
import torch
from sentence_transformers import CrossEncoder
from app.config import RERANKER_MODEL, RERANK_TOP_N

class CrossEncoderReranker:
    def __init__(self, model_name: str = RERANKER_MODEL):
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        print(f"[Reranker] Loading Cross-Encoder model '{model_name}' on device: {device}...")
        
        # Load the CrossEncoder model
        self.model = CrossEncoder(model_name, device=device)

    def rerank(self, query: str, documents: list, top_n: int = RERANK_TOP_N) -> list:
        """
        Re-scores and re-ranks retrieved candidates against the query.
        """
        if not documents:
            return []
            
        # Eliminate duplicates if any, preserving order
        unique_docs = []
        seen = set()
        for doc in documents:
            if doc not in seen:
                seen.add(doc)
                unique_docs.append(doc)

        pairs = [[query, doc] for doc in unique_docs]
        scores = self.model.predict(pairs)
        
        # Pair documents with their cross-encoder scores and sort descending
        ranked = sorted(zip(unique_docs, scores), key=lambda x: x[1], reverse=True)
        
        # Return only the top n documents
        return [doc for doc, score in ranked[:top_n]]
