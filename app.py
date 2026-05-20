import os
import uuid
import time
import json
import re
import numpy as np
from contextlib import asynccontextmanager

import edge_tts
import httpx

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from groq import Groq

from lingua import Language, LanguageDetectorBuilder

from database import get_db, init_db, Offer, FAQ, Service, Prompt, Conversation
from embeddings import get_embedder, load_or_build_index, rebuild_index, get_reranker


# ════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY manquant dans le fichier .env")

AUDIO_FOLDER = "static/audio/"
MAX_TOKENS   = 1000
MAX_HISTORY  = 10

os.makedirs(AUDIO_FOLDER, exist_ok=True)

EDGE_VOICES = {
    "fr": "fr-FR-DeniseNeural",
    "ar": "ar-DZ-AminaNeural",
    "en": "en-US-JennyNeural"
}

LANGUAGE_NAMES = {
    "fr": "French",
    "ar": "Arabic",
    "en": "English"
}

LANG_KEYWORDS = {
    "fr": ["bonjour", "salut", "bonsoir", "merci", "oui", "non", "aide",
           "comment", "quoi", "quel", "prix", "offre", "forfait", "je", "votre",
           "je voudrais", "c'est quoi", "combien", "activer", "recharger",
           "moins", "plus", "cher", "internet", "appel", "données"],
    "ar": ["مرحبا", "السلام", "شكرا", "نعم", "لا", "كيف", "ما", "سعر",
           "عرض", "مساعدة", "اريد", "عندي", "هل",
           "كيفاش", "واش", "بغيت", "ديناراتش", "راني", "نحب", "عطيني"],
    "en": ["hello", "hi", "yes", "no", "help", "how", "what", "price",
           "offer", "plan", "thanks", "good", "morning", "is", "are",
           "can", "have", "want", "does", "the", "my", "i", "dont",
           "activate", "explain", "need", "use",
           "how much", "i want", "can you", "tell me", "cheaper", "more"]
}

PHRASES_CONFIRMATION = [
    "je la prends", "celle-là", "oui cette offre", "i want this one",
    "je veux celle-ci", "je veux cette offre", "parfait je prends",
    "ça me convient", "je souscris", "بغيتها", "هذه تناسبني",
]

RERANKER_SEUILS = {
    "fr": 1.5,
    "en": 0.5,
    "ar": 0.8,   # était implicitement 0.0 — trop permissif
}


# ════════════════════════════════════════════════════════════════════
#  LIFESPAN
# ════════════════════════════════════════════════════════════════════

@asynccontextmanager # Lorsque FastAPI démarre exécute toutes les initialisations
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("   IZZY — Démarrage FastAPI + PostgreSQL")
    print("=" * 60)

    init_db() # crée les tables PostgreSQL.

    app.state.embedder = get_embedder() # Chargement du modèle Embedding
    app.state.reranker = get_reranker() # Chargement du modèle Reranker qui attribue un score de pertinence.

    # Groq client d'abord (nécessaire pour load_or_build_index LLM)
    app.state.groq_client = Groq(api_key=GROQ_API_KEY) # Création du client LLM

    # ── Index ChromaDB avec extraction métadonnées via LLM
    app.state.faiss_index, app.state.documents = load_or_build_index( # construit la base vectorielle
        app.state.embedder,
        app.state.groq_client   # ← extraction métadonnées via LLM
    )

    print("✅ Izzy est prête !\n")
    yield
    print("👋 Izzy s'arrête...")


# ════════════════════════════════════════════════════════════════════
#  FASTAPI
# ════════════════════════════════════════════════════════════════════

app = FastAPI(
    title    = "IZZY — Agent IA Djezzy",
    version  = "4.0.0",
    lifespan = lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════
#  MODÈLES PYDANTIC
# ════════════════════════════════════════════════════════════════════

class QuestionInput(BaseModel):
    question:   str
    session_id: str

class OfferInput(BaseModel):
    content:  str
    category: str = "general"

class OfferUpdate(BaseModel):
    content:   str  | None = None
    category:  str  | None = None
    is_active: bool | None = None

class PromptUpdate(BaseModel):
    content: str


# ════════════════════════════════════════════════════════════════════
#  DÉTECTION LANGUE
# ════════════════════════════════════════════════════════════════════

_lingua_detector = LanguageDetectorBuilder.from_languages(
    Language.FRENCH, Language.ARABIC, Language.ENGLISH
).build()


def _has_keyword(text: str, kw: str) -> bool:
    return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))


def detect_lang(text: str) -> str:
    text_lower = text.lower().strip()

    scores = {"fr": 0, "ar": 0, "en": 0}
    for lang, keywords in LANG_KEYWORDS.items():
        for kw in keywords:
            if _has_keyword(text_lower, kw):
                scores[lang] += 1

    best_lang  = max(scores, key=scores.get)
    best_score = scores[best_lang]
    if best_score > 0:
        return best_lang

    if sum(1 for c in text if '\u0600' <= c <= '\u06FF') > 0:
        return "ar"

    if len(text_lower) >= 10:
        try:
            result = _lingua_detector.detect_language_of(text)
            if result == Language.ARABIC:  return "ar"
            if result == Language.FRENCH:  return "fr"
            if result == Language.ENGLISH: return "en"
        except Exception:
            pass

    return "fr"


def detect_lang_response(answer: str, lang_question: str) -> str:
    arabic_chars = sum(1 for c in answer if '\u0600' <= c <= '\u06FF')
    if arabic_chars > 2:
        return "ar"

    if len(answer.strip()) >= 20:
        try:
            result = _lingua_detector.detect_language_of(answer)
            if result == Language.ARABIC:  return "ar"
            if result == Language.FRENCH:  return "fr"
            if result == Language.ENGLISH: return "en"
        except Exception:
            pass

    return lang_question


# ════════════════════════════════════════════════════════════════════
#  GESTION HISTORIQUE
# ════════════════════════════════════════════════════════════════════

def get_history(session_id: str, db: Session) -> list:
    messages = (
        db.query(Conversation)
        .filter_by(session_id=session_id)
        .order_by(Conversation.created_at.asc())
        .limit(MAX_HISTORY * 2)
        .all()
    )
    return [m.to_dict() for m in messages]


def save_message(session_id: str, role: str, content: str, lang: str, db: Session):
    db.add(Conversation(
        session_id=session_id, role=role, content=content, lang=lang
    ))
    db.commit()


def count_exchanges(session_id: str, db: Session) -> int:
    return db.query(Conversation).filter_by(session_id=session_id).count() // 2


# ════════════════════════════════════════════════════════════════════
#  HELPERS RAG
# ════════════════════════════════════════════════════════════════════

def est_confirmation(q: str) -> bool:
    q_lower = q.lower().strip()
    return len(q_lower.split()) <= 6 and any(p in q_lower for p in PHRASES_CONFIRMATION)


def dedupliquer_contexte(documents: list[str], embedder,
                          seuil: float = 0.88) -> list[str]:
    if len(documents) <= 1:
        return documents
    try:
        vecs = embedder.encode(documents, convert_to_numpy=True)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        indices_uniques = [0]
        for i in range(1, len(documents)):
            est_doublon = any(
                float(np.dot(vecs[i], vecs[j])) > seuil
                for j in indices_uniques
            )
            if not est_doublon:
                indices_uniques.append(i)
        result = [documents[i] for i in indices_uniques]
        if len(result) < len(documents):
            print(f"  🔄 Déduplication : {len(documents)} → {len(result)} docs uniques")
        return result
    except Exception as e:
        print(f"⚠️  Déduplication échouée : {e}")
        return documents


def nettoyer_contexte(context: str) -> str:
    context = re.sub(r'\[.*?\.csv\]', '', context)
    context = re.sub(
        r'\|\s*(?:category|is_active|needs_reindex|content)\s*:[^|{\n]*', '', context
    )
    context = re.sub(r'\bcontent\s*:\s*', '', context)
    return context.strip()


def get_original_content_by_source_id(source_id: str, db: Session) -> str | None:
    if not source_id or "_" not in source_id:
        return None
    try:
        id_str, table_name = source_id.split("_", 1)
        doc_id = int(id_str)
        if table_name == "offers":
            row = db.query(Offer).filter_by(id=doc_id).first()
        elif table_name == "faq":
            row = db.query(FAQ).filter_by(id=doc_id).first()
        elif table_name == "services":
            row = db.query(Service).filter_by(id=doc_id).first()
        else:
            row = None
        return row.content if row else None
    except Exception as e:
        print(f"⚠️  Erreur fetch original depuis PG ({source_id}): {e}")
        return None


# ════════════════════════════════════════════════════════════════════
#  EXTRACTION CONTRAINTES VIA LLM
# ════════════════════════════════════════════════════════════════════

EXTRACTION_SYSTEM = """Tu es un extracteur de contraintes pour un moteur de recherche d'offres téléphoniques Djezzy (Algérie).

Analyse la question et retourne UNIQUEMENT un JSON avec ces champs (null si non mentionné) :
{
  "prix_max": <int|null>,
  "prix_min": <int|null>,
  "prix_exact": <int|null>,
  "data_min": <float|null>,
  "data_max": <float|null>,
  "illimite": <true|null>,
  "reseau": <"4g"|"5g"|"3g"|null>,
  "duree_min": <int|null>,
  "roaming": <true|null>,
  "streaming": <true|null>,
  "exclure_streaming": <true|null>,
  "nom_offre": <str|null>         // nom si demandé ex: "3ayla", "student", "tod"
}

Règles :
- Retourne UNIQUEMENT le JSON, sans texte avant ou après
- null = pas de contrainte sur ce champ
- Utilise prix_exact UNIQUEMENT si l'utilisateur dit exactement 'à X DA' ou 'pour X DA'
- Ne mets JAMAIS prix_max ET prix_min ET prix_exact en même temps
- Si prix_exact est renseigné, laisse prix_max et prix_min à null
- "illimite": true SEULEMENT si explicitement demandé
- "exclure_streaming": true UNIQUEMENT si l'utilisateur dit explicitement qu'il ne veut PAS de streaming
- Prix en DA/dinar/دينار → extraire le nombre entier
- Durées : "1 mois"=30, "2 mois"=60, "1 semaine"=7
"""

# Extraction contraintes via LLM pour comprendre l’intention
def extraire_contraintes_llm(question: str, groq_client, lang: str) -> dict: 
    try:
        t0 = time.time()
        response = groq_client.chat.completions.create(
            model      = "llama-3.3-70b-versatile",
            messages   = [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user",   "content": question}
            ],
            max_tokens = 200,
            temperature= 0.0,
        )
        raw = response.choices[0].message.content.strip()
        print(f"⏱️  Extraction contraintes : {time.time() - t0:.3f}s | raw: {raw}")

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print("⚠️  Aucun JSON trouvé dans la réponse d'extraction")
            return {}

        data = json.loads(json_match.group())
        contraintes = {k: v for k, v in data.items() if v is not None}
        print(f"🎯 Contraintes extraites : {contraintes}")
        return contraintes

    except json.JSONDecodeError as e:
        print(f"⚠️  JSON invalide dans l'extraction : {e}")
        return {}
    except Exception as e:
        print(f"⚠️  Erreur extraction contraintes : {e}")
        return {}


def construire_filtre(contraintes: dict, collection) -> dict | None:
    if not contraintes:
        return None

    conditions = []

    if contraintes.get("prix_exact"):
        conditions.append({"prix": {"$eq": contraintes["prix_exact"]}})
    else:
        if contraintes.get("prix_max"):
            conditions.append({"prix": {"$lte": contraintes["prix_max"]}})
        if contraintes.get("prix_min"):
            conditions.append({"prix": {"$gte": contraintes["prix_min"]}})

    if contraintes.get("data_min"):
        conditions.append({"data_go": {"$gte": float(contraintes["data_min"])}})
    if contraintes.get("data_max"):
        conditions.append({"data_go": {"$lte": float(contraintes["data_max"])}})

    if contraintes.get("illimite") is True:
        conditions.append({"illimite": {"$eq": True}})

    if contraintes.get("reseau"):
        conditions.append({"reseau": {"$eq": contraintes["reseau"]}})

    if contraintes.get("duree_min"):
        conditions.append({"duree_j": {"$gte": contraintes["duree_min"]}})

    if contraintes.get("roaming") is True:
        conditions.append({"roaming": {"$eq": True}})

    if contraintes.get("streaming") is True:
        conditions.append({"type_offre": {"$eq": "streaming"}})
    elif contraintes.get("exclure_streaming") is True:
        conditions.append({"type_offre": {"$ne": "streaming"}})

    if not conditions:
        return None

    where_filter = {"$and": conditions} if len(conditions) > 1 else conditions[0]

    # Vérification que le filtre retourne des résultats
    try:
        test = collection.get(where=where_filter, limit=1)
        if not test["ids"]:
            print(f"⚠️  Filtre trop strict, fallback vector search pur")
            return None
        print(f"🔍 Filtre appliqué : {where_filter}")
        return where_filter
    except Exception as e:
        print(f"⚠️  Erreur vérification filtre : {e} → fallback vector search pur")
        return None


# ════════════════════════════════════════════════════════════════════
#  SQL SEARCH
# ════════════════════════════════════════════════════════════════════

def sql_search(contraintes: dict, db: Session, limit: int = 6) -> list[str]:
    if not contraintes:
        return []
    from sqlalchemy import and_
    resultats = []
    for Model in [Offer, FAQ, Service]:
        try:
            cols = {c.name for c in Model.__table__.columns}
            conditions = [Model.is_active == True]
            if "prix" in cols:
                if contraintes.get("prix_exact"):
                    conditions.append(Model.prix == contraintes["prix_exact"])
                else:
                    if contraintes.get("prix_max"):
                        conditions.append(Model.prix <= contraintes["prix_max"])
                        conditions.append(Model.prix > 0)
                    if contraintes.get("prix_min"):
                        conditions.append(Model.prix >= contraintes["prix_min"])
            if "data_go" in cols and contraintes.get("data_min"):
                conditions.append(Model.data_go >= contraintes["data_min"])
            if "data_go" in cols and contraintes.get("data_max"):
                conditions.append(Model.data_go <= contraintes["data_max"])
            if "illimite" in cols and contraintes.get("illimite") is True:
                conditions.append(Model.illimite == True)
            if "reseau" in cols and contraintes.get("reseau"):
                conditions.append(Model.reseau == contraintes["reseau"])
            if "duree_j" in cols and contraintes.get("duree_min"):
                conditions.append(Model.duree_j >= contraintes["duree_min"])
            if "roaming" in cols and contraintes.get("roaming") is True:
                conditions.append(Model.roaming == True)
            if "type_offre" in cols:
                if contraintes.get("streaming") is True:
                    conditions.append(Model.type_offre == "streaming")
                elif contraintes.get("exclure_streaming") is True:
                    conditions.append(Model.type_offre != "streaming")
            # Filtre nom_offre (recherche textuelle)
            if contraintes.get("nom_offre"):
                conditions.append(
                    Model.content.ilike(f"%{contraintes['nom_offre']}%")
                )

            if len(conditions) == 1:  # seulement is_active → skip
                continue
            rows = db.query(Model).filter(and_(*conditions)).limit(limit).all()
            if rows:
                print(f"  🗄️  SQL {Model.__tablename__} : {len(rows)} résultats")
                resultats.extend([r.content for r in rows])
        except Exception as e:
            print(f"⚠️  SQL {Model.__tablename__} : {e}")
    print(f"🗄️  SQL total : {len(resultats)} documents")
    return resultats


REWRITER_SYSTEM = """Tu es un assistant de reformulation de requêtes pour un chatbot télécom Djezzy.
Formule une question de recherche autonome, claire et concise en français, anglais ou arabe, en combinant la dernière question de l'utilisateur avec l'historique récent de la conversation.

Règles importantes :
- Si la dernière question fait référence à "d'autres" (ex: "y a-t-il d'autres offres ?", "autre chose ?"), reformule pour chercher des alternatives distinctes de celles mentionnées précédemment dans la conversation.
- Conserve les critères clés (prix, data, validité) si la question continue la recherche précédente.
- Retourne UNIQUEMENT la question reformulée, sans salutations, explications ou ponctuation superflue.
"""

def reecrire_question_historique(question: str, history: list, groq_client) -> str:
    if not history:
        return question

    # Récupérer les 4 derniers messages (historique récent)
    history_str = ""
    for msg in history[-4:]:
        role = "Utilisateur" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    prompt = f"Historique de la conversation :\n{history_str}\nDernière question de l'utilisateur : {question}\n\nQuestion autonome reformulée :"

    try:
        t0 = time.time()
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": REWRITER_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.1,
        )
        reformulated = response.choices[0].message.content.strip()
        print(f"⏱️  Reformulation de la question : {time.time() - t0:.3f}s | '{question}' ➔ '{reformulated}'")
        return reformulated
    except Exception as e:
        print(f"⚠️  Échec de la reformulation : {e}")
        return question


# ════════════════════════════════════════════════════════════════════
#  RAG QUERY — HYBRID SEARCH
# ════════════════════════════════════════════════════════════════════

def rag_query(question: str, session_id: str, lang: str,
              db: Session, request: Request) -> tuple[str, str]:

    collection  = request.app.state.faiss_index
    groq_client = request.app.state.groq_client
    reranker    = request.app.state.reranker
    embedder    = request.app.state.embedder

    # ── Étape 1 : Détection confirmation ──
    context = ""
    if est_confirmation(question):
        history_msgs = get_history(session_id, db)
        for msg in reversed(history_msgs):
            if msg["role"] == "assistant" and len(msg["content"]) > 100:
                context = msg["content"]
                print("🔁 Confirmation détectée — contexte réutilisé")
                break

    # ── Étape 2 : Enrichissement question courte ──
    if len(question.split()) < 5 and not est_confirmation(question):
        history_msgs = get_history(session_id, db)
        question_enrichie = reecrire_question_historique(question, history_msgs, groq_client)
    else:
        question_enrichie = question

    # ── Étape 3 : Extraction contraintes ──
    contraintes = {}
    if not context:
        contraintes = extraire_contraintes_llm(question_enrichie, groq_client, lang)

    # ── Étape 4 : SQL search (précision numérique exacte) ──
    sql_docs = []
    if not context and contraintes:
        sql_docs = sql_search(contraintes, db, limit=6)
        if not sql_docs and contraintes.get("exclure_streaming"):
            contraintes_souples = {k: v for k, v in contraintes.items()
                                    if k != "exclure_streaming"}
            sql_docs = sql_search(contraintes_souples, db, limit=6)

    # ── Étape 5 : ChromaDB vector search pur (sans filtre) ──
    # Retourne les contenus originaux complets via les métadonnées
    chroma_docs = []
    if not context:
        try:
            t0 = time.time()
            results = collection.query(
                query_texts=[question_enrichie],
                n_results  = 40,   # plus large car on a plusieurs chunks par offre
                include    = ["documents", "distances", "metadatas"]
            )
            print(f"⏱️  ChromaDB : {time.time() - t0:.4f}s "
                  f"— {len(results['documents'][0])} chunks")

            # ── Dédupliquer par source_id : garder le meilleur chunk par offre ──
            # et retourner le contenu ORIGINAL (pas le chunk résumé)
            vus          = {}   # source_id → (distance, original_content)
            chunks_bruts = results["documents"][0]
            distances    = results["distances"][0]
            metadatas    = results["metadatas"][0]

            for chunk, dist, meta in zip(chunks_bruts, distances, metadatas):
                meta = meta or {}
                source_id = meta.get("source_id", "")
                
                # Fetch original from metadata, fallback to DB if missing
                original = meta.get("original")
                if not original:
                    original = get_original_content_by_source_id(source_id, db)
                if not original:
                    original = chunk

                if source_id not in vus or dist < vus[source_id][0]:
                    vus[source_id] = (dist, original)

            chroma_docs = [content for _, content in vus.values()]
            print(f"🔍 ChromaDB après dédup source : {len(chroma_docs)} offres uniques")

        except Exception as e:
            print(f"⚠️  ChromaDB échoué : {e}")
            chroma_docs = []

    # ── Étape 6 : Fusion SQL (prioritaire) + ChromaDB ──
    filtered = []
    if not context:
        # SQL en premier (exact), ChromaDB en complément (sémantique)
        sql_set  = set(sql_docs)
        combined = list(sql_docs)
        for doc in chroma_docs:
            if doc not in sql_set:
                combined.append(doc)

        print(f"🔀 Fusion : {len(sql_docs)} SQL + {len(chroma_docs)} ChromaDB "
              f"→ {len(combined)} uniques")

        if combined:
            paires      = [[question, doc] for doc in combined]
            raw_scores  = reranker.predict(paires)
            # Normalisation Sigmoïde
            scores      = 1 / (1 + np.exp(-np.array(raw_scores)))
            
            docs_scores = []
            for doc, score in zip(combined, scores):
                is_sql = doc in sql_set
                # Boost SQL
                final_score = min(1.0, score + 0.15) if is_sql else score
                docs_scores.append({
                    "doc": doc,
                    "score": final_score,
                    "is_sql": is_sql,
                    "original_score": score
                })
            
            # Trier par score ajusté
            docs_scores = sorted(docs_scores, key=lambda x: x["score"], reverse=True)
            
            # Seuils distincts : les documents SQL sont toujours inclus, les sémantiques doivent passer le seuil de 0.70
            top_n = min(6, len(docs_scores))
            filtered = []
            for item in docs_scores[:top_n]:
                if item["is_sql"]:
                    # Garder impérativement les résultats SQL exacts pour éviter de jeter des correspondances mathématiques strictes
                    filtered.append(item["doc"])
                else:
                    # Recherche sémantique pure soumise au seuil strict
                    if item["score"] >= 0.70:
                        filtered.append(item["doc"])
            
            print(f"🎯 Reranker avec seuils distincts (SQL: inclus, Sem: 0.70) | top scores : {[round(float(item['score']), 2) for item in docs_scores[:top_n]]}")

            if not filtered:
                # Fallback : top 2 forcés (priorise SQL si présent)
                filtered = [item["doc"] for item in docs_scores[:2]]
                print("⚠️  Reranker fallback — top 2 forcés")

        # Déduplication sémantique finale
        filtered = dedupliquer_contexte(filtered, embedder, seuil=0.88)

    if not context:
        if filtered:
            context_parts = []
            current_len = 0
            # Contexte max de 12000 caractères au lieu de 3000
            max_context_len = 12000
            for doc in filtered:
                doc_clean = nettoyer_contexte(doc)
                if current_len + len(doc_clean) + 2 <= max_context_len:
                    context_parts.append(doc_clean)
                    current_len += len(doc_clean) + 2
                else:
                    # Ne pas couper au milieu d'un document, s'arrêter
                    break
            context = "\n\n".join(context_parts)
        else:
            context = "Aucune offre trouvée"

    # ── Étape 6 : LLM principal ──
    prompt_row = db.query(Prompt).filter_by(name="system_prompt").first()
    prompt_tpl = prompt_row.content if prompt_row else "You are Izzy.\n\n{context}"

    print(f"📋 CONTEXTE INJECTÉ :\n{context}\n{'='*40}")

    system_prompt = prompt_tpl.format(
        language_name=LANGUAGE_NAMES.get(lang, "French"),
        context=context
    )

    history   = get_history(session_id, db)
    lang_name = LANGUAGE_NAMES.get(lang, "French")
    messages  = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({
        "role": "system",
        "content": (
            f"⚠️ MANDATORY: The user's next message is in {lang_name}. "
            f"Your response MUST be entirely in {lang_name}.\n"
            f"⚠️ CRITICAL: ONLY use facts/offers from the provided context. If the context does not contain any offers matching the user's specific request (e.g. price range, criteria), you MUST state clearly that you do not have this information, rather than inventing or extrapolating offers. Never invent offers like Confort 6000 or Confort 9000 if they are not in the context."
        )
    })
    messages.append({"role": "user", "content": question})

    response = groq_client.chat.completions.create(
        model      = "llama-3.3-70b-versatile",
        messages   = messages,
        max_tokens = MAX_TOKENS,
        temperature= 0.1,
    )

    return response.choices[0].message.content.strip(), context


# ════════════════════════════════════════════════════════════════════
#  SYNTHÈSE VOCALE
# ════════════════════════════════════════════════════════════════════

async def speak_with_meta(text: str, lang: str) -> tuple:
    try:
        filename = f"{uuid.uuid4().hex}.mp3"
        path     = os.path.join(AUDIO_FOLDER, filename)
        voice    = EDGE_VOICES.get(lang, "fr-FR-DeniseNeural")
        tts      = edge_tts.Communicate(text, voice)
        metadata = []
        chunks   = []

        async for chunk in tts.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                metadata.append({
                    "text":  chunk["text"],
                    "start": round(chunk["offset"] / 10_000_000, 3),
                    "end":   round((chunk["offset"] + chunk["duration"]) / 10_000_000, 3)
                })

        with open(path, "wb") as f:
            for c in chunks:
                f.write(c)

        return filename, metadata

    except Exception as e:
        print(f"⚠️ Edge TTS échoué ({lang}): {e}")
        return None, []


# ════════════════════════════════════════════════════════════════════
#  ROUTES — UTILISATEUR
# ════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Backend IZZY actif."}


@app.post("/ask")
async def ask(body: QuestionInput, request: Request, db: Session = Depends(get_db)):
    question   = body.question.strip()
    session_id = body.session_id

    if not question:
        raise HTTPException(status_code=400, detail="Question vide")

    lang_question      = detect_lang(question)
    answer, context    = rag_query(question, session_id, lang_question, db, request)
    lang_voice         = detect_lang_response(answer, lang_question)
    filename, metadata = await speak_with_meta(answer, lang_voice)
    audio_url          = f"/static/audio/{filename}" if filename else None

    save_message(session_id, "user",      question, lang_question, db)
    save_message(session_id, "assistant", answer,   lang_voice,    db)

    for f in os.listdir(AUDIO_FOLDER):
        fpath = os.path.join(AUDIO_FOLDER, f)
        if os.path.getmtime(fpath) < time.time() - 120:
            try:    os.remove(fpath)
            except: pass

    return {
        "answer":      answer,
        "audio_url":   audio_url,
        "lang":        lang_voice,
        "metadata":    metadata,
        "history_len": count_exchanges(session_id, db),
        "context":     context
    }


@app.post("/reset")
async def reset(body: dict, db: Session = Depends(get_db)):
    session_id = body.get("session_id", "")
    if session_id:
        db.query(Conversation).filter_by(session_id=session_id).delete()
        db.commit()
    return {"status": "ok"}


# ════════════════════════════════════════════════════════════════════
#  ROUTES — ADMIN
# ════════════════════════════════════════════════════════════════════

# Tables gérées depuis la page Admin
ADMIN_MODELS = {
    "offers": Offer,
    "faq": FAQ,
    "services": Service,
}

ADMIN_LABELS = {
    "offers": "Offres",
    "faq": "FAQ",
    "services": "Services",
}


def _get_admin_model(table: str):
    Model = ADMIN_MODELS.get(table)
    if not Model:
        raise HTTPException(status_code=400, detail="Type invalide")
    return Model


@app.get("/admin/data")
async def admin_data(db: Session = Depends(get_db)):
    items = []
    stats_by_type = {}

    for table, Model in ADMIN_MODELS.items():
        rows = db.query(Model).order_by(Model.category, Model.id).all()
        active_count = db.query(Model).filter_by(is_active=True).count()

        stats_by_type[table] = {
            "label": ADMIN_LABELS.get(table, table),
            "total": len(rows),
            "active": active_count,
            "inactive": len(rows) - active_count,
        }

        for row in rows:
            items.append({
                "id": row.id,
                "table": table,
                "type": table,
                "type_label": ADMIN_LABELS.get(table, table),
                "content": row.content,
                "category": row.category,
                "is_active": row.is_active,
                "needs_reindex": row.needs_reindex,
            })

    prompt = db.query(Prompt).filter_by(name="system_prompt").first()

    return {
        "items": items,
        "prompt": prompt.content if prompt else "",
        "stats": {
            "total_items": len(items),
            "active_items": sum(1 for item in items if item["is_active"]),
            "inactive_items": sum(1 for item in items if not item["is_active"]),
            "conversations": db.query(Conversation).count(),
            "by_type": stats_by_type,
        },
    }


@app.post("/admin/items/{table}")
async def admin_add_item(
    table: str,
    body: OfferInput,
    request: Request,
    db: Session = Depends(get_db)
):
    Model = _get_admin_model(table)

    item = Model(
        content=body.content.strip(),
        category=body.category or table,
        is_active=True,
        needs_reindex=True,
    )

    db.add(item)
    db.commit()
    _refresh_index(request)

    return {"status": "ok", "id": item.id, "table": table}


@app.put("/admin/items/{table}/{item_id}")
async def admin_update_item(
    table: str,
    item_id: int,
    body: OfferUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    Model = _get_admin_model(table)
    item = db.query(Model).filter_by(id=item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Élément introuvable")

    if body.content is not None:
        item.content = body.content.strip()

    if body.category is not None:
        item.category = body.category.strip() or table

    if body.is_active is not None:
        item.is_active = body.is_active

    item.needs_reindex = True

    db.commit()
    _refresh_index(request)

    return {"status": "ok"}


@app.delete("/admin/items/{table}/{item_id}")
async def admin_delete_item(
    table: str,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    Model = _get_admin_model(table)
    item = db.query(Model).filter_by(id=item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Élément introuvable")

    db.delete(item)
    db.commit()
    _refresh_index(request)

    return {"status": "ok"}


# Compatibilité avec ton ancien Admin.jsx : les anciennes routes offres restent valides
@app.post("/admin/offers")
async def admin_add_offer(body: OfferInput, request: Request, db: Session = Depends(get_db)):
    return await admin_add_item("offers", body, request, db)


@app.put("/admin/offers/{offer_id}")
async def admin_update_offer(
    offer_id: int,
    body: OfferUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    return await admin_update_item("offers", offer_id, body, request, db)


@app.delete("/admin/offers/{offer_id}")
async def admin_delete_offer(
    offer_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    return await admin_delete_item("offers", offer_id, request, db)


@app.put("/admin/prompt")
async def admin_update_prompt(body: PromptUpdate, db: Session = Depends(get_db)):
    prompt = db.query(Prompt).filter_by(name="system_prompt").first()

    if not prompt:
        prompt = Prompt(
            name="system_prompt",
            content=body.content,
            description="Prompt principal d'Izzy"
        )
        db.add(prompt)
    else:
        prompt.content = body.content

    db.commit()
    return {"status": "ok"}


@app.get("/admin/stats")
async def admin_stats(db: Session = Depends(get_db)):
    return {
        "total_items": (
            db.query(Offer).count()
            + db.query(FAQ).count()
            + db.query(Service).count()
        ),
        "active_items": (
            db.query(Offer).filter_by(is_active=True).count()
            + db.query(FAQ).filter_by(is_active=True).count()
            + db.query(Service).filter_by(is_active=True).count()
        ),
        "offers": db.query(Offer).count(),
        "faq": db.query(FAQ).count(),
        "services": db.query(Service).count(),
        "conversations": db.query(Conversation).count(),
    }


def _refresh_index(request: Request):
    new_index, new_docs = rebuild_index(
        request.app.state.embedder,
        request.app.state.groq_client
    )
    if new_index is not None:
        request.app.state.faiss_index = new_index
        request.app.state.documents = new_docs
        print(f"🔄 Index ChromaDB mis à jour — {len(new_docs)} documents")


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model": "whisper-large-v3", "response_format": "verbose_json"}
        )

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Erreur Whisper")

    result = response.json()
    text   = result.get("text", "").strip()
    lang_w = result.get("language", "fr")

    lang_map = {"french": "fr", "arabic": "ar", "english": "en"}
    lang     = lang_map.get(lang_w.lower(), "fr")

    print(f"✅ Whisper : '{text}' | langue: {lang_w} → {lang}")
    return {"text": text, "lang": lang}


@app.post("/ask-text")
async def ask_text(body: QuestionInput, request: Request,
                   db: Session = Depends(get_db)):
    question      = body.question.strip()
    lang_question = detect_lang(question)
    answer, context = rag_query(question, body.session_id,
                                lang_question, db, request)
    lang_voice = detect_lang_response(answer, lang_question)
    return {
        "answer":  answer,
        "lang":    lang_voice,
        "context": context
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)