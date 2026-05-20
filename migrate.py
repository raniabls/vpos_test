"""
migrate.py — Import CSV normalisés → PostgreSQL
Stocke les colonnes numériques (prix, data_go, duree_j...)
directement dans la BDD pour le SQL search hybride.

Usage :
  python migrate.py                   ← importe tout le dossier
  python migrate.py --clear           ← vide les tables avant import
  python migrate.py --folder data_normalized/
"""

import os
import re
import argparse
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from database import init_db, SessionLocal, Offer, FAQ, Service

DATASET_FOLDER = "data_normalized/"

# ════════════════════════════════════════════════════════════════════
#  MAPPING COLONNES NORMALISÉES → champs numériques
# ════════════════════════════════════════════════════════════════════

# Colonnes qui contiennent le prix principal
COLS_PRIX = {"prix_da", "prix", "prix_forfait", "prix_normal", "price"}

# Colonnes qui contiennent le prix remisé
COLS_PRIX_REMISE = {"prix_remise", "prix_apres_remise_50", "prix_apres_remise"}

# Colonnes qui contiennent la data
COLS_DATA = {"volume_internet_go", "volume_internet", "internet", "data_go"}

# Colonnes qui contiennent la durée
COLS_DUREE = {"validite_jours", "validite", "validity", "validité"}

# Colonnes qui contiennent le nom de l'offre
COLS_NOM = {"nom_offre", "offre", "forfait_principal", "pack", "name", "period"}


def extraire_nombre(valeur: str) -> float:
    """Extrait le premier nombre d'une chaîne."""
    if not valeur or str(valeur).strip() in ["", "nan"]:
        return 0.0
    match = re.search(r'(\d+(?:\.\d+)?)', str(valeur))
    return float(match.group(1)) if match else 0.0


def extraire_metadonnees_row(row: pd.Series, colonnes: list[str]) -> dict:
    """
    Extrait les métadonnées numériques d'une ligne CSV.
    Cherche dans toutes les colonnes normalisées.
    """
    cols_lower = {c.lower(): c for c in colonnes}

    def get_val(col_set):
        for col in col_set:
            if col in cols_lower:
                return str(row.get(cols_lower[col], ""))
        return ""

    # ── Prix ──
    prix_str = get_val(COLS_PRIX)
    prix     = int(extraire_nombre(prix_str)) if prix_str else 0

    # ── Prix remise ──
    prix_remise_str = get_val(COLS_PRIX_REMISE)
    prix_remise     = int(extraire_nombre(prix_remise_str)) if prix_remise_str else 0

    # ── Data ──
    data_str = get_val(COLS_DATA)
    data_val = extraire_nombre(data_str)
    # Convertir Mo → Go si nécessaire
    if data_str and any(u in data_str.lower() for u in ["mo", "mb"]):
        data_val = round(data_val / 1024, 2)
    data_go = data_val

    # ── Durée ──
    duree_str = get_val(COLS_DUREE)
    duree_val = extraire_nombre(duree_str)
    if duree_str and "mois" in duree_str.lower():
        duree_j = int(duree_val * 30)
    elif duree_val > 0:
        duree_j = int(duree_val)
    else:
        duree_j = 30

    # ── Nom offre ──
    nom_str = get_val(COLS_NOM)
    nom     = str(nom_str).strip() if nom_str and nom_str != "nan" else ""

    # ── Illimité ──
    content_full = " ".join(str(v) for v in row.values).lower()
    illimite     = any(kw in content_full for kw in
                       ["illimit", "unlimited", "غير محدود", "sans limite"])

    # ── Réseau ──
    reseau = "5g" if "5g" in content_full else "4g"

    # ── Type offre ──
    if any(kw in content_full for kw in ["tod", "shahid", "netflix", "streaming"]):
        type_offre = "streaming"
    elif any(kw in content_full for kw in ["roaming", "international", "hadj", "omra",
                                            "espagne", "turquie", "france"]):
        type_offre = "roaming"
    elif any(kw in content_full for kw in ["postpay", "post-pay", "facture", "abonnement"]):
        type_offre = "postpaye"
    else:
        type_offre = "prepaye"

    # ── Roaming ──
    roaming = any(kw in content_full for kw in
                  ["roaming", "international", "hadj", "omra",
                   "espagne", "turquie", "france", "étranger", "pays"])

    return {
        "prix"       : prix,
        "prix_remise": prix_remise,
        "data_go"    : data_go,
        "illimite"   : illimite,
        "duree_j"    : duree_j,
        "reseau"     : reseau,
        "type_offre" : type_offre,
        "roaming"    : roaming,
        "nom_offre"  : nom,
    }


# ════════════════════════════════════════════════════════════════════
#  ROUTING FICHIER → TABLE
# ════════════════════════════════════════════════════════════════════

def detect_table(filename: str):
    name = filename.lower().replace(".csv", "")
    if any(kw in name for kw in ["faq", "question", "aide", "help"]):
        return FAQ, "faq"
    elif any(kw in name for kw in ["service", "assistance", "support"]):
        return Service, "service"
    else:
        return Offer, "offer"


# ════════════════════════════════════════════════════════════════════
#  IMPORT PRINCIPAL
# ════════════════════════════════════════════════════════════════════

def import_csv_to_db(folder: str, clear_first: bool = False):
    init_db()
    db = SessionLocal()

    total_imported = 0
    total_skipped  = 0

    try:
        if clear_first:
            for Model in [Offer, FAQ, Service]:
                count = db.query(Model).count()
                db.query(Model).delete()
                print(f"🗑️  Table '{Model.__tablename__}' vidée ({count} lignes)")
            db.commit()

        for filename in sorted(os.listdir(folder)):
            if not filename.endswith(".csv"):
                continue

            path = os.path.join(folder, filename)
            try:
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
                print(f"  ⚠️  Encodage latin-1 : {filename}")

            if df.empty:
                print(f"  ⚠️  Fichier vide : {filename}")
                continue

            Model, _ = detect_table(filename)
            category = filename.replace(".csv", "")
            table    = Model.__tablename__
            colonnes = list(df.columns)

            print(f"\n📂 {filename} → [{table}] ({len(df)} lignes)")

            for _, row in df.iterrows():
                # Construire le contenu texte
                content = f"[{filename}] " + " | ".join(
                    f"{col}: {str(row[col])}"
                    for col in df.columns
                    if str(row[col]).strip() not in ["", "nan"]
                )

                # Ignorer les doublons
                if db.query(Model).filter_by(content=content).first():
                    total_skipped += 1
                    continue

                # Extraire les métadonnées numériques
                meta = extraire_metadonnees_row(row, colonnes)

                db.add(Model(
                    content     = content,
                    category    = category,
                    is_active   = True,
                    needs_reindex = True,
                    **meta       # prix, data_go, duree_j, nom_offre, etc.
                ))
                total_imported += 1

            db.commit()
            print(f"  ✅ {total_imported} lignes importées jusqu'ici")

        # ── Résumé ──
        print(f"\n{'='*55}")
        print(f"✅ Migration terminée")
        print(f"   Importées  : {total_imported}")
        print(f"   Ignorées   : {total_skipped} (doublons)")
        print(f"   Offers BDD : {db.query(Offer).count()}")
        print(f"   FAQ BDD    : {db.query(FAQ).count()}")
        print(f"   Services   : {db.query(Service).count()}")
        print(f"{'='*55}")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear",  action="store_true",
                        help="Vider les tables avant import")
    parser.add_argument("--folder", default=DATASET_FOLDER,
                        help="Dossier CSV à importer")
    args = parser.parse_args()
    import_csv_to_db(args.folder, args.clear)