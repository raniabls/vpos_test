# IZZY — FastAPI + PostgreSQL

## Installation

```bash
pip install -r requirements.txt
```

## Configuration (IMPORTANT)

### Étape 1 — Configurer PostgreSQL
Ouvrir pgAdmin ou psql et exécuter :
```bash
psql -U postgres -f setup_postgres.sql
```

### Étape 2 — Configurer le fichier .env
Modifier `.env` avec tes vrais credentials :
```
DATABASE_URL=postgresql://izzy_user:TON_MOT_DE_PASSE@localhost:5432/izzy_db
GROQ_API_KEY=ta_cle_groq
```

### Étape 3 — Importer les données CSV
```bash
python migrate.py
```

### Étape 4 — Lancer l'application
```bash
uvicorn app:app --reload --port 5000
```

## Accès
| URL | Description |
|-----|-------------|
| http://localhost:5000 | Interface Izzy |
| http://localhost:5000/admin | Administration |
| http://localhost:5000/docs | Documentation API |
