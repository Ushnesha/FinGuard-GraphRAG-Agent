import os
import json
import asyncio
import hashlib
from typing import List
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from hybrid_search_engine import HybridSearchEngine
from config import MEGA_CORPUS

CORPUS = MEGA_CORPUS[0]["CORPUS"]
QUERY = MEGA_CORPUS[0]["QUERY"][1]

# Define rigid schemas for structured output
class Entity(BaseModel):
    name: str = Field(description="Name of the entity, normalized to lowercase")
    type: str = Field(description="Entity type: COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, or TIME_PERIOD")

class Relationship(BaseModel):
    source: str = Field(description="Source entity name")
    type: str = Field(description="Relationship type: PART_OF, REPORTS, FOR_PERIOD, or ACQUIRED")
    target: str = Field(description="Target entity name")

class GraphExtraction(BaseModel):
    entities: List[Entity]
    relationships: List[Relationship]

class ExtractedQueryEntity(BaseModel):
    text: str = Field(description="The exact entity text mentioned in the query, e.g. 'Apple'")
    type: str = Field(description="The type of entity: COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, or TIME_PERIOD")

class QueryExtractionResult(BaseModel):
    entities: List[ExtractedQueryEntity]


class GraphRAGPipeline:
    def __init__(self, documents: list = CORPUS):
        self.raw_documents = documents
        corpus_str = "".join(sorted(self.raw_documents))
        self.corpus_hash = hashlib.md5(corpus_str.encode("utf-8")).hexdigest()
        
        self.documents = []
        for doc in self.raw_documents:
            self.documents.extend(self._chunk_document(doc))
        
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # self.llm = ChatOllama(
        #     model="llama3.2:3b",
        #     temperature=0,
        #     base_url=self.ollama_base_url
        # )
        self.llm = ChatOpenAI(
            model="meta-llama/Meta-Llama-3-8B-Instruct", 
            openai_api_key="none",                          # vLLM doesn't require a real API key
            openai_api_base=os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1"),
            temperature=0,
            max_tokens=1000,
            model_kwargs={
                "response_format": {"type": "json_object"},
                "stop": ["<|eot_id|>", "<|end_of_text|>"]
            }
        )
        
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password123")
        self.neo4j_driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password)
        )
        if self._is_graph_initialize_needed():
            self._initialize_knowledge_graph()

    def _is_graph_initialize_needed(self) -> bool:
        """Check if the Neo4j database has no Entity nodes or is out of sync with the corpus."""
        with self.neo4j_driver.session() as session:
            # 1. Check if we have any Entity nodes
            result = session.run("MATCH (e:Entity) RETURN count(e) AS count")
            record = result.single()
            if record["count"] == 0:
                return True
                
            # 2. Check if the stored corpus hash matches the current corpus hash
            result = session.run("MATCH (m:Metadata {id: 1}) RETURN m.corpus_hash AS hash")
            record = result.single()
            if not record or record["hash"] != self.corpus_hash:
                return True
                
            return False

    def _chunk_document(self, doc: str, max_chars: int = 600, overlap: int = 120) -> list:
        """
        Chunks documents while keeping tables (lines containing '|') completely intact.
        """
        lines = doc.split("\n")
        chunks = []
        
        current_text_block = []
        current_table_block = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # Check if this line is part of a table
            is_table_line = "|" in stripped
            
            if is_table_line:
                if not in_table:
                    # Flush accumulated text block before starting table
                    if current_text_block:
                        chunks.extend(self._chunk_text_block("\n".join(current_text_block), max_chars, overlap))
                        current_text_block = []
                    in_table = True
                current_table_block.append(stripped)
            else:
                if in_table:
                    # Flush table block completely intact
                    if current_table_block:
                        chunks.append("\n".join(current_table_block))
                        current_table_block = []
                    in_table = False
                current_text_block.append(stripped)

        # Flush any remaining blocks
        if in_table and current_table_block:
            chunks.append("\n".join(current_table_block))
        elif current_text_block:
            chunks.extend(self._chunk_text_block("\n".join(current_text_block), max_chars, overlap))

        return chunks

    def _chunk_text_block(self, text: str, max_chars: int, overlap: int) -> list:
        """Helper to chunk standard text paragraph blocks."""
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
                    end = boundary + 1  # include the separator character
            chunks.append(text[start:end].strip())
            start = end - overlap
            if start >= len(text) or end >= len(text):
                break
            if start <= 0 or start == end - overlap:
                start = end
        return [c for c in chunks if c]
        

    def _ensure_indexes(self):
        """Ensure uniqueness constraints and indexes exist before insertion."""
        with self.neo4j_driver.session() as session:
            session.run("""
                CREATE CONSTRAINT entity_name_unique IF NOT EXISTS
                FOR (e:Entity) REQUIRE e.name IS UNIQUE
            """)

    async def _extract_from_chunk(self, doc: str) -> GraphExtraction:
        """Asynchronously extract graph data from a single document chunk."""
        prompt = f"""
        Identify all key Entities and Relationships in the text below.
        
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
        "{doc}"
        """
        try:
            # Direct invocation without structured output wrapper to avoid guided decoding overhead
            response = await self.llm.ainvoke(prompt)
            content = response.content.strip()
            
            # Clean up markdown code wraps if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content)
            
            # Manually map to Pydantic models for type safety with the downstream code
            entities = []
            for item in data.get("entities", []):
                if isinstance(item, dict) and "name" in item and "type" in item:
                    entities.append(Entity(name=str(item["name"]), type=str(item["type"])))
                    
            relationships = []
            for item in data.get("relationships", []):
                if isinstance(item, dict) and "source" in item and "type" in item and "target" in item:
                    relationships.append(
                        Relationship(
                            source=str(item["source"]),
                            type=str(item["type"]),
                            target=str(item["target"])
                        )
                    )
            return GraphExtraction(entities=entities, relationships=relationships)
        except Exception as e:
            print(f"Error extracting chunk: {e}")
            return GraphExtraction(entities=[], relationships=[])

    def _batch_write_to_neo4j(self, all_entities: list, all_relationships: list):
        """Write all collected graph elements in batched Cypher operations."""
        # Convert Pydantic objects to dicts if they aren't already
        all_entities = [e.model_dump() if hasattr(e, "model_dump") else e for e in all_entities]
        all_relationships = [r.model_dump() if hasattr(r, "model_dump") else r for r in all_relationships]
        
        allowed_rel_types = {"PART_OF", "REPORTS", "FOR_PERIOD", "ACQUIRED"}
        
        # Deduplicate & format entities
        deduped_entities = {
            e["name"].lower().strip(): e["type"].upper().strip() 
            for e in all_entities if e.get("name") and e.get("type")
        }
        entities_batch = [{"name": k, "type": v} for k, v in deduped_entities.items()]

        # Group relationships by allowed type
        rels_by_type = {}
        for rel in all_relationships:
            r_type = rel.get("type", "").upper().strip()
            if r_type in allowed_rel_types:
                rels_by_type.setdefault(r_type, []).append({
                    "source": rel["source"].lower().strip(),
                    "target": rel["target"].lower().strip()
                })

        with self.neo4j_driver.session() as session:
            # 1. Batch insert entities
            if entities_batch:
                session.run(
                    """
                    UNWIND $batch AS item
                    MERGE (e:Entity {name: item.name})
                    ON CREATE SET e.type = item.type
                    """,
                    batch=entities_batch
                )

            # 2. Batch insert relationships grouped by edge label
            for r_type, rel_list in rels_by_type.items():
                session.run(
                    f"""
                    UNWIND $batch AS item
                    MERGE (a:Entity {{name: item.source}})
                    MERGE (b:Entity {{name: item.target}})
                    MERGE (a)-[:{r_type}]->(b)
                    """,
                    batch=rel_list
                )



    async def _knowledge_graph_builder(self, concurrency_limit: int = 10):
        print("Initializing Neo4j Knowledge dynamically from corpus...")
        # Programmatically write core entity linkages to Neo4j
        strt = time()

        self._ensure_indexes()

        with self.neo4j_driver.session() as session:
            # Clean database first
            session.run("MATCH (n) DETACH DELETE n")
            
        documents = self.documents
        
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def worker(doc):
            async with semaphore:
                return await self._extract_from_chunk(doc)

        # Run extraction jobs concurrently across chunks
        print(f"Extracting relationships concurrently (Concurrency: {concurrency_limit})...")
        results: List[GraphExtraction] = await asyncio.gather(
            *(worker(doc) for doc in documents)
        )

        # Aggregate results across all chunks
        all_entities = []
        all_relationships = []
        for res in results:
            all_entities.extend([e.model_dump() for e in res.entities])
            all_relationships.extend([r.model_dump() for r in res.relationships])

        # Writing to Neo4j in bulk
        print("Writing extracted data to Neo4j in batch...")
        self._batch_write_to_neo4j(all_entities, all_relationships)
        
        # Save the corpus hash to Neo4j metadata
        with self.neo4j_driver.session() as session:
            session.run(
                "MERGE (m:Metadata {id: 1}) SET m.corpus_hash = $hash",
                hash=self.corpus_hash
            )
        print("Graph initialization complete!")
        print(f"Time taken for Graph Initialization: {(time()-strt)*1000}ms")



    def _initialize_knowledge_graph(self):
        """Synchronous wrapper to run the async graph builder."""
        asyncio.run(self._knowledge_graph_builder())

    def extract_and_link_entities(self, user_query: str) -> dict:
        """
        1. Extract entities from the user query via LLM.
        2. Normalize strings.
        3. Match extracted entities against existing Neo4j nodes.
        """
        prompt = f"""
        Extract all domain-specific entities from the following user query.
        Allowed Types: [COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, TIME_PERIOD]

        You must format your response STRICTLY as a valid JSON object with this key structure:
        {{
            "entities": [
                {{"text": "entity name", "type": "ENTITY_TYPE"}}
            ]
        }}

        Return ONLY valid JSON. Do not include any explanation or markdown formatting outside of the JSON block.

        Query: "{user_query}"
        """
        # 1. LLM Extraction
        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Clean up markdown code wraps if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content)
            
            normalized_entities = []
            for item in data.get("entities", []):
                if isinstance(item, dict) and "text" in item and "type" in item:
                    normalized_entities.append({
                        "text": str(item["text"]).lower().strip(),
                        "type": str(item["type"]).upper().strip()
                    })
        except Exception as e:
            print(f"Extraction failed: {e}")
            return {"raw_entities": [], "matched_nodes": []}

        if not normalized_entities:
            return {"raw_entities": [], "matched_nodes": []}

        # 2. Match entities against Neo4j using token overlap
        matched_nodes = []
        
        # Stop words to ignore during matching to avoid false positives (e.g. matching everything with "the" or "company")
        STOP_WORDS = {"the", "of", "and", "a", "company", "in", "to", "for", "contracts", "rates", "rate", "inc", "co", "ltd"}

        try:
            with self.neo4j_driver.session() as session:
                # Fetch all existing entities in the graph
                result = session.run("MATCH (e:Entity) RETURN e.name AS name, e.type AS type")
                db_entities = [{"name": r["name"], "type": r["type"]} for r in result]
                
            for ext_entity in normalized_entities:
                ext_name = ext_entity["text"].lower().strip()
                ext_tokens = set(ext_name.split()) - STOP_WORDS
                
                if not ext_tokens:
                    ext_tokens = set(ext_name.split())
                    
                for db_ent in db_entities:
                    db_name_lower = db_ent["name"].lower().strip()
                    
                    # Check for exact match or strict substring containment first
                    if ext_name == db_name_lower or ext_name in db_name_lower or db_name_lower in ext_name:
                        if db_ent not in matched_nodes:
                            matched_nodes.append(db_ent)
                        continue
                    
                    # Token-based overlap check
                    db_tokens = set(db_name_lower.split()) - STOP_WORDS
                    if not db_tokens:
                        db_tokens = set(db_name_lower.split())
                        
                    overlap = ext_tokens.intersection(db_tokens)
                    if len(overlap) >= 2 or (len(ext_tokens) == 1 and len(overlap) >= 1):
                        if db_ent not in matched_nodes:
                            matched_nodes.append(db_ent)
        except Exception as e:
            print(f"Error matching entities against Neo4j: {e}")

        return {
            "raw_extracted": normalized_entities,
            "matched_nodes": matched_nodes
        }



    def query_graph_relationships(self, user_query: str, max_triplets: int = 20) -> list:
        """
        1. Extract and link entities from user query.
        2. Traverse 1-hop relationships (in both directions) for matched nodes.
        3. Return structured string relationships for LLM prompt augmentation.
        """

        # 1. Reuse entity extraction & linking logic
        extraction_result = self.extract_and_link_entities(user_query)
        matched_nodes = extraction_result.get("matched_nodes", [])

        if not matched_nodes:
            return []

        # Get target entity names that exist in the graph
        entity_names = [node["name"] for node in matched_nodes]

        # 2. Fetch 1-hop context (both incoming and outgoing relationships)
        relations = []
        with self.neo4j_driver.session() as session:
            cypher = """
            MATCH (n:Entity)
            WHERE n.name IN $names
            MATCH (n)-[r]-(m:Entity)
            RETURN n.name AS source, type(r) AS rel, m.name AS target, labels(n) AS source_label
            LIMIT $limit
            """
            result = session.run(cypher, names=entity_names, limit=max_triplets)

            for record in result:
                triplet = f"({record['source']}) -[{record['rel']}]-> ({record['target']})"
                if triplet not in relations:
                    relations.append(triplet)

        return relations
        

    def run_pipeline(self, query: str, search_engine: HybridSearchEngine) -> str:

        text_context = search_engine.search(query)
        graph_context = self.query_graph_relationships(query)
        context_str = "Text Context:\n" + "\n".join(text_context) + "\n\nGraph Context:\n" + "\n".join(graph_context)
        prompt = f"Using ONLY the context below, answer the query.\n\nContext:\n{context_str}\n\nQuery: {query}"
        
        # llm = ChatOllama(
        #     model=model_name,
        #     temperature=0,
        #     base_url=self.ollama_base_url
        # )
        response = self.llm.invoke(prompt).content
        return response, context_str

    def delete_graph(self):
        with self.neo4j_driver.session() as session:
            # Clean database first
            session.run("MATCH (n) DETACH DELETE n")


if __name__ == "__main__":
        from time import time
        # search_engine = HybridSearchEngine(CORPUS)
        pipeline = GraphRAGPipeline(CORPUS)
        try:
            pipeline.neo4j_driver.verify_connectivity()
            print("Successfully connected to Neo4j database!")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
        start_time = time()
        formatted_context = pipeline.query_graph_relationships(QUERY)
        print(f"Time taken to extract query context from graph: {(time() - start_time) * 1000} ms")
        print(f"\n--- FORMATTED FINAL CONTEXT FOR QUERY : {QUERY} ---")
        print(formatted_context)
        # pipeline.delete_graph()
        # search_engine.close()
        pipeline.neo4j_driver.close()
    