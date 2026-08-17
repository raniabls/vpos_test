"""
evaluate.py — Évaluation automatique d'Izzy (RAG + LLM)
"""

import os
import json
import time
import argparse
import requests
import re
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer
#import matplotlib.pyplot as plt

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
groq_client  = Groq(api_key=GROQ_API_KEY)
embedder     = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# ══════════════════════════════════════════════
#  UTILITAIRE DE PARSING JSON LLM
# ══════════════════════════════════════════════

def extraire_json_clean(text: str) -> str:
    """
    Extrait la chaîne JSON proprement depuis le texte retourné par le LLM.
    Gère les blocs de code markdown ```json ... ``` ou extrait simplement
    le contenu entre la première accolade '{' et la dernière accolade '}'.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1].strip()
    return text


# ══════════════════════════════════════════════
#  APPEL GROQ AVEC GESTION RATE LIMIT TOKENS
# ══════════════════════════════════════════════

def appel_groq(messages: list, max_tokens: int = 250, retries: int = 3) -> str:
    """
    Appel Groq avec gestion automatique des erreurs de tokens (rate limit).
    Si l'erreur contient 'tokens' ou 'rate_limit', on attend et on réessaie.
    Retourne le texte de la réponse ou "" en cas d'échec.
    """
    for attempt in range(retries):
        try:
            r = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens
            )
            return r.choices[0].message.content.strip()

        except Exception as e:
            err = str(e).lower()

            # Détection erreur de tokens / rate limit
            if any(kw in err for kw in ["tokens", "rate_limit", "rate limit",
                                         "429", "too many", "exceeded"]):
                attente = 60 if attempt == 0 else 120
                print(f"    ⏳ Rate limit tokens — attente {attente}s "
                      f"(tentative {attempt+1}/{retries})...")
                time.sleep(attente)
                continue

            # Autre erreur — on attend moins longtemps
            print(f"    ⚠️  Groq erreur tentative {attempt+1}: {e}")
            if attempt < retries - 1:
                time.sleep(5)

    print("    ❌ Groq — échec après toutes les tentatives, on continue")
    return ""


# ══════════════════════════════════════════════
#  CHARGEMENT DU DATASET
# ══════════════════════════════════════════════

def charger_dataset(csv_path: str) -> list[dict]:
    try:
        df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines='skip')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="latin-1", on_bad_lines='skip')
        print(f"⚠️  Encodage latin-1 détecté pour {csv_path}")

    colonnes_requises = ["question", "reponse_attendue", "mots_cles_attendus", "langue"]
    manquantes = [c for c in colonnes_requises if c not in df.columns]
    if manquantes:
        raise ValueError(f"Colonnes manquantes : {manquantes}")

    dataset = []
    for _, row in df.iterrows():
        question = str(row["question"]).strip()
        if not question or question == "nan":
            continue

        mots_cles_raw = str(row.get("mots_cles_attendus", ""))
        mots_cles = [
            m.strip() for m in mots_cles_raw.split(",")
            if m.strip() and m.strip() != "nan"
        ]

        hors_sujet_raw = str(row.get("hors_sujet", "False")).strip().lower()
        hors_sujet = hors_sujet_raw in ["true", "1", "oui", "yes"]

        dataset.append({
            "question"          : question,
            "reponse_attendue"  : str(row["reponse_attendue"]).strip(),
            "mots_cles_attendus": mots_cles,
            "langue"            : str(row.get("langue", "fr")).strip(),
            "hors_sujet"        : hors_sujet
        })

    nb_hors_sujet = sum(1 for d in dataset if d["hors_sujet"])
    print(f"✅ Dataset chargé : {len(dataset)} questions "
          f"({nb_hors_sujet} hors sujet) depuis '{csv_path}'")
    return dataset


# ══════════════════════════════════════════════
#  MÉTRIQUE 1 — FAITHFULNESS
# ══════════════════════════════════════════════

def nettoyer_boilerplate_reponse(reponse: str) -> str:
    # On remplace par vide toutes les phrases ou segments typiques d'activation/contact
    # Français
    reponse = re.sub(r"(?i)(?:pour activer|pour plus de détails|pour souscrire|pour obtenir|si vous souhaitez|n'hésitez pas|vous pouvez|il suffit de|veuillez)\s+[^.!?]*(?:700|l'application djezzy|l’application djezzy|l'app djezzy|l’app djezzy)[^.!?]*[.!?]?", "", reponse)
    reponse = re.sub(r"(?i)(?:contactez|contacter|composez|composer|utilisez|utiliser)\s+[^.!?]*(?:700|l'application djezzy|l’application djezzy|l'app djezzy|l’app djezzy)[^.!?]*[.!?]?", "", reponse)
    # Anglais
    reponse = re.sub(r"(?i)(?:to activate|for more details|to subscribe|please|you can)\s+[^.!?]*(?:700|djezzy app)[^.!?]*[.!?]?", "", reponse)
    reponse = re.sub(r"(?i)(?:contact|dial|use)\s+[^.!?]*(?:700|djezzy app)[^.!?]*[.!?]?", "", reponse)
    # Arabe
    reponse = re.sub(r"(?i)(?:لتفعيل|للاشتراك|للحصول|يمكنك|يرجى)\s+[^.!?]*(?:700|تطبيق دجيزي|تطبيق جيزي)[^.!?]*[.!?]?", "", reponse)
    reponse = re.sub(r"(?i)(?:الاتصال|استخدام|طلب)\s+[^.!?]*(?:700|تطبيق دجيزي|تطبيق جيزي)[^.!?]*[.!?]?", "", reponse)
    
    phrases = [
        # Français
        r"pour activer cette offre,?\s*(?:vous pouvez)?\s*(?:contactez|contacter)\s*le\s*700\s*ou\s*(?:utilisez|utiliser)\s*(?:l'application|l’application)\s*djezzy",
        r"pour activer ces offres,?\s*(?:vous pouvez)?\s*(?:utilisez|utiliser)\s*(?:l'application|l’application)\s*djezzy\s*ou\s*(?:contactez|contacter)\s*(?:le\s*)?700",
        r"pour activer l'une de ces offres,?\s*(?:vous pouvez)?\s*(?:contactez|contacter)\s*le\s*700\s*ou\s*(?:utilisez|utiliser)\s*(?:l'application|l’application)\s*djezzy",
        r"pour obtenir des informations sur d'autres offres,?\s*je vous invite à contacter le 700 ou à utiliser l'application djezzy",
        r"pour plus de détails ou pour activer cette offre,?\s*(?:vous pouvez)?\s*(?:contactez|contacter)\s*le\s*700\s*ou\s*(?:utilisez|utiliser)\s*(?:l'application|l’application)\s*djezzy",
        r"il est donc recommandé de contacter directement le service client de djezzy pour obtenir de l'aide sur l'activation",
        r"vous pouvez contacter le 700 ou utiliser l'application djezzy",
        r"contactez le 700 ou utilisez l'application djezzy",
        
        # Anglais
        r"to activate this offer,?\s*(?:you can)?\s*contact\s*700\s*or\s*use\s*(?:the\s*)?djezzy\s*(?:app|application)",
        r"for more details,?\s*(?:you can)?\s*contact\s*djezzy\s*(?:customer service\s*)?at\s*700\s*or\s*use\s*(?:the\s*)?djezzy\s*(?:app|application)",
        r"to pay your djezzy bill online,?\s*you can use the e-paiement service",
        
        # Arabe
        r"لتفعيل هذه الخدمة،?\s*يمكنك الاتصال بالرقم 700 أو استخدام تطبيق جيزي",
        r"لتفعيل هذه الخدمة،?\s*يرجى الاتصال بالرقم 700 أو استخدام تطبيق جيزي",
        r"لتفعيل الخدمة،?\s*يرجى الاتصال بالرقم 700 أو استخدام تطبيق جيزي",
        r"لتفعيل هذه الخدمة،?\s*يمكنك الاتصال على 700 أو استخدام تطبيق جيزي",
        r"لتفعيل هذه الخدمة،?\s*يرجى الاتصال على 700 أو استخدام تطبيق دجيزي",
        r"عن طريق الاتصال على الرقم 700 أو من خلال تطبيق دجيزي",
        r"الاتصال بالرقم 700 أو استخدام تطبيق جيزي",
        r"الاتصال على الرقم 700 أو من خلال تطبيق دجيزي"
    ]
    
    clean_rep = reponse
    for pat in phrases:
        clean_rep = re.sub(pat, "", clean_rep, flags=re.IGNORECASE)
    
    # Supprimer les phrases vides ou trop courtes restantes du nettoyage
    clean_rep = clean_rep.strip()
    return clean_rep if len(clean_rep) > 5 else reponse


# ══════════════════════════════════════════════
#  MÉTRIQUE 1 — FAITHFULNESS
# ══════════════════════════════════════════════

def calculer_faithfulness(question: str, reponse: str,
                           contexte: str) -> tuple[float, str]:
    reponse_propre = nettoyer_boilerplate_reponse(reponse)

        # ── Détection langue de la réponse ──────────────────────────
    arabic_chars = sum(1 for c in reponse if '\u0600' <= c <= '\u06FF')
    est_arabe    = arabic_chars > len(reponse) * 0.2

    # ── Instruction cross-lingue si réponse arabe ────────────────
    note_crosslingue = ""
    if est_arabe:
        note_crosslingue = """
IMPORTANT — Correspondances cross-lingues à accepter :
- "دينار" / "دج" / "DA" / "DZD" → même unité monétaire ✓
- "جيجا" / "Go" / "GB"          → même unité de data ✓  
- "ميغا" / "Mo" / "MB"          → même unité ✓
- "شهر" / "mois" / "30 jours"   → même durée ✓
- "يوم" / "jour" / "24h"        → même durée ✓
- "أسبوع" / "semaine" / "7 jours" → même durée ✓
- "غير محدود" / "illimité"      → même sens ✓
Une valeur numérique identique exprimée dans une autre langue 
ou unité équivalente EST supportée par le contexte.
"""

    prompt = f"""Tu es un évaluateur strict de systèmes RAG pour un agent télécom algérien.

Question posée : "{question}"

Contexte fourni au système RAG :
{contexte[:1500]}

Réponse générée par le système :
{reponse_propre}

INSTRUCTIONS STRICTES :
1. Identifie CHAQUE affirmation factuelle : prix (dinars), volume (Go/Mo), durée (jours/mois), nom d'offre
2. Une affirmation est supportée UNIQUEMENT si elle apparaît EXPLICITEMENT dans le contexte
3. Si la réponse dit "je n'ai pas cette information" alors que le contexte contient l'info → score 0.0
4. Si la réponse invente des valeurs absentes du contexte → score 0.0 pour ces affirmations
5. Les chiffres doivent être EXACTS — "1500 DA" ≠ "1000 DA"
6. Si le contexte est vide ou "Aucune offre trouvée" → score 0.5 par défaut

Retourne UNIQUEMENT ce JSON sans texte avant ou après :
{{
  "affirmations_total": <int>,
  "affirmations_supportees": <int>,
  "score": <float 0.0-1.0>,
  "details": "<max 120 chars, cite les valeurs problématiques>"
}}"""

    text = appel_groq([{"role": "user", "content": prompt}], max_tokens=250)
    if not text:
        return 0.5, "erreur calcul"

    try:
        clean_text = extraire_json_clean(text)
        data  = json.loads(clean_text)
        score = float(data.get("score", 0.5))

        total     = data.get("affirmations_total", 0)
        supportes = data.get("affirmations_supportees", 0)
        if total > 0:
            score_calcule = supportes / total
            if abs(score - score_calcule) > 0.2:
                score = score_calcule

        return score, data.get("details", "")
    except Exception:
        return 0.5, "erreur parsing"


# ══════════════════════════════════════════════
#  MÉTRIQUE 2 — ANSWER RELEVANCY
# ══════════════════════════════════════════════
SCALE_PARAMS = {
    "fr": {"min_score": 0.22, "range": 0.38},
    "ar": {"min_score": 0.15, "range": 0.32},  # distribution plus basse
    "en": {"min_score": 0.24, "range": 0.36},
}

def calculer_answer_relevancy(question: str, reponse: str, langue: str = "fr") -> float:
    try:
        reponse_propre = nettoyer_boilerplate_reponse(reponse)
        vecs  = embedder.encode([question, reponse_propre], convert_to_numpy=True)
        vecs  = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        raw_score = float(np.dot(vecs[0], vecs[1]))
        params    = SCALE_PARAMS.get(langue, SCALE_PARAMS["fr"])
        # Ajustement linéaire pour ramener la similarité cosinus de paraphrase-MiniLM sur une échelle réaliste
        score     = (raw_score - params["min_score"]) / params["range"]
        return max(0.0, min(1.0, score))
    except Exception as e:
        print(f"    ⚠️  Relevancy error: {e}")
        return 0.0


# ══════════════════════════════════════════════
#  MÉTRIQUE 3 — CONTEXT PRECISION (LLM)
# ══════════════════════════════════════════════

"""def calculer_context_precision(contexte: str, mots_cles: list[str],
                                question: str) -> float:
    if not contexte or contexte == "Aucune offre trouvée":
        return 0.0
    if not mots_cles:
        return 0.0

    # Nettoyage et comparaison directe (100% locale pour économiser l'API et éviter les rate limits)
    contexte_lower = contexte.lower()
    trouves = 0
    for kw in mots_cles:
        kw_n = kw.lower().strip()
        # Normalisation simple pour les espaces autour de Go / Mo
        def normaliser(texte):
           texte = texte.lower()
           texte = re.sub(r"(\d+)\s*go", r"\1go", texte)
           texte = re.sub(r"(\d+)\s*mo", r"\1mo", texte)
           texte = re.sub(r"(\d+)\s*da", r"\1da", texte)  # ← ajouter
           texte = re.sub(r"(\d+)\s*din", r"\1din", texte)  # ← ajouter
           texte = re.sub(r"\s+", " ", texte)
           return texte
    
        kw_n = normaliser(kw_n)
        
        ctx_clean = normaliser(contexte_lower)
        
        if kw_n in ctx_clean:
            trouves += 1
            
    return trouves / len(mots_cles)"""
import re

def normaliser(texte: str) -> str:
    texte = texte.lower()
    texte = re.sub(r"(\d+)\s*go",  r"\1go",  texte)
    texte = re.sub(r"(\d+)\s*mo",  r"\1mo",  texte)
    texte = re.sub(r"(\d+)\s*da",  r"\1da",  texte)
    texte = re.sub(r"(\d+)\s*din", r"\1din", texte)
    texte = re.sub(r"\s+", " ",              texte)
    return texte


def keyword_match(kw: str, texte: str) -> bool:
    """
    Matching robuste avec 3 niveaux de vérification.
    """
    kw_n    = normaliser(kw)
    texte_n = normaliser(texte)

    # Niveau 1 — Keyword purement numérique ex: "1800"
    # → vérifier que ce n'est pas une sous-séquence d'un plus grand nombre
    if re.match(r'^\d+\w*$', kw_n):
        pattern = r'(?<!\d)' + re.escape(kw_n) + r'(?!\d)'
        return bool(re.search(pattern, texte_n))

    # Niveau 2 — Keyword alphanumérique ex: "30go", "tod"
    # → vérifier les frontières de mot
    if re.match(r'^[\w\d]+$', kw_n):
        pattern = r'(?<![a-zA-Z0-9\u0600-\u06FF])' \
                  + re.escape(kw_n) \
                  + r'(?![a-zA-Z0-9\u0600-\u06FF])'
        return bool(re.search(pattern, texte_n))

    # Niveau 3 — Keyword multi-mots ex: "1800 da", "30 jours"
    return kw_n in texte_n


def calculer_context_precision(contexte: str, mots_cles: list[str],
                                question: str) -> float:
    if not contexte or contexte == "Aucune offre trouvée":
        return 0.0
    if not mots_cles:
        return 0.0

    trouves = sum(1 for kw in mots_cles if keyword_match(kw, contexte))
    return trouves / len(mots_cles)


def calculer_context_recall(reponse: str, mots_cles: list[str],
                             question: str, reponse_attendue: str) -> float:
    if not reponse or not mots_cles:
        return 0.0

    trouves = sum(1 for kw in mots_cles if keyword_match(kw, reponse))
    return trouves / len(mots_cles)

# ══════════════════════════════════════════════
#  MÉTRIQUE 4 — CONTEXT RECALL (LLM)
# ══════════════════════════════════════════════

"""def calculer_context_recall(reponse: str, mots_cles: list[str],
                             question: str, reponse_attendue: str) -> float:
    if not reponse or not reponse_attendue:
        return 0.0
    if not mots_cles:
        return 0.0

    # Nettoyage et comparaison directe (100% locale pour économiser l'API et éviter les rate limits)
    reponse_lower = reponse.lower()
    trouves = 0
    for kw in mots_cles:
        kw_n = kw.lower().strip()
        # Normalisation simple pour les espaces autour de Go / Mo

        def normaliser(texte):
           texte = texte.lower()
           texte = re.sub(r"(\d+)\s*go", r"\1go", texte)
           texte = re.sub(r"(\d+)\s*mo", r"\1mo", texte)
           texte = re.sub(r"(\d+)\s*da", r"\1da", texte)  # ← ajouter
           texte = re.sub(r"(\d+)\s*din", r"\1din", texte)  # ← ajouter
           texte = re.sub(r"\s+", " ", texte)
           return texte
        
        kw_n = normaliser(kw_n)
        
        rep_clean = normaliser(reponse_lower)
        
        if kw_n in rep_clean:
            trouves += 1
            
    return trouves / len(mots_cles)"""

# ══════════════════════════════════════════════
#  MÉTRIQUE 5 — REFUS HORS SUJET (score simple)
# ══════════════════════════════════════════════

def evaluer_refus(reponse: str, est_hors_sujet: bool, question: str) -> float:
    """
    Retourne un score simple :
      - Question hors sujet + Izzy refuse   → 1.0 (correct)
      - Question hors sujet + Izzy répond   → 0.0 (erreur)
      - Question normale   + Izzy répond    → 1.0 (correct)
      - Question normale   + Izzy refuse    → 0.0 (erreur)
    """
    reponse_lower = reponse.lower()
    mots_refus = [
        "uniquement", "only", "فقط",
        "je ne réponds", "je ne peux pas répondre",
        "désolé, je", "sorry, i",
        "ne concerne pas", "hors de mes",
        "exclusivement djezzy", "pas dans mes",
        "لا أستطيع الإجابة", "خارج نطاق"
    ]
    a_refuse = any(w in reponse_lower for w in mots_refus)

    # Score binaire : 1.0 si le comportement est correct, 0.0 sinon
    if est_hors_sujet:
        return 1.0 if a_refuse else 0.0
    else:
        # Si c'est une question normale, elle ne doit pas avoir refusé ET produit une réponse très courte
        if a_refuse and len(reponse) < 100:
            return 0.0
        return 1.0


# ══════════════════════════════════════════════
#  MÉTRIQUE 6 — COHÉRENCE LANGUE
# ══════════════════════════════════════════════

def evaluer_coherence_langue(langue_attendue: str, langue_reponse: str) -> float:
    return 1.0 if langue_attendue == langue_reponse else 0.0


# ══════════════════════════════════════════════
#  APPEL À IZZY
# ══════════════════════════════════════════════

def interroger_izzy(question: str, api_url: str,
                    session_id: str, retries: int = 3) -> dict:
    for tentative in range(retries):
        try:
            debut = time.time()
            r = requests.post(
                f"{api_url}/ask-text",
                json={"question": question, "session_id": session_id},
                timeout=60
            )
            latence = time.time() - debut

            if r.status_code == 500:
                print(f"    ⏳ HTTP 500 — attente 15 sec (tentative {tentative+1}/{retries})...")
                time.sleep(15)
                continue

            if r.status_code == 429:
                print(f"    ⏳ Rate limit — attente 60 sec...")
                time.sleep(60)
                continue

            if r.status_code != 200:
                print(f"    ⚠️  HTTP {r.status_code} — on continue")
                return {}

            data = r.json()
            return {
                "reponse"        : data.get("answer", ""),
                "contexte"       : data.get("context", ""),
                "langue_reponse" : data.get("lang", "fr"),
                "latence"        : latence
            }
        except requests.exceptions.Timeout:
            print(f"    ⏳ Timeout — tentative {tentative+1}/{retries}")
            time.sleep(5)
        except Exception as e:
            print(f"    ⚠️  Erreur réseau : {e} — on continue")
            return {}

    print(f"    ⚠️  Izzy injoignable après {retries} tentatives — on continue")
    return {}


# ══════════════════════════════════════════════
#  ÉVALUATION COMPLÈTE
# ══════════════════════════════════════════════

def evaluer(api_url: str, output_path: str = None, dataset: list = None):

    tests = dataset if dataset is not None else []
    if not tests:
        print("❌ Aucun dataset fourni")
        return

    tests_normaux    = [t for t in tests if not t["hors_sujet"]]
    tests_hors_sujet = [t for t in tests if t["hors_sujet"]]

    print(f"\n{'='*65}")
    print(f"  ÉVALUATION IZZY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  API : {api_url}")
    print(f"  {len(tests)} questions "
          f"({len(tests_normaux)} normales, {len(tests_hors_sujet)} hors sujet)")
    print(f"{'='*65}\n")

    resultats        = []
    session_normale  = f"eval_normal_{int(time.time())}"
    session_hs       = f"eval_hs_{int(time.time())}"

    scores_faith     = []
    scores_relev     = []
    scores_prec      = []
    scores_recall    = []
    scores_coherence = []
    scores_refus     = []   # ← score simple 0.0 ou 1.0
    latences         = []
    langue_results   = {"fr": [], "ar": [], "en": []}

    for i, test in enumerate(tests):
        question   = test["question"]
        attendue   = test["reponse_attendue"]
        mots_cles  = test["mots_cles_attendus"]
        langue     = test["langue"]
        hors_sujet = test.get("hors_sujet", False)

        session_id = session_hs if hors_sujet else session_normale

        print(f"[{i+1:02d}/{len(tests)}] {'🚫' if hors_sujet else '💬'} {question[:55]}...")

        resultat = interroger_izzy(question, api_url, session_id)

        # ── Si Izzy est injoignable, on saute cette question et on continue ──
        if not resultat:
            print(f"  ⏭️  Question ignorée, on passe à la suivante")
            continue

        reponse        = resultat["reponse"]
        contexte       = resultat.get("contexte", "")
        latence        = resultat["latence"]
        langue_reponse = resultat.get("langue_reponse", "fr")

# ── Métriques ──────────────────────────────────────────────

        # --- Faithfulness ---
        if hors_sujet:
            faith_score  = None
            faith_detail = "hors sujet — non applicable"
        elif not contexte or contexte.strip() == "Aucune offre trouvée":
            if len(reponse.strip()) > 80:
                faith_score  = 0.2
                faith_detail = "contexte vide — réponse générée sans source"
            else:
                faith_score  = 0.5
                faith_detail = "contexte vide — réponse courte acceptable"
        else:
            faith_score, faith_detail = calculer_faithfulness(
                question, reponse, contexte
            )

        relev_score  = calculer_answer_relevancy(question, reponse, langue)
        prec_score   = calculer_context_precision(contexte, mots_cles, question)
        recall_score = calculer_context_recall(reponse, mots_cles, question, attendue)
        coh_score    = evaluer_coherence_langue(langue, langue_reponse)
        refus_score  = evaluer_refus(reponse, hors_sujet, question)

        # --- Accumulation des scores ---
        if not hors_sujet:
            scores_prec.append(prec_score)
            scores_recall.append(recall_score)

            if faith_score is not None:
                scores_faith.append(faith_score)

            if langue in langue_results:
                langue_results[langue].append({
                    "faithfulness"    : faith_score if faith_score is not None else 0.0,
                    "answer_relevancy": relev_score,
                    "context_recall"  : recall_score
                })

        scores_relev.append(relev_score)
        scores_coherence.append(coh_score)
        scores_refus.append(refus_score)
        latences.append(latence)

        # --- Affichage console ---
        coh_icon   = "✅" if coh_score == 1.0 else "❌"
        refus_icon = "✅" if refus_score == 1.0 else "❌"
        faith_str  = f"{faith_score:.2f}" if faith_score is not None else "N/A"
        print(f"  💬 {reponse[:80]}...")
        print(f"  📊 Faith={faith_str} | Relev={relev_score:.2f} | "
              f"Prec={prec_score:.2f} | Recall={recall_score:.2f} | "
              f"Langue={coh_icon} | Refus={refus_icon} | ⏱ {latence:.2f}s")
        if faith_detail:
            print(f"  ℹ️  {faith_detail}")

        resultats.append({
            "question"         : question,
            "langue"           : langue,
            "hors_sujet"       : hors_sujet,
            "reponse"          : reponse,
            "contexte_recu"    : contexte[:300] if contexte else "",
            "faithfulness"     : round(faith_score, 3) if faith_score is not None else None,
            "answer_relevancy" : round(relev_score, 3),
            "context_precision": round(prec_score, 3),
            "context_recall"   : round(recall_score, 3),
            "coherence_langue" : coh_score,
            "refus_score"      : refus_score,
            "latence_sec"      : round(latence, 3),
        })

        time.sleep(8.0)  # ← augmenté pour éviter rate limit tokens

    # ── Résumé ──
    def moy(lst): return round(np.mean(lst), 3) if lst else 0.0
    def moy_langue(lang, cle):
        vals = [r[cle] for r in langue_results.get(lang, [])]
        return moy(vals)

    faith_moy  = moy(scores_faith)
    relev_moy  = moy(scores_relev)
    prec_moy   = moy(scores_prec)
    recall_moy = moy(scores_recall)
    coh_moy    = moy(scores_coherence)
    refus_moy  = moy(scores_refus)   # ← moyenne simple
    lat_moy    = moy(latences)
    lat_max    = round(max(latences), 3) if latences else 0

    f1 = round(2 * (prec_moy * recall_moy) / (prec_moy + recall_moy + 1e-9), 3)

    nb_evaluees = len(scores_faith)

    print(f"\n{'='*65}")
    print(f"  RÉSULTATS FINAUX ({nb_evaluees}/{len(tests)} questions évaluées)")
    print(f"{'='*65}")
    print(f"  Faithfulness      (anti-hallucination) : {faith_moy:.3f} / 1.0")
    print(f"  Answer Relevancy  (pertinence)         : {relev_moy:.3f} / 1.0")
    print(f"  Context Precision (qualité ChromaDB)   : {prec_moy:.3f} / 1.0")
    print(f"  Context Recall    (couverture réponse) : {recall_moy:.3f} / 1.0")
    print(f"  F1 Score RAG                           : {f1:.3f} / 1.0")
    print(f"  Cohérence langue                       : {coh_moy:.3f} / 1.0")
    print(f"  Score refus hors sujet                 : {refus_moy:.3f} / 1.0")
    print(f"  Latence moyenne                        : {lat_moy:.2f}s")
    print(f"  Latence maximale                       : {lat_max:.2f}s")

    print(f"\n  SCORES PAR LANGUE :")
    for lang in ["fr", "ar", "en"]:
        nb = len(langue_results[lang])
        if nb > 0:
            print(f"  {lang.upper()} ({nb} questions) — "
                  f"Faith={moy_langue(lang,'faithfulness'):.2f} | "
                  f"Relev={moy_langue(lang,'answer_relevancy'):.2f} | "
                  f"Recall={moy_langue(lang,'context_recall'):.2f}")

    print(f"\n  INTERPRÉTATION :")
    seuils = {
        "Faithfulness"     : (faith_moy,  0.8, "hallucinations détectées"),
        "Answer Relevancy" : (relev_moy,  0.7, "réponses hors sujet"),
        "Context Precision": (prec_moy,   0.7, "ChromaDB retourne des docs non pertinents"),
        "Context Recall"   : (recall_moy, 0.6, "ChromaDB manque des docs importants"),
        "Cohérence langue" : (coh_moy,    0.9, "problème détection langue"),
        "Score refus"      : (refus_moy,  0.8, "hors sujet mal gérés"),
    }
    for nom, (score, seuil, probleme) in seuils.items():
        icone = "✅" if score >= seuil else "⚠️ "
        label = "BON" if score >= seuil else f"À AMÉLIORER ({probleme})"
        print(f"  {icone} {nom:25s} : {score:.3f} — {label}")

    rapport = {
        "date"          : datetime.now().isoformat(),
        "api_url"       : api_url,
        "nb_questions"  : len(tests),
        "nb_evaluees"   : nb_evaluees,
        "moyennes"      : {
            "faithfulness"      : faith_moy,
            "answer_relevancy"  : relev_moy,
            "context_precision" : prec_moy,
            "context_recall"    : recall_moy,
            "f1_score_rag"      : f1,
            "coherence_langue"  : coh_moy,
            "score_refus"       : refus_moy,
            "latence_moy_sec"   : lat_moy,
            "latence_max_sec"   : lat_max,
        },
        "scores_par_langue": {
            lang: {
                "faithfulness"    : moy_langue(lang, "faithfulness"),
                "answer_relevancy": moy_langue(lang, "answer_relevancy"),
                "context_recall"  : moy_langue(lang, "context_recall"),
                "nb_questions"    : len(langue_results[lang])
            }
            for lang in ["fr", "ar", "en"]
        },
        "resultats_detailles": resultats
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
        print(f"\n  💾 Rapport : {output_path}")

    return rapport

# ══════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api",     default="http://localhost:5000")
    parser.add_argument("--output",  default="results/evaluationllama.json")
    parser.add_argument("--dataset", default="dataset_test.csv")
    args = parser.parse_args()

    dataset = charger_dataset(args.dataset)
    evaluer(args.api, args.output, dataset)