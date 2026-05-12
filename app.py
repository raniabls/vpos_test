import os
import uuid
import time
from contextlib import asynccontextmanager

import faiss
import edge_tts
import httpx

# ✅ Charger les variables .env AVANT tout import qui utilise os.getenv
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from groq import Groq

#from langdetect import detect
import re
from lingua import Language, LanguageDetectorBuilder

from database import get_db, init_db, Offer, Prompt, Conversation
from embeddings import get_embedder, load_or_build_index, rebuild_index


# ════════════════════════════════════════════════════════════════════
#  CONFIGURATION — Lue depuis .env
# ════════════════════════════════════════════════════════════════════

# ✅ Les secrets viennent du fichier .env, pas du code
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY manquant dans le fichier .env")

AUDIO_FOLDER    = "static/audio/"
FAISS_K         = 10 # jai diminuer
DISTANCE_THRESH = 0.6 # il etais 0,5 jai changer
MAX_TOKENS      = 500
MAX_HISTORY     = 20

os.makedirs(AUDIO_FOLDER, exist_ok=True)

EDGE_VOICES = {
    "fr": "fr-FR-DeniseNeural",
    "ar": "ar-DZ-AminaNeural",
    #"ar": "ar-SA-ZariyahNeural",
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


# ════════════════════════════════════════════════════════════════════
#  LIFESPAN — Démarrage et arrêt de FastAPI
# ════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("   IZZY — Démarrage FastAPI + PostgreSQL")
    print("=" * 60)

    # Initialiser PostgreSQL (crée les tables + prompt par défaut)
    # Lève une exception si PostgreSQL n'est pas démarré
    init_db()

    # Charger le modèle SentenceTransformer
    app.state.embedder = get_embedder()

    # Charger ou construire l'index FAISS
    app.state.faiss_index, app.state.documents = load_or_build_index(
        app.state.embedder
    )

    # Initialiser le client Groq
    app.state.groq_client = Groq(api_key=GROQ_API_KEY)

    print("✅ Izzy est prête !\n")
    yield
    print("👋 Izzy s'arrête...")


# ════════════════════════════════════════════════════════════════════
#  INITIALISATION FASTAPI
# ════════════════════════════════════════════════════════════════════

app = FastAPI(
    title    = "IZZY — Agent IA Djezzy",
    version  = "3.0.0",
    lifespan = lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════
#  MODÈLES PYDANTIC — Validation automatique
# ════════════════════════════════════════════════════════════════════
# il vérifie les données qui entrent dans ta route avant même que la fonction s'exécute.
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

# ── Initialiser lingua une seule fois au démarrage (pas à chaque appel)
_lingua_detector = LanguageDetectorBuilder.from_languages(
    Language.FRENCH, Language.ARABIC, Language.ENGLISH
).build()


def _has_keyword(text: str, kw: str) -> bool:
    # Vérifie les mots entiers pour éviter les faux positifs
    return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

def detect_lang(text: str) -> str:
    text_lower = text.lower().strip()

    # ── Couche 1 : score de mots-clés (plus de biais d'ordre)
    scores = {"fr": 0, "ar": 0, "en": 0}
    for lang, keywords in LANG_KEYWORDS.items():
        for kw in keywords:
            if _has_keyword(text_lower, kw):
                scores[lang] += 1

    best_lang  = max(scores, key=scores.get)
    best_score = scores[best_lang]
    if best_score > 0:
        return best_lang

    # ── Couche 2 : caractères Unicode arabes
    if sum(1 for c in text if '\u0600' <= c <= '\u06FF') > 0:
        return "ar"

    # ── Couche 3 : lingua (seulement si texte suffisamment long)
    if len(text_lower) >= 10:
        try:
            result = _lingua_detector.detect_language_of(text)
            if result == Language.ARABIC:  return "ar"
            if result == Language.FRENCH:  return "fr"
            if result == Language.ENGLISH: return "en"
        except Exception:
            pass

    # ── Fallback
    return "fr"

def detect_lang_response(answer: str, lang_question: str) -> str:
    
    # ── Couche 1 : caractères Unicode arabes (priorité absolue)
    arabic_chars = sum(1 for c in answer if '\u0600' <= c <= '\u06FF')
    if arabic_chars > 2:
        return "ar"

    # ── Couche 2 : lingua (si texte suffisamment long)
    if len(answer.strip()) >= 20:
        try:
            result = _lingua_detector.detect_language_of(answer)
            if result == Language.ARABIC:  return "ar"
            if result == Language.FRENCH:  return "fr"
            if result == Language.ENGLISH: return "en"
        except Exception:
            pass

    # ── Fallback : on fait confiance à la langue de la question
    return lang_question

# ════════════════════════════════════════════════════════════════════
#  GESTION HISTORIQUE (PostgreSQL)
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
#  MOTEUR RAG
# ════════════════════════════════════════════════════════════════════

def rag_query(question: str, session_id: str, lang: str,
              db: Session, request: Request) -> str:

    embedder    = request.app.state.embedder
    faiss_index = request.app.state.faiss_index
    documents   = request.app.state.documents
    groq_client = request.app.state.groq_client

    # Recherche vectorielle FAISS
    question_embedding = embedder.encode([question], convert_to_numpy=True)
    faiss.normalize_L2(question_embedding)
    start = time.time()
    D, I = faiss_index.search(question_embedding, k=min(FAISS_K, len(documents)))
    end = time.time()
    print(f"⏱️ Temps recherche FAISS: {end - start:.4f} secondes")

    seen, filtered = set(), []
    for j in range(len(I[0])):
        if D[0][j] > DISTANCE_THRESH:
            doc = documents[I[0][j]]
            key = doc[:70].strip()
            if key not in seen:
                seen.add(key)
                filtered.append(doc)

    # si FAISS trouve des documents pertinents ou non. 
    # Un score proche de 1.0 = très pertinent, proche de 0.0 = rien trouvé de bon.
    print(f"🔍 FAISS — meilleur score: {D[0][0]:.3f} | docs trouvés: {len(filtered)}")

    context = "\n".join(filtered) if filtered else "\n".join([documents[i] for i in I[0]])
    context = context[:3000]
    last_dot = context.rfind(".")   # trouve le dernier point
    if last_dot > 2000:             # seulement si on a assez de contenu
     context = context[:last_dot + 1]

    # Récupérer le prompt depuis PostgreSQL
    prompt_row = db.query(Prompt).filter_by(name="system_prompt").first()
    prompt_tpl = prompt_row.content if prompt_row else "You are Izzy.\n\n{context}"

    system_prompt = prompt_tpl.format(
        language_name = LANGUAGE_NAMES.get(lang, "French"),
        context       = context
    )

    history  = get_history(session_id, db)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    # POUR Injecter un rappel fort de langue juste avant la question
    lang_name = LANGUAGE_NAMES.get(lang, "French")
    messages.append({
     "role": "system", 
     "content": f"⚠️ MANDATORY: The user's next message is in {lang_name}. Your response MUST be entirely in {lang_name}. This overrides all conversation history."
    })
    messages.append({"role": "user", "content": question})

    response = groq_client.chat.completions.create(
        model      = "llama-3.3-70b-versatile",
        messages   = messages,
        max_tokens = MAX_TOKENS,
        # extra_body = {"reasoning_effort": "none"}
    )

    return response.choices[0].message.content.strip(), context

#  SYNTHÈSE VOCALE
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
        # Edge TTS down → on log l'erreur et on retourne None
        # L'app continue, l'utilisateur voit la réponse texte sans audio
        print(f"⚠️ Edge TTS échoué ({lang}): {e}")
        return None, []

# ════════════════════════════════════════════════════════════════════
#  ROUTES — INTERFACE UTILISATEUR
# ════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Backend IZZY actif. Lancez le frontend React sur http://127.0.0.1:5173"}


@app.post("/ask")
async def ask(
    body:    QuestionInput,
    request: Request,
    db:      Session = Depends(get_db)
):
    question   = body.question.strip()
    session_id = body.session_id

    if not question:
        raise HTTPException(status_code=400, detail="Question vide")

    lang_question          = detect_lang(question)
    answer, context                 = rag_query(question, session_id, lang_question, db, request)
    lang_voice             = detect_lang_response(answer, lang_question)
    filename, metadata     = await speak_with_meta(answer, lang_voice)
    audio_url = f"/static/audio/{filename}" if filename else None

    save_message(session_id, "user",      question, lang_question, db)
    save_message(session_id, "assistant", answer,   lang_voice,    db)

    # Nettoyer anciens fichiers audio
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
        "context" : context
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

@app.get("/admin/data")
async def admin_data(db: Session = Depends(get_db)):
    offers = db.query(Offer).order_by(Offer.category, Offer.id).all()
    prompt = db.query(Prompt).filter_by(name="system_prompt").first()
    stats = {
        "total_offers": db.query(Offer).count(),
        "active_offers": db.query(Offer).filter_by(is_active=True).count(),
        "conversations": db.query(Conversation).count(),
    }
    return {
        "offers": [
            {
                "id": o.id,
                "content": o.content,
                "category": o.category,
                "is_active": o.is_active,
                "needs_reindex": o.needs_reindex,
            }
            for o in offers
        ],
        "prompt": prompt.content if prompt else "",
        "stats": stats,
    }


@app.post("/admin/offers")
async def admin_add_offer(body: OfferInput, request: Request, db: Session = Depends(get_db)):
    db.add(Offer(content=body.content.strip(), category=body.category,
                 is_active=True, needs_reindex=True))
    db.commit()
    _refresh_index(request)
    return {"status": "ok"}


@app.put("/admin/offers/{offer_id}")
async def admin_update_offer(offer_id: int, body: OfferUpdate,
                              request: Request, db: Session = Depends(get_db)):
    offer = db.query(Offer).filter_by(id=offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    if body.content   is not None: offer.content   = body.content.strip()
    if body.category  is not None: offer.category  = body.category
    if body.is_active is not None: offer.is_active = body.is_active
    offer.needs_reindex = True
    db.commit()
    _refresh_index(request)
    return {"status": "ok"}


@app.delete("/admin/offers/{offer_id}")
async def admin_delete_offer(offer_id: int, request: Request, db: Session = Depends(get_db)):
    offer = db.query(Offer).filter_by(id=offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    db.delete(offer); db.commit()
    _refresh_index(request)
    return {"status": "ok"}


@app.put("/admin/prompt")
async def admin_update_prompt(body: PromptUpdate, db: Session = Depends(get_db)):
    prompt = db.query(Prompt).filter_by(name="system_prompt").first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt introuvable")
    prompt.content = body.content
    db.commit()
    return {"status": "ok"}


@app.get("/admin/stats")
async def admin_stats(db: Session = Depends(get_db)):
    return {
        "total_offers":  db.query(Offer).count(),
        "active_offers": db.query(Offer).filter_by(is_active=True).count(),
        "conversations": db.query(Conversation).count(),
    }


def _refresh_index(request: Request):
    new_index, new_docs = rebuild_index(request.app.state.embedder)
    if new_index is not None:
        request.app.state.faiss_index = new_index
        request.app.state.documents   = new_docs
        print(f"🔄 Index FAISS mis à jour — {len(new_docs)} offres")
        

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Reçoit l'audio du navigateur → Groq Whisper → texte transcrit.
    """
    audio_bytes = await audio.read()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={
                "model": "whisper-large-v3",
                "response_format": "verbose_json"
            }
        )

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Erreur Whisper")

    result  = response.json()
    text    = result.get("text", "").strip()
    lang_w  = result.get("language", "fr")  # langue détectée par Whisper

    # Convertir le code langue Whisper vers ton format (fr/ar/en)
    lang_map = {
        "french":  "fr",
        "arabic":  "ar",
        "english": "en"
    }
    lang = lang_map.get(lang_w.lower(), "fr")

    print(f"✅ Whisper : '{text}' | langue: {lang_w} → {lang}")

    return {"text": text, "lang": lang}

#nouvelle route pour l'évaluation
@app.post("/ask-text")
async def ask_text(
    body: QuestionInput,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        question = body.question.strip()

        if not question:
            raise HTTPException(status_code=400, detail="Question vide")

        # Détection langue
        lang_question = detect_lang(question)

        # RAG
        answer, context = rag_query(
            question,
            body.session_id,
            lang_question,
            db,
            request
        )

        return {
            "answer": answer,
            "context": context,
            "lang": lang_question
        }

    except Exception as e:
        print(f"❌ /ask-text ERROR: {e}")

        return {
            "answer": "",
            "context": "",
            "lang": "fr",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
