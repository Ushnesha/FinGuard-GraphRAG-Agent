from scripts.load_data import load_finqa_corpus
import os

# --- DATA CORPUS CONFIGURATION ---
FinQA_data_path = "data/FinQA/train.json"
FinQA_corpus = load_finqa_corpus(FinQA_data_path)

MEGA_CORPUS = [{"CORPUS" : FinQA_corpus[:200],
"QUERY" : ["What was the percentage increase in total aircraft fuel expense for mainline and regional operations from 2016 to 2018?", "By what percentage did Intel Corporation's total cash and investments grow from December 29, 2012 to December 28, 2013?", "What is the total estimated value (in thousands of dollars) of the restricted stock and restricted stock units granted to employees during the fiscal year ended March 31, 2012?","What is the net difference in the fair value of forward exchange contracts between October 31, 2009, and November 1, 2008, under a scenario of a 10\% unfavorable movement in foreign currency exchange rates?", "In fiscal 2019, what percentage of the net cash provided by operating activities was spent on the purchases of land, buildings, and equipment?"]}]

# --- ENVIRONMENT VARIABLES & CONNECTION URLS ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_API_URL = "https://api.tavily.com/search"

# --- SYSTEM HYPERPARAMETERS ---
LLM_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 2000

# --- RETRIEVAL & VECTOR STORE CONFIGURATION ---
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_DIMENSION = 384
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120
QDRANT_PATH = "./qdrant_db"
QDRANT_COLLECTION = "local_chunks_minilm"