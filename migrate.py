"""
migrate.py — Import CSV → PostgreSQL (offers / faq / services)

Le fichier est routé automatiquement selon son nom :
  - contient "faq"                    → table faq
  - contient "service"                → table services
  - tout le reste                     → table offers  ← augmentés

Usage :
  python migrate.py                   ← importe tout le dossier DataSet/
  python migrate.py --clear           ← vide les 3 tables avant import
"""

import os
import argparse
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from database import init_db, SessionLocal, Offer, FAQ, Service

DATASET_FOLDER = "augmented_files/"


def detect_table(filename: str):
    """
    Retourne le modèle SQLAlchemy selon le nom du fichier CSV.
    Règles :
      faq* / *_faq* / *questions*  → FAQ
      service* / *_service*        → Service
      tout le reste                → Offer
    """
    name = filename.lower().replace(".csv", "")

    if any(kw in name for kw in ["faq", "question", "aide", "help"]):
        return FAQ, "faq"
    elif any(kw in name for kw in ["service", "assistance", "support"]):
        return Service, "service"
    else:
        return Offer, "offer"


def import_csv_to_db(clear_first: bool = False):
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

        for filename in sorted(os.listdir(DATASET_FOLDER)):
            if not filename.endswith(".csv"):
                continue

            path      = os.path.join(DATASET_FOLDER, filename)
            df        = pd.read_csv(path)
            Model, _  = detect_table(filename)
            category  = filename.replace(".csv", "")
            table     = Model.__tablename__

            print(f"\n📂 {filename} → table [{table}] ({len(df)} lignes)")

            for _, row in df.iterrows():
                content = f"[{filename}] " + " | ".join(
                    [f"{col}: {str(row[col])}" for col in df.columns
                     if str(row[col]).strip() not in ["", "nan"]]
                )

                if db.query(Model).filter_by(content=content).first():
                    total_skipped += 1
                    continue

                db.add(Model(
                    content=content,
                    category=category,
                    is_active=True,
                    needs_reindex=True
                ))
                total_imported += 1

            db.commit()

        # Résumé par table
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
    parser.add_argument("--clear", action="store_true",
                        help="Vider les 3 tables avant import")
    args = parser.parse_args()
    import_csv_to_db(args.clear)