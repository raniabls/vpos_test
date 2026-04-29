import os
import pickle
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer

DATA_DIR = "augmented_files"
CACHE_DIR = "faiss_cache"
CACHE_FILE = os.path.join(CACHE_DIR, "precomputed_embeddings.pkl")

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

os.makedirs(CACHE_DIR, exist_ok=True)

def row_to_text(row, source_file):
    parts = []
    for col, value in row.items():
        if pd.notna(value):
            parts.append(f"{col}: {value}")
    return f"Source: {source_file} | " + " | ".join(parts)

def main():
    print("Loading model...")
    model = SentenceTransformer(MODEL_NAME)

    documents = []

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".csv"):
            path = os.path.join(DATA_DIR, filename)
            print(f"Reading {filename}")

            df = pd.read_csv(path)

            for _, row in df.iterrows():
                text = row_to_text(row, filename)
                documents.append(text)

    if not documents:
        raise ValueError("No CSV data found in augmented_files/")

    print(f"Generating embeddings for {len(documents)} documents...")

    embeddings = model.encode(
        documents,
        convert_to_numpy=True,
        show_progress_bar=True
    )

    faiss.normalize_L2(embeddings)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(
            {
                "model_name": MODEL_NAME,
                "documents": documents,
                "embeddings_shape": embeddings.shape,
                "faiss_index": index,
            },
            f
        )

    print(f"Saved embeddings cache to {CACHE_FILE}")
    print(f"Total documents: {len(documents)}")

if __name__ == "__main__":
    main()