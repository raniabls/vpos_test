"""
embeddings.py — ChromaDB pour Izzy (Djezzy)
Chunking intelligent : plusieurs chunks par offre
  - Chunk résumé  : "TOD 1 MOIS — 10 Go — 1800 DA — 30 jours"
  - Chunk prix    : "TOD 1 MOIS coûte 1800 dinars pour 30 jours"
  - Chunk data    : "TOD 1 MOIS offre 10 Go d'internet"
  - Chunk complet : contenu original (fallback)
"""

import os
import re
import json
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb.utils import embedding_functions
from database import SessionLocal, Offer, FAQ, Service
from groq import Groq

CHROMA_DIR     = os.getenv("CHROMA_DIR", "chroma_db/")
os.makedirs(CHROMA_DIR, exist_ok=True)
MODEL_NAME     = "paraphrase-multilingual-MiniLM-L12-v2"
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
# ANcien modele " mmarco-mMiniLMv2-L12-H384-v1"


# ════════════════════════════════════════════════════════════════════
#  MODÈLES
# ════════════════════════════════════════════════════════════════════

def get_reranker():
    print("⏳ Chargement du reranker...")
    reranker = CrossEncoder(RERANKER_MODEL)
    print("✅ Reranker chargé")
    return reranker

def get_embedder():
    print("⏳ Chargement du modèle SentenceTransformer...")
    embedder = SentenceTransformer(MODEL_NAME)
    print("✅ Modèle chargé")
    return embedder


# ════════════════════════════════════════════════════════════════════
#  PARSING DU FORMAT PIPE
#  Format : [fichier.csv] Clé1: Val1 | Clé2: Val2 | ...
# ════════════════════════════════════════════════════════════════════

def parser_contenu(content: str) -> dict:
    content_clean = re.sub(r'^\[.*?\]\s*', '', content).strip()
    champs = {}
    for partie in content_clean.split('|'):
        partie = partie.strip()
        if ':' in partie:
            cle, _, valeur = partie.partition(':')
            champs[cle.strip().lower()] = valeur.strip()
    return champs


def extraire_valeur_numerique(texte: str) -> float:
    match = re.search(r'(\d+(?:\.\d+)?)', texte)
    return float(match.group(1)) if match else 0.0

# ════════════════════════════════════════════════════════════════════
#  CHUNKING INTELLIGENT : Au lieu de stocker une seule phrase énorme créer plusieurs chunks. 
# Chaque chunk optimise une recherche différente et il es transformer en vecteur
# ════════════════════════════════════════════════════════════════════

def creer_chunks(doc_id: str, content: str, category: str,
                 meta: dict) -> list[dict]:
    chunks = []
    champs = parser_contenu(content)

    nom = (champs.get("nom_offre") or champs.get("offre") or
           champs.get("nom") or champs.get("name") or
           champs.get("forfait") or champs.get("pack") or
           champs.get("produit") or "").strip()
    if not nom:
        for v in champs.values():
            v = v.strip()
            if v and not re.match(r"^\d", v) and len(v) > 2:
                nom = v
                break
    prix_str = (champs.get("prix_da") or champs.get("prix") or
                champs.get("price") or "")
    data_str = (champs.get("volume_internet_go") or champs.get("data_go") or
                champs.get("internet") or champs.get("data") or "")
    duree_str = (champs.get("validite_jours") or champs.get("duree_j") or
                 champs.get("validite") or champs.get("duree") or "")
    pays_str  = champs.get("pays", "")

    prix  = extraire_valeur_numerique(prix_str)  if prix_str  else 0.0
    data  = extraire_valeur_numerique(data_str)  if data_str  else 0.0
    duree = extraire_valeur_numerique(duree_str) if duree_str else 0.0

    if not nom:
        nom = content[:50].strip()

    # ── Chunk 0 : Résumé dense ──
    parties_resume = [nom]
    if prix  > 0: parties_resume.append(f"{int(prix)} DA")
    if data  > 0: parties_resume.append(f"{data} Go internet")
    if duree > 0: parties_resume.append(f"{int(duree)} jours")
    if pays_str:  parties_resume.append(f"pays: {pays_str}")

    chunk_resume = " — ".join(parties_resume)
    chunks.append({
        "id"        : f"{doc_id}_chunk0",
        "content"   : chunk_resume,
        "chunk_type": "resume",
        "source_id" : doc_id,
        "original"  : content,
    })

    # ── Chunk 1 : Prix / Budget ──
    if prix > 0:
        if duree > 0:
            chunk_prix = (
                f"{nom} coûte {int(prix)} dinars algériens "
                f"pour {int(duree)} jours"
            )
        else:
            chunk_prix = f"{nom} coûte {int(prix)} dinars algériens"
        if data > 0:
            chunk_prix += f" avec {data} Go de données"

        chunks.append({
            "id"        : f"{doc_id}_chunk1",
            "content"   : chunk_prix,
            "chunk_type": "prix",
            "source_id" : doc_id,
            "original"  : content,
        })

    # ── Chunk 2 : Data / Internet ──
    if data > 0:
        if prix > 0:
            chunk_data = (
                f"{nom} offre {data} Go d'internet "
                f"à {int(prix)} dinars algériens"
            )
        else:
            chunk_data = f"{nom} offre {data} Go d'internet"
        if duree > 0:
            chunk_data += f" valable {int(duree)} jours"

        chunks.append({
            "id"        : f"{doc_id}_chunk2",
            "content"   : chunk_data,
            "chunk_type": "data",
            "source_id" : doc_id,
            "original"  : content,
        })

    # ── Chunk 3 : Contenu complet (original) ──
    content_clean = re.sub(r'^\[.*?\]\s*', '', content).strip()
    chunks.append({
        "id"        : f"{doc_id}_chunk3",
        "content"   : content_clean,
        "chunk_type": "complet",
        "source_id" : doc_id,
        "original"  : content,
    })

    return chunks


# ════════════════════════════════════════════════════════════════════
#  EXTRACTION MÉTADONNÉES
# ════════════════════════════════════════════════════════════════════

EXTRACTION_META_SYSTEM = """Tu es un extracteur de métadonnées pour des offres téléphoniques Djezzy (Algérie).

Analyse le texte de l'offre et retourne UNIQUEMENT un JSON :
{
  "prix": <int>,
  "prix_remise": <int>,
  "data_go": <float>,
  "illimite": <bool>,
  "duree_j": <int>,
  "reseau": <"4g"|"5g"|"3g">,
  "type_offre": <"prepaye"|"postpaye"|"streaming"|"roaming">,
  "roaming": <bool>,
  "nom_offre": <str>
}

Règles :
- UNIQUEMENT le JSON, rien d'autre
- Prix en DA/dinar → nombre entier
- Mo/MB → Go (diviser par 1024)
- "roaming" si pays étranger, international, Hadj, Omra mentionnés
- "streaming" si TOD, Shahid, Netflix, YouTube mentionnés
- duree_j : "1 mois"=30, "2 mois"=60, "1 semaine"=7
- illimite: true seulement si explicitement écrit
"""

_meta_cache: dict[str, dict] = {}

def extraire_metadonnees(content: str, category: str,
                          groq_client=None) -> dict:
    meta_defaut = {
        "categorie"  : category,
        "prix"       : 0,
        "prix_remise": 0,
        "data_go"    : 0.0,
        "illimite"   : False,
        "duree_j"    : 30,
        "reseau"     : "4g",
        "type_offre" : "prepaye",
        "roaming"    : False,
        "nom_offre"  : "",
    }

    champs = parser_contenu(content)
    if champs:
        prix_str  = (champs.get("prix_da") or champs.get("prix") or "")
        data_str  = (champs.get("volume_internet_go") or champs.get("data_go") or
                     champs.get("internet") or "")
        duree_str = (champs.get("validite_jours") or champs.get("duree_j") or
                     champs.get("validite") or "")
        nom       = (champs.get("nom_offre") or champs.get("offre") or
                     champs.get("nom") or champs.get("name") or
                     champs.get("forfait") or champs.get("pack") or
                     champs.get("produit") or "")

        prix  = int(extraire_valeur_numerique(prix_str))  if prix_str  else 0
        data  = extraire_valeur_numerique(data_str)       if data_str  else 0.0
        duree = int(extraire_valeur_numerique(duree_str)) if duree_str else 30

        if prix > 0 or data > 0:
            meta_defaut.update({
                "prix"      : prix,
                "data_go"   : data,
                "duree_j"   : duree if duree > 0 else 30,
                "nom_offre" : nom,
                "illimite"  : any(kw in content.lower() for kw in
                                  ["illimit", "unlimited", "غير محدود"]),
                "reseau"    : "5g" if "5g" in content.lower() else "4g",
                "roaming"   : any(kw in content.lower() for kw in
                                  ["roaming", "international", "hadj", "omra",
                                   "espagne", "turquie", "france", "étranger"]),
                "type_offre": ("streaming" if any(kw in content.lower() for kw in
                                                   ["tod", "shahid", "netflix"])
                               else "roaming" if any(kw in content.lower() for kw in
                                                      ["roaming", "hadj", "omra"])
                               else "prepaye"),
            })
            print(f"  ✅ Parse direct : {nom} | {prix} DA | {data} Go | {duree}j")
            return meta_defaut

    return meta_defaut


# ════════════════════════════════════════════════════════════════════
#  INDEX CHROMADB
# ════════════════════════════════════════════════════════════════════

def load_or_build_index(embedder, groq_client=None):
    """
    Charge ou construit ChromaDB avec chunking intelligent.
    Chaque offre génère 2 à 4 chunks selon ses attributs.
    """
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME
    )

    # ── get_or_create_collection : PAS de metadatas ici ──
    collection = chroma_client.get_or_create_collection(
        name               = "izzy_offers",
        embedding_function = ef,
        metadata           = {"hnsw:space": "cosine"}
    )

    db = SessionLocal()
    try:
        documents = []
        for Model in [Offer, FAQ, Service]:
            rows = db.query(Model).filter_by(is_active=True).all() # recupere donne depuis postgres
            for r in rows:
                documents.append({
                    "id"      : f"{r.id}_{Model.__tablename__}",
                    "content" : r.content,
                    "category": r.category or "general"
                })
            print(f"  📋 {Model.__tablename__}: {len(rows)} documents actifs")
    finally:
        db.close()

    if not documents:
        print("⚠️  Aucun document en base !")
        return collection, []

    existing_ids = set(collection.get()["ids"])

    tous_chunks = []
    for doc in documents:
        meta   = extraire_metadonnees(doc["content"], doc["category"], groq_client)
        chunks = creer_chunks(doc["id"], doc["content"], doc["category"], meta)
        for chunk in chunks:
            if chunk["id"] not in existing_ids:
                chunk_meta = {**meta, "chunk_type": chunk["chunk_type"],
                              "source_id": chunk["source_id"]}
                tous_chunks.append({
                    "id"      : chunk["id"],
                    "content" : chunk["content"],
                    "original": chunk["original"],
                    "meta"    : chunk_meta,
                })

    if tous_chunks:
        print(f"🔄 Ajout de {len(tous_chunks)} chunks "
              f"({len(documents)} offres × ~{len(tous_chunks)//len(documents)} chunks/offre)...")

        batch_size = 100
        for i in range(0, len(tous_chunks), batch_size):
            # ── Fix 4 : "original" inclus dans les métadonnées ──
            lot = tous_chunks[i:i + batch_size]
            collection.add(
                ids       = [c["id"]      for c in lot],
                documents = [c["content"] for c in lot],
                metadatas = [{**c["meta"], "original": c["original"]} for c in lot],
            )
            print(f"  ↳ {min(i+batch_size, len(tous_chunks))}/{len(tous_chunks)} chunks ajoutés")

        print(f"✅ ChromaDB — {collection.count()} chunks total")
    else:
        print(f"✅ ChromaDB à jour — {collection.count()} chunks")

    all_contents = [d["content"] for d in documents]
    return collection, all_contents


def rebuild_index(embedder, groq_client=None):
    """Reconstruit ChromaDB depuis zéro."""
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        chroma_client.delete_collection("izzy_offers")
        print("🗑️  Collection supprimée pour reconstruction")
    except Exception:
        pass
    return load_or_build_index(embedder, groq_client)