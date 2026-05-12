import os
import hashlib
import faiss
from sentence_transformers import SentenceTransformer
from database import SessionLocal, Offer, FAQ, Service, EmbeddingCache

FAISS_CACHE_DIR = "faiss_cache/"
os.makedirs(FAISS_CACHE_DIR, exist_ok=True)
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def get_embedder():
    print("⏳ Chargement du modèle SentenceTransformer...")
    embedder = SentenceTransformer(MODEL_NAME)
    print("✅ Modèle chargé")
    return embedder


def _compute_hash(documents):
    content = "\n".join(sorted(documents))
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _build_faiss_index(documents, embedder):
    print(f"⏳ Calcul des embeddings pour {len(documents)} documents...")
    emb = embedder.encode(documents, convert_to_numpy=True, show_progress_bar=True)
    faiss.normalize_L2(emb)
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    print(f"✅ Index FAISS construit — {idx.ntotal} vecteurs")
    return idx


def load_or_build_index(embedder):
    db = SessionLocal()
    try:
        documents = []
        for Model in [Offer, FAQ, Service]:
            # POUR CHAQUE TABLE LIT DEPUIS POSTGRESQL
            rows = db.query(Model).filter_by(is_active=True).all()
            documents.extend([r.content for r in rows])
            print(f"  📋 {Model.__tablename__}: {len(rows)} documents actifs")

        if not documents:
            print("⚠️  Aucun document en base de données !")
            return None, []

        current_hash = _compute_hash(documents) # calcule le hash
        cache = db.query(EmbeddingCache).filter_by(content_hash=current_hash).first()
        
        #Verifie si existe deja
        if cache and os.path.exists(cache.faiss_path):
            print(f"✅ Index FAISS chargé depuis cache ({cache.offer_count} docs)")
            return faiss.read_index(cache.faiss_path), documents

        print("🔄 Recalcul de l'index FAISS...")
        index      = _build_faiss_index(documents, embedder)
        faiss_path = os.path.join(FAISS_CACHE_DIR, f"index_{current_hash[:8]}.faiss")
        faiss.write_index(index, faiss_path)

        old = db.query(EmbeddingCache).first()
        if old:
            if os.path.exists(old.faiss_path):
                os.remove(old.faiss_path)
            db.delete(old)

        db.add(EmbeddingCache(
            content_hash=current_hash,
            faiss_path=faiss_path,
            offer_count=len(documents)
        ))
        db.commit()
        print(f"✅ Index FAISS sauvegardé → {faiss_path}")
        return index, documents

    finally:
        db.close()


def rebuild_index(embedder):
    return load_or_build_index(embedder)