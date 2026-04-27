""" Pour compiler soit 
  python Augmentedata.py --files DataSet/nomfichier.csv DataSet/nomfich.csv
  python Augmentedata.py --folder DataSet/ """

import os, json, csv, time, argparse, glob
import pandas as pd
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

# Tags automatiques selon les valeurs

def generer_tags(row: pd.Series) -> str:
    """
    Analyse les valeurs de la ligne et génère des tags descriptifs.
    Ces tags sont ajoutés au content pour aider FAISS à mieux matcher.

    Exemples :
      prix 200 DA  → [PRIX_BAS]
      data 20Go    → [GROS_VOLUME]
      illimité     → [ILLIMITE]
    """
    tags = []
    row_str = " ".join([str(v).lower() for v in row.values])

    # ── Tags PRIX ──
    try:
        # Cherche un nombre suivi de "da" ou "dinar"
        import re
        prix_match = re.search(r'(\d+)\s*(da|dinar|dzd)', row_str)
        if prix_match:
            prix = int(prix_match.group(1))
            if prix <= 300:
                tags.append("[PRIX_TRES_BAS]")
            elif prix <= 600:
                tags.append("[PRIX_BAS]")
            elif prix <= 1200:
                tags.append("[PRIX_MOYEN]")
            else:
                tags.append("[PRIX_ELEVE]")
    except Exception:
        pass

    # ── Tags DATA ──
    try:
        data_match = re.search(r'(\d+)\s*(go|gb|mo|mb)', row_str)
        if data_match:
            quantite = int(data_match.group(1))
            unite    = data_match.group(2)
            # Convertir Mo en Go pour comparer
            if unite in ["mo", "mb"]:
                quantite = quantite / 1024
            if quantite >= 50:
                tags.append("[TRES_GROS_VOLUME]")
            elif quantite >= 20:
                tags.append("[GROS_VOLUME]")
            elif quantite >= 5:
                tags.append("[VOLUME_MOYEN]")
            else:
                tags.append("[PETIT_VOLUME]")
    except Exception:
        pass

    # ── Tags ILLIMITÉ ──
    if any(kw in row_str for kw in ["illimit", "unlimited", "sans limite"]):
        tags.append("[ILLIMITE]")

    # ── Tags VALIDITÉ ──
    try:
        validite_match = re.search(r'(\d+)\s*(j|jour|jours|day)', row_str)
        if validite_match:
            jours = int(validite_match.group(1))
            if jours >= 30:
                tags.append("[LONGUE_DUREE]")
            elif jours >= 7:
                tags.append("[DUREE_MOYENNE]")
            else:
                tags.append("[COURTE_DUREE]")
    except Exception:
        pass

    # ── Tags RÉSEAU ──
    if "5g" in row_str:
        tags.append("[5G]")
    elif "4g" in row_str:
        tags.append("[4G]")
    elif "3g" in row_str:
        tags.append("[3G]")

    return " ".join(tags)


# ─────────────────────────────────────────────
# Construction du content
# ─────────────────────────────────────────────

def construire_content(filename: str, row: pd.Series) -> str:
    """
    Reconstruit le content exactement comme migrate.py.
    Ajoute les tags automatiques à la fin.

    Ex: [forfaits.csv] nom: Djezzy 5Go | prix: 500 DA | data: 5Go [PRIX_BAS] [VOLUME_MOYEN]
    """
    parts = [
        f"{col}: {str(row[col])}"
        for col in row.index
        if str(row[col]).strip() not in ["", "nan", "NaN"]
    ]
    content = f"[{filename}] " + " | ".join(parts)

    # Ajouter les tags
    tags = generer_tags(row)
    if tags:
        content = content + " " + tags

    return content


# ─────────────────────────────────────────────
# Génération — 2 variantes en français
# ─────────────────────────────────────────────

def generer_variantes(content: str, categorie: str, retries: int = 3) -> list[str]:
    """
    Génère 2 reformulations en français avec vocabulaire différent.
    """

    prompt = f"""Tu travailles sur la base de données d'Izzy, l'agent IA de Djezzy Algérie.

Voici une offre Djezzy :
"{content}"

Génère exactement 2 reformulations en français.
Règles STRICTES :
- Vocabulaire DIFFÉRENT entre les 2 versions et par rapport à l'original
- FRANÇAIS uniquement
- Garde TOUTES les informations exactes (prix, data, validité, réseau)
- Style naturel comme un conseiller Djezzy qui parle à un client
- Si le prix est bas (≤ 300 DA) : mentionne "économique", "abordable" ou "petit budget"
- Si le prix est moyen (301-600 DA) : mentionne "bon rapport qualité-prix"
- Si le prix est élevé (> 600 DA) : mentionne "premium" ou "haut de gamme"
- Si data ≥ 20Go : mentionne "généreux", "gros volume" ou "beaucoup de data"
- Si illimité : mentionne "sans restriction" ou "sans limite"
- Ne pas inventer de données
- Ne pas copier les tags comme [PRIX_BAS] dans la réponse

Retourne UNIQUEMENT ce JSON, rien d'autre :
{{"variantes": ["...", "..."]}}"""

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.75,
                max_tokens=400
            )
            text = response.choices[0].message.content.strip()

            # Nettoyer les backticks markdown
            if "```" in text:
                parts = text.split("```")
                text  = parts[1] if len(parts) > 1 else parts[0]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            data      = json.loads(text)
            variantes = data.get("variantes", [])

            if not isinstance(variantes, list) or len(variantes) < 2:
                raise ValueError(f"Pas assez de variantes : {len(variantes)}")

            # Garder max 2, nettoyer
            return [v.strip() for v in variantes[:2] if v.strip()]

        except Exception as e:
            print(f"    ⚠️  Tentative {attempt+1}/{retries} : {e}")
            if attempt < retries - 1:
                time.sleep(2)

    print("    ❌ Abandon pour cette ligne")
    return []


# ─────────────────────────────────────────────
# Traitement d'un fichier
# ─────────────────────────────────────────────

def augmenter_un_fichier(input_csv: str) -> str:
    dossier    = os.path.dirname(input_csv) or "."
    filename   = os.path.basename(input_csv)
    nom_base   = os.path.splitext(filename)[0]
    output_csv = os.path.join("augmented_files", f"{nom_base}_augmente.csv")
    categorie  = nom_base

    try:
        df = pd.read_csv(input_csv, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(input_csv, encoding="latin-1")
        print(f"  ⚠️  Encodage latin-1 détecté pour {filename}")

    total = len(df)
    print(f"\n{'─'*60}")
    print(f"📂 {filename} — {total} lignes — colonnes : {list(df.columns)}")
    print(f"🎯 Objectif : {total * 3} lignes (original + 2 variantes)")
    print(f"{'─'*60}")

    nouvelles_lignes = []

    for i, row in df.iterrows():
        content = construire_content(filename, row)

        if not content.strip():
            continue

        # Garder l'originale avec tags
        nouvelles_lignes.append({
            "content"      : content,
            "category"     : categorie,
            "is_active"    : "true",
            "needs_reindex": "true"
        })

        print(f"  [{i+1}/{total}] {content[:70]}...")

        # Générer 2 variantes
        variantes = generer_variantes(content, categorie)

        for v in variantes:
            nouvelles_lignes.append({
                "content"      : v,
                "category"     : categorie,
                "is_active"    : "true",
                "needs_reindex": "true"
            })

        print(f"    ✅ {len(variantes)} variantes | Sous-total : {len(nouvelles_lignes)}")
        time.sleep(0.5)

    # Sauvegarder
    fieldnames = ["content", "category", "is_active", "needs_reindex"]
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(nouvelles_lignes)

    print(f"\n  💾 {filename} → {output_csv}")
    print(f"     {total} originales + {len(nouvelles_lignes)-total} variantes = {len(nouvelles_lignes)} lignes")
    return output_csv


# ─────────────────────────────────────────────
# Traitement multi-fichiers
# ─────────────────────────────────────────────

def augmenter_plusieurs_fichiers(fichiers: list):
    print(f"\n🚀 {len(fichiers)} fichier(s) à traiter\n")
    resultats = []

    for filepath in fichiers:
        if not os.path.exists(filepath):
            print(f"❌ Introuvable : {filepath}")
            continue
        out = augmenter_un_fichier(filepath)
        if out:
            resultats.append((filepath, out))

    print(f"\n{'='*60}")
    print(f"🎉 RÉSUMÉ FINAL")
    print(f"{'='*60}")
    for src, dst in resultats:
        try:
            src_count = len(pd.read_csv(src))
            dst_count = sum(1 for _ in open(dst, encoding="utf-8")) - 1
            print(f"  {os.path.basename(src):35s} {src_count:>4} → {dst_count:>5} lignes")
        except Exception:
            print(f"  {os.path.basename(src)}")

    print(f"\n📌 Prochaine étape :")
    print(f"   python migrate.py --clear")
    print(f"{'='*60}")


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--files",  nargs="+", metavar="FICHIER")
    group.add_argument("--folder", metavar="DOSSIER")
    args = parser.parse_args()

    if args.folder:
        tous     = glob.glob(os.path.join(args.folder, "*.csv"))
        fichiers = [f for f in tous if "_augmente" not in f]
        if not fichiers:
            print(f"❌ Aucun CSV trouvé dans : {args.folder}")
        else:
            augmenter_plusieurs_fichiers(fichiers)
    else:
        augmenter_plusieurs_fichiers(args.files)