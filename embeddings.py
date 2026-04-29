import os
import pickle
import faiss
from sentence_transformers import SentenceTransformer

CACHE_FILE = "faiss_cache/precomputed_embeddings.pkl"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

def get_embedder():
    print("Loading SentenceTransformer model...")
    embedder = SentenceTransformer(MODEL_NAME)
    print("Model loaded")
    return embedder

def load_or_build_index(embedder=None):
    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError(
            f"{CACHE_FILE} not found. Run: python generate_embeddings.py"
        )

    print("Loading precomputed FAISS index...")

    with open(CACHE_FILE, "rb") as f:
        data = pickle.load(f)

    index = data["faiss_index"]
    documents = data["documents"]

    print(f"FAISS index loaded: {len(documents)} documents")

    return index, documents

def rebuild_index(embedder=None):
    return load_or_build_index(embedder)