import os
import json
import asyncio
import json
from typing import List
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
from langchain_ollama import ChatOllama
from hybrid_search_engine import HybridSearchEngine
from config import CORPUS, QUERY

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
    def __init__(self):
        self.search_engine = HybridSearchEngine(CORPUS)
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.llm = ChatOllama(
            model="llama3.2:3b",
            temperature=0,
            base_url=self.ollama_base_url
        )
        self.structured_llm = self.llm.with_structured_output(GraphExtraction, method="json_mode")
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
                
            # 2. Check if the stored corpus hash matches the current search engine hash
            result = session.run("MATCH (m:Metadata {id: 1}) RETURN m.corpus_hash AS hash")
            record = result.single()
            if not record or record["hash"] != self.search_engine.corpus_hash:
                return True
                
            return False
        

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

        You must format your response STRICTLY as a JSON object matching this structure:
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
        
        Text:
        "{doc}"
        """
        try:
            # Using structured output guarantees clean data directly matching the Pydantic schema
            return await self.structured_llm.ainvoke(prompt)
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

        self._ensure_indexes()

        with self.neo4j_driver.session() as session:
            # Clean database first
            session.run("MATCH (n) DETACH DELETE n")
            
        documents = self.search_engine.documents
        
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
                hash=self.search_engine.corpus_hash
            )
        print("Graph initialization complete!")



    def _initialize_knowledge_graph(self):
        """Synchronous wrapper to run the async graph builder."""
        asyncio.run(self._knowledge_graph_builder())

    def extract_and_link_entities(self, user_query: str, model_name: str = "llama3.2:3b") -> dict:
        """
        1. Extract entities from the user query via LLM.
        2. Normalize strings.
        3. Match extracted entities against existing Neo4j nodes.
        """
        prompt = f"""
        Extract all domain-specific entities from the following user query.
        Allowed Types: [COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, TIME_PERIOD]

        You must format your response STRICTLY as a JSON object with this key structure:
        {{
            "entities": [
                {{"text": "entity name", "type": "ENTITY_TYPE"}}
            ]
        }}

        Query: "{user_query}"
        """
        
        llm = ChatOllama(
            model=model_name,
            temperature=0,
            base_url=self.ollama_base_url
        )
        structured_llm = llm.with_structured_output(QueryExtractionResult, method="json_mode")
        # 1. LLM Extraction
        try:
            extraction = structured_llm.invoke(prompt)
        except Exception as e:
            print(f"Extraction failed: {e}")
            return {"raw_entities": [], "matched_nodes": []}

        normalized_entities = [
            {"text": e.text.lower().strip(), "type": e.type.upper().strip()}
            for e in extraction.entities
        ]

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



    def query_graph_relationships(self, user_query: str, max_triplets: int = 20, model_name: str = "llama3.2:3b") -> list:
        """
        1. Extract and link entities from user query.
        2. Traverse 1-hop relationships (in both directions) for matched nodes.
        3. Return structured string relationships for LLM prompt augmentation.
        """

        # 1. Reuse entity extraction & linking logic
        extraction_result = self.extract_and_link_entities(user_query, model_name)
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
        

    def run_pipeline(self, query:str, model_name: str = "llama3.2:3b") -> str:

        text_context = self.search_engine.search(query)
        graph_context = self.query_graph_relationships(query)
        context_str = "Text Context:\n" + "\n".join(text_context) + "\n\nGraph Context:\n" + "\n".join(graph_context)
        prompt = f"Using ONLY the context below, answer the query.\n\nContext:\n{context_str}\n\nQuery: {query}"
        
        llm = ChatOllama(
            model=model_name,
            temperature=0,
            base_url=self.ollama_base_url
        )
        response = llm.invoke(prompt).content
        return response, context_str


if __name__ == "__main__":
    try:
        from time import time
        start_time = time()
        pipeline = GraphRAGPipeline()
        pipeline.neo4j_driver.verify_connectivity()
        print("Successfully connected to Neo4j database!")
        answer, formatted_context = pipeline.run_pipeline(QUERY)
        end_time = time()
        print(f"Time taken: {(end_time - start_time) * 1000} ms")
        print(f"\n--- FORMATTED FINAL CONTEXT FOR QUERY : {QUERY} ---")
        print(formatted_context)
        print("\n--- FINAL ANSWER ---")
        print(answer)

        pipeline.search_engine.close()
        pipeline.neo4j_driver.close()
    except Exception as e:
        print(f"Failed to connect to Neo4j: {e}")