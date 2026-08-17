import os
import re
import json
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb.utils import embedding_functions
from database import SessionLocal, Offer, FAQ, Service

CHROMA_DIR     = os.getenv("CHROMA_DIR", "chroma_db/")
os.makedirs(CHROMA_DIR, exist_ok=True)
MODEL_NAME     = "paraphrase-multilingual-MiniLM-L12-v2"
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


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
#  PARSER PIPE ROBUSTE
#  Gère les valeurs contenant ':' (JSON embarqué, URLs, textes longs)
#  Exemple : ... | qa_pairs: [{"q": "...", "a": "..."}] | url: https://...
# ════════════════════════════════════════════════════════════════════

def parser_contenu(content: str) -> dict:
    """
    Parse le format pipe : [fichier.csv] Clé1: Val1 | Clé2: Val2 | ...

    Robuste aux valeurs complexes contenant ':' (JSON, URLs).
    Le split se fait uniquement sur les '|' suivis d'un nom de clé (mot:),
    pas sur les '|' à l'intérieur d'une valeur JSON ou d'une URL.
    """
    content_clean = re.sub(r'^\[.*?\]\s*', '', content).strip()
    champs = {}

    # Split sur ' | ' uniquement quand suivi d'un identifiant clé (lettres/chiffres/_ puis ':')
    # Cela évite de couper les URLs (https://...) et les JSON internes [{...}]
    parties = re.split(r'\s*\|\s*(?=[a-zA-Z_]\w*\s*:)', content_clean)

    for partie in parties:
        partie = partie.strip()
        if ':' in partie:
            cle, _, valeur = partie.partition(':')
            champs[cle.strip().lower()] = valeur.strip()

    return champs


def extraire_valeur_numerique(texte: str) -> float:
    if not texte:
        return 0.0
    val_clean = re.sub(r'(?<=\d)\s+(?=\d)', '', str(texte))
    match = re.search(r'(\d+(?:\.\d+)?)', val_clean)
    return float(match.group(1)) if match else 0.0


# ════════════════════════════════════════════════════════════════════
#  EXTRACTION QA_PAIRS
#  Les qa_pairs sont un JSON embarqué dans le pipe :
#  qa_pairs: [{"q": "...", "a": "..."}, ...]
# ════════════════════════════════════════════════════════════════════

def extraire_qa_pairs(valeur: str) -> list[dict]:
    """
    Parse la valeur JSON de qa_pairs.
    Retourne une liste de dicts {"q": ..., "a": ...} ou [] si échec.
    """
    if not valeur:
        return []
    try:
        valeur = valeur.strip()
        # Parfois la valeur est tronquée par le split — on tente quand même
        data = json.loads(valeur)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)
                    and "q" in item and "a" in item]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


# ════════════════════════════════════════════════════════════════════
#  KEYWORDS MULTILINGUES
# ════════════════════════════════════════════════════════════════════

def construire_keywords(content: str) -> list[str]:
    """Construit une liste de mots-clés multilingues selon le contenu."""
    content_lower = content.lower()
    keywords = []

    if any(w in content_lower for w in ["roaming", "voyage", "étranger", "etranger",
                                         "hadj", "omra", "espagne", "turquie", "france", "pays"]):
        keywords.extend(["roaming", "voyage", "travel", "international",
                          "تجوال", "سفر", "الخارج"])

    if any(w in content_lower for w in ["facture", "facturation", "paiement", "payer",
                                         "pay", "bill", "edahabia", "visa"]):
        keywords.extend(["bill", "invoice", "payment", "pay", "facture",
                          "paiement", "فاتورة", "دفع", "سداد"])

    if any(w in content_lower for w in ["activation", "activer", "souscrire",
                                         "ussd", "code", "composer"]):
        keywords.extend(["activation", "activate", "subscribe", "ussd", "code",
                          "تفعيل", "تشغيل", "اشتراك", "رمز"])

    if any(w in content_lower for w in ["sim", "puce", "usim", "e-sim", "carte"]):
        keywords.extend(["sim card", "puce", "chip", "carte sim", "شريحة", "بطاقة SIM"])

    if any(w in content_lower for w in ["recharge", "recharger", "crédit", "credit", "flexy"]):
        keywords.extend(["recharge", "credit", "top up", "recharger", "تعبئة", "شحن", "رصيد"])

    if any(w in content_lower for w in ["internet", "data", "données", "donnees",
                                         "go", "mo", "octets"]):
        keywords.extend(["internet", "data", "volume", "go", "gb", "انترنت", "بيانات", "جيجا"])

    if any(w in content_lower for w in ["appel", "appels", "minutes", "voix",
                                         "voice", "call", "calls"]):
        keywords.extend(["call", "calls", "minutes", "voice", "appel", "voix",
                          "مكالمات", "اتصال", "دقائق"])

    if any(w in content_lower for w in ["gratuit", "gratuite", "gratuité", "free", "offert"]):
        keywords.extend(["free", "gratis", "gratuit", "مجاني", "بدون رسوم"])

    if any(w in content_lower for w in ["offre", "forfait", "plan", "package"]):
        keywords.extend(["offer", "package", "plan", "forfait", "offre",
                          "عرض", "باقة", "اشتراك"])

    if any(w in content_lower for w in ["transfert", "transfer", "flexily", "envoyer"]):
        keywords.extend(["transfer", "send credit", "transfert", "تحويل", "إرسال رصيد"])

    if any(w in content_lower for w in ["urgence", "tranquilo", "crédit d'urgence"]):
        keywords.extend(["emergency credit", "crédit urgence", "رصيد طوارئ", "سلفة"])

    if any(w in content_lower for w in ["service", "description", "fonctionnalite",
                                         "qa_pairs", "url"]):
        keywords.extend(["service", "djezzy service", "خدمة", "djezzy"])

    return list(set(keywords))


# ════════════════════════════════════════════════════════════════════
#  CHUNKING UNIFIÉ
#  Un seul point d'entrée pour Offres, FAQ et Services.
#  Tous au format pipe — seuls les champs disponibles diffèrent.
#
#  Champs offres  : nom_offre/prix_da/volume_internet_go/validite_jours/pays
#  Champs services: nom_offre/service/description/activation/codes/
#                   conditions/limites/cible/qa_pairs/url
#  Champs FAQ     : question/reponse/answer  (ou texte libre)
# ════════════════════════════════════════════════════════════════════

def creer_chunks(doc_id: str, content: str, category: str,
                 meta: dict) -> list[dict]:
    """
    Fonction unifiée de chunking pour tous les types de documents.
    Tous sont au format pipe — on détecte le sous-type via les champs présents.

    Types détectés automatiquement :
    - offre   : champs prix_da / volume_internet_go / validite_jours
    - service : champs description / activation / codes / qa_pairs
    - faq     : champs question / reponse (ou texte libre)
    """
    champs = parser_contenu(content)
    chunks = []

    # ── Détection du sous-type via les champs présents ──
    est_offre   = any(k in champs for k in ["prix_da", "prix", "price",
                                             "volume_internet_go", "data_go",
                                             "validite_jours", "duree_j"])
    est_service = any(k in champs for k in ["description", "activation",
                                             "codes", "qa_pairs", "url",
                                             "fonctionnalites"])
    # FAQ : soit champs question/reponse, soit texte libre sans champs connus
    est_faq     = any(k in champs for k in ["question", "reponse", "answer",
                                             "qa_pairs"])

    # ── Extraction champs communs ──
    nom = (champs.get("nom_offre") or champs.get("offre")   or
           champs.get("service")   or champs.get("nom")     or
           champs.get("name")      or champs.get("forfait") or
           champs.get("pack")      or champs.get("produit") or "").strip()

    # Fallback nom : premier champ non numérique
    if not nom:
        for v in champs.values():
            v = v.strip()
            if v and not re.match(r"^\d", v) and len(v) > 2:
                nom = v
                break
    if not nom:
        nom = content[:50].strip()

    # ── Extraction champs offres ──
    prix_str  = (champs.get("prix_da") or champs.get("prix") or
                 champs.get("price")   or "")
    data_str  = (champs.get("volume_internet_go") or champs.get("data_go") or
                 champs.get("internet") or champs.get("data") or "")
    duree_str = (champs.get("validite_jours") or champs.get("duree_j") or
                 champs.get("validite") or champs.get("duree") or "")
    pays_str  = champs.get("pays", "")

    prix  = extraire_valeur_numerique(prix_str)  if prix_str  else 0.0
    data  = extraire_valeur_numerique(data_str)  if data_str  else 0.0
    duree = extraire_valeur_numerique(duree_str) if duree_str else 0.0

    # ── Extraction champs services ──
    description  = champs.get("description", "")
    activation   = champs.get("activation", "")
    codes        = champs.get("codes", "")
    conditions   = champs.get("conditions", "")
    limites      = champs.get("limites", "")
    cible        = champs.get("cible", "")
    fonctions    = champs.get("fonctionnalites", "")
    remarques    = champs.get("remarques", "")
    url          = champs.get("url", "")
    categorie_ch = champs.get("categorie", "")

    # ── Extraction qa_pairs (services enrichis avec scraping) ──
    qa_pairs = extraire_qa_pairs(champs.get("qa_pairs", ""))

    # ── Mots-clés multilingues ──
    keywords = construire_keywords(content)

    # ════════════════════════════════════════════════
    #  CHUNK 0 : Résumé dense
    # ════════════════════════════════════════════════
    if est_offre and not est_service:
        # Résumé offre : nom + prix + data + durée
        parties = [nom]
        if prix  > 0: parties.append(f"{int(prix)} DA")
        if data  > 0: parties.append(f"{data} Go internet")
        if duree > 0: parties.append(f"{int(duree)} jours")
        if pays_str:  parties.append(f"pays: {pays_str}")
        resume = " — ".join(parties)
    else:
        # Résumé service/FAQ : nom + description
        resume = f"{nom} — {description}" if description else nom
        if cible:       resume += f" — Pour: {cible}"
        if categorie_ch: resume += f" — Catégorie: {categorie_ch}"

    chunks.append({
        "id":         f"{doc_id}_chunk0",
        "content":    resume,
        "chunk_type": "resume",
        "source_id":  doc_id,
        "original":   content,
    })

    # ════════════════════════════════════════════════
    #  CHUNK résumé EN
    # ════════════════════════════════════════════════
    if est_offre and not est_service:
        parties_en = [nom]
        if "djezzy" in nom.lower(): parties_en.append("Djezzy")
        if prix  > 0: parties_en.append(f"{int(prix)} dinars")
        if data  > 0: parties_en.append(f"{data} GB internet")
        if duree > 0: parties_en.append(f"{int(duree)} days")
        if pays_str:  parties_en.append(f"country: {pays_str}")
        resume_en = " — ".join(parties_en)
    else:
        resume_en = f"{nom} — {description}"
        if activation: resume_en += f" — How to activate: {activation}"

    chunks.append({
        "id":         f"{doc_id}_chunk_en",
        "content":    resume_en,
        "chunk_type": "resume_en",
        "source_id":  doc_id,
        "original":   content,
    })

    # ════════════════════════════════════════════════
    #  CHUNK résumé AR
    # ════════════════════════════════════════════════
    if est_offre and not est_service:
        parties_ar = [nom]
        if "djezzy" in nom.lower(): parties_ar.append("دجيزي")
        if prix  > 0: parties_ar.append(f"{int(prix)} دينار جزائري")
        if data  > 0: parties_ar.append(f"{data} جيجا إنترنت")
        if duree > 0: parties_ar.append(f"{int(duree)} يوم")
        if pays_str:  parties_ar.append(f"بلد: {pays_str}")
        resume_ar = " — ".join(parties_ar) + " — عروض إنترنت دجيزي"
    else:
        resume_ar = f"{nom} — {description} — دجيزي"
        if activation: resume_ar += f" — كيفية التفعيل: {activation}"

    chunks.append({
        "id":         f"{doc_id}_chunk_ar",
        "content":    resume_ar,
        "chunk_type": "resume_ar",
        "source_id":  doc_id,
        "original":   content,
    })

    # ════════════════════════════════════════════════
    #  CHUNKS SPÉCIFIQUES OFFRES
    # ════════════════════════════════════════════════

    if est_offre and not est_service:
        # Chunk prix/budget
        if prix > 0:
            chunk_prix = (f"{nom} coûte {int(prix)} dinars algériens"
                          + (f" pour {int(duree)} jours" if duree > 0 else "")
                          + (f" avec {data} Go de données" if data > 0 else ""))
            chunks.append({
                "id":         f"{doc_id}_chunk1",
                "content":    chunk_prix,
                "chunk_type": "prix",
                "source_id":  doc_id,
                "original":   content,
            })

        # Chunk data/internet
        if data > 0:
            chunk_data = (f"{nom} offre {data} Go d'internet"
                          + (f" à {int(prix)} dinars algériens" if prix > 0 else "")
                          + (f" valable {int(duree)} jours" if duree > 0 else ""))
            chunks.append({
                "id":         f"{doc_id}_chunk2",
                "content":    chunk_data,
                "chunk_type": "data",
                "source_id":  doc_id,
                "original":   content,
            })

    # ════════════════════════════════════════════════
    #  CHUNKS SPÉCIFIQUES SERVICES
    # ════════════════════════════════════════════════

    elif est_service:
        # Chunk activation / codes USSD
        # Répond à : "comment activer X", "quel code pour X", "comment utiliser X"
        if activation or codes:
            chunk_activation = f"{nom} — Activation: {activation}"
            if codes:     chunk_activation += f" | Codes USSD: {codes}"
            if fonctions: chunk_activation += f" | Fonctionnalités: {fonctions}"
            chunks.append({
                "id":         f"{doc_id}_chunk1",
                "content":    chunk_activation,
                "chunk_type": "activation",
                "source_id":  doc_id,
                "original":   content,
            })

        # Chunk conditions / limites / éligibilité
        # Répond à : "conditions pour X", "qui peut utiliser X", "limites X"
        if conditions or limites or cible:
            chunk_conditions = f"{nom} — Conditions: {conditions}"
            if limites: chunk_conditions += f" | Limites: {limites}"
            if cible:   chunk_conditions += f" | Cible: {cible}"
            chunks.append({
                "id":         f"{doc_id}_chunk2",
                "content":    chunk_conditions,
                "chunk_type": "conditions",
                "source_id":  doc_id,
                "original":   content,
            })

        # ── Chunks QA pairs ──
        # Chaque paire Q/A devient un chunk dédié.
        # C'est le chunk le plus puissant pour le RAG :
        # quand l'utilisateur pose exactement la même question,
        # la similarité cosinus sera maximale.
        for i, qa in enumerate(qa_pairs):
            q = qa.get("q", "").strip()
            a = qa.get("a", "").strip()
            if q and a:
                chunk_qa = f"Q: {q}\nR: {a}"
                chunks.append({
                    "id":         f"{doc_id}_chunk_qa_{i}",
                    "content":    chunk_qa,
                    "chunk_type": "qa",
                    "source_id":  doc_id,
                    "original":   content,
                })

    # ════════════════════════════════════════════════
    #  CHUNK 3 : Contenu complet enrichi (commun à tous)
    # ════════════════════════════════════════════════

    content_clean = re.sub(r'^\[.*?\]\s*', '', content).strip()

    # Pour les services : reconstruire un texte lisible sans le JSON qa_pairs brut
    if est_service:
        parties_complet = []
        if categorie_ch: parties_complet.append(f"Catégorie: {categorie_ch}")
        parties_complet.append(f"{nom}: {description}")
        if fonctions:   parties_complet.append(f"Fonctionnalités: {fonctions}")
        if conditions:  parties_complet.append(f"Conditions: {conditions}")
        if activation:  parties_complet.append(f"Activation: {activation}")
        if codes:       parties_complet.append(f"Codes USSD: {codes}")
        if limites:     parties_complet.append(f"Limites: {limites}")
        if cible:       parties_complet.append(f"Cible: {cible}")
        if remarques:   parties_complet.append(f"Remarques: {remarques}")
        if url:         parties_complet.append(f"Plus d'infos: {url}")
        # Ajouter les Q/A en texte lisible (pas en JSON brut)
        for qa in qa_pairs:
            q = qa.get("q", "").strip()
            a = qa.get("a", "").strip()
            if q and a:
                parties_complet.append(f"Q: {q} — R: {a}")
        content_clean = ". ".join(p for p in parties_complet if p.strip(". "))

    # Enrichissement keywords
    if keywords:
        content_clean += "\nKeywords: " + ", ".join(keywords)

    # Enrichissement valeurs normalisées (offres uniquement)
    if est_offre and not est_service:
        valeurs_norm = []
        if prix  > 0: valeurs_norm.append(f"{int(prix)}DA {int(prix)} DA {int(prix)} dinars")
        if data  > 0: valeurs_norm.append(f"{data}Go {data} Go {data}GB")
        if duree > 0: valeurs_norm.append(f"{int(duree)}j {int(duree)} jours {int(duree)} days")
        if valeurs_norm:
            content_clean += "\nValeurs: " + " | ".join(valeurs_norm)

    chunks.append({
        "id":         f"{doc_id}_chunk3",
        "content":    content_clean,
        "chunk_type": "complet",
        "source_id":  doc_id,
        "original":   content,
    })

    return chunks


# ════════════════════════════════════════════════════════════════════
#  EXTRACTION MÉTADONNÉES
# ════════════════════════════════════════════════════════════════════

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
    if not champs:
        meta_defaut["nom_offre"] = content[:60].strip()
        return meta_defaut

    # ── Nom (commun à tous les types) ──
    nom = (champs.get("nom_offre") or champs.get("offre")   or
           champs.get("service")   or champs.get("nom")     or
           champs.get("name")      or champs.get("forfait") or
           champs.get("pack")      or champs.get("produit") or "")

    # ── Détection sous-type ──
    est_offre   = any(k in champs for k in ["prix_da", "prix", "price",
                                             "volume_internet_go", "data_go",
                                             "validite_jours", "duree_j"])
    est_service = any(k in champs for k in ["description", "activation",
                                             "codes", "qa_pairs", "url"])

    if est_offre and not est_service:
        # Extraction numérique offres
        prix_str  = champs.get("prix_da") or champs.get("prix") or ""
        data_str  = (champs.get("volume_internet_go") or champs.get("data_go") or
                     champs.get("internet") or "")
        duree_str = (champs.get("validite_jours") or champs.get("duree_j") or
                     champs.get("validite") or "")

        prix  = int(extraire_valeur_numerique(prix_str))  if prix_str  else 0
        data  = extraire_valeur_numerique(data_str)       if data_str  else 0.0
        duree = int(extraire_valeur_numerique(duree_str)) if duree_str else 30

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
        print(f"  ✅ Offre  : {nom} | {prix} DA | {data} Go | {duree}j")

    elif est_service:
        # Métadonnées services
        cat = champs.get("categorie", category)
        meta_defaut.update({
            "nom_offre" : nom,
            "categorie" : cat,
            "type_offre": "service",
            "roaming"   : any(kw in content.lower() for kw in
                              ["roaming", "international", "hadj", "omra", "étranger"]),
        })
        print(f"  ✅ Service: {nom} | catégorie: {cat}")

    else:
        # FAQ ou texte libre
        meta_defaut.update({
            "nom_offre" : nom or content[:60].strip(),
            "type_offre": "faq",
        })
        print(f"  ✅ FAQ    : {(nom or content)[:40]}...")

    return meta_defaut


# ════════════════════════════════════════════════════════════════════
#  INDEX CHROMADB
# ════════════════════════════════════════════════════════════════════

def load_or_build_index(embedder, groq_client=None):
    """
    Charge ou construit ChromaDB avec chunking intelligent unifié.
    Tous les documents (Offres, FAQ, Services) sont au format pipe —
    le sous-type est détecté automatiquement via les champs présents.
    """
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME
    )

    collection = chroma_client.get_or_create_collection(
        name               = "izzy_offers",
        embedding_function = ef,
        metadata           = {"hnsw:space": "cosine"}
    )

    db = SessionLocal()
    try:
        documents = []
        for Model in [Offer, FAQ, Service]:
            rows = db.query(Model).filter_by(is_active=True).all()
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
                chunk_meta = {
                    **meta,
                    "chunk_type": chunk["chunk_type"],
                    "source_id" : chunk["source_id"],
                }
                tous_chunks.append({
                    "id"      : chunk["id"],
                    "content" : chunk["content"],
                    "original": chunk["original"],
                    "meta"    : chunk_meta,
                })

    if tous_chunks:
        nb_par_doc = len(tous_chunks) // max(len(documents), 1)
        print(f"🔄 Ajout de {len(tous_chunks)} chunks "
              f"({len(documents)} docs × ~{nb_par_doc} chunks/doc)...")

        batch_size = 100
        for i in range(0, len(tous_chunks), batch_size):
            lot = tous_chunks[i:i + batch_size]
            collection.add(
                ids       = [c["id"]      for c in lot],
                documents = [c["content"] for c in lot],
                metadatas = [{**c["meta"], "original": c["original"]} for c in lot],
            )
            print(f"  ↳ {min(i + batch_size, len(tous_chunks))}/{len(tous_chunks)} chunks ajoutés")

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