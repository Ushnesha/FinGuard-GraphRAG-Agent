import os
import json
import asyncio
import hashlib
from langchain_openai import ChatOpenAI
from app.config import MEGA_CORPUS

CORPUS = MEGA_CORPUS[0]["CORPUS"]

def _chunk_text_block(text: str, max_chars: int, overlap: int) -> list:
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end < len(text):
            boundary = text.rfind("\n", end - 150, end)
            if boundary == -1:
                boundary = text.rfind(". ", end - 100, end)
            if boundary == -1:
                boundary = text.rfind(" ", end - 50, end)
            if boundary != -1:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= len(text) or end >= len(text):
            break
        if start <= 0 or start == end - overlap:
            start = end
    return [c for c in chunks if c]

def chunk_document(doc: str, max_chars: int = 600, overlap: int = 120) -> list:
    lines = doc.split("\n")
    chunks = []
    current_text_block = []
    current_table_block = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_table_line = "|" in stripped
        if is_table_line:
            if not in_table:
                if current_text_block:
                    chunks.extend(_chunk_text_block("\n".join(current_text_block), max_chars, overlap))
                    current_text_block = []
                in_table = True
            current_table_block.append(stripped)
        else:
            if in_table:
                if current_table_block:
                    chunks.append("\n".join(current_table_block))
                    current_table_block = []
                in_table = False
            current_text_block.append(stripped)

    if in_table and current_table_block:
        chunks.append("\n".join(current_table_block))
    elif current_text_block:
        chunks.extend(_chunk_text_block("\n".join(current_text_block), max_chars, overlap))

    return chunks

async def main():
    llm = ChatOpenAI(
        model="meta-llama/Meta-Llama-3-8B-Instruct", 
        openai_api_key="none",
        openai_api_base=os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1"),
        temperature=0,
        max_tokens=1000
    )
    json_llm = llm.bind(response_format={"type": "json_object"})

    chunks = []
    for doc in CORPUS:
        chunks.extend(chunk_document(doc))

    print(f"Total chunks to test: {len(chunks)}")

    for i, chunk in enumerate(chunks[80:200]):  # test first 20 chunks
        prompt = f"""Identify all key Entities and Relationships in the text below.
        
        Allowed Entity Types: [COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, TIME_PERIOD]
        Allowed Relationship Types: [PART_OF, REPORTS, FOR_PERIOD, ACQUIRED]

        You must format your response STRICTLY as a valid JSON object matching this structure:
        {{
            "entities": [
                {{"name": "entity name", "type": "ENTITY_TYPE"}}
            ],
            "relationships": [
                {{"source": "source_entity_name", "type": "RELATIONSHIP_TYPE", "target": "target_entity_name"}}
            ]
        }}
        
        Formatting constraints:
        1. Use exactly "name" (not "id" or "text") for the entity name.
        2. Use exactly "type" (not "relationship_type" or "label") for the relationship type.
        3. CRITICAL: Every element in the "entities" list MUST be a full object with "name" and "type". Under NO circumstances should you return plain strings in the "entities" list.
        4. If no entities or relationships are found, return empty lists: {{"entities": [], "relationships": []}}
        
        Return ONLY valid JSON. Do not include any explanation or markdown formatting outside of the JSON block.
        
        Text:
        "{chunk}"
        """
        
        try:
            resp = await json_llm.ainvoke(prompt, stop=["<|eot_id|>", "<|end_of_text|>"])
            content = resp.content.strip()
            finish_reason = resp.response_metadata.get("finish_reason", "unknown")
            tokens = resp.response_metadata.get("token_usage", {}).get("completion_tokens", 0)
            print(f"Chunk {i}: len={len(chunk)} | finish_reason={finish_reason} | tokens={tokens}")
            if tokens > 500 or finish_reason == "length":
                print(f"--- FAILED CHUNK {i} CONTENT ---")
                print(chunk)
                print(f"--- MODEL OUTPUT ---")
                print(repr(content))
                print("-" * 50)
        except Exception as e:
            print(f"Chunk {i} failed with error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
