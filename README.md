# IZZY — Assistant IA Telecom (FastAPI + React + PostgreSQL)

IZZY est un assistant intelligent basé sur un système RAG (Retrieval-Augmented Generation) permettant de répondre aux questions liées aux offres, services et FAQ télécoms.

Le projet utilise :

* FastAPI pour le backend
* PostgreSQL pour le stockage des données
* React pour l’interface utilisateur
* des modèles IA pour la génération des réponses et la reconnaissance vocale

---

# Installation

Installer les dépendances Python :

```bash
pip install -r requirements.txt
```

---

# Configuration

## Étape 1 — Configurer PostgreSQL

Ouvrir pgAdmin ou psql puis exécuter :

```bash
psql -U postgres -f setup_postgres.sql
```

Cette étape permet de :

* créer la base de données `izzy_db`
* créer les tables nécessaires
* créer l’utilisateur PostgreSQL du projet

---

## Étape 2 — Configurer le fichier `.env`

Modifier le fichier `.env` avec vos informations :

```env
DATABASE_URL=postgresql://izzy_user:VOTRE_MOT_DE_PASSE@localhost:5432/izzy_db
GROQ_API_KEY=votre_cle_groq
```

---

# Préparation des données

## Étape 3 — Augmentation des données

Avant d’importer les données dans PostgreSQL, lancer le script d’augmentation :

```bash
python Augmentedata.py
```

Cette étape permet :

* d’ajouter des variantes linguistiques
* d’améliorer la reconnaissance des offres
* d’associer certains noms d’offres en français et en arabe

---

## Étape 4 — Migration des données vers PostgreSQL

Importer les données CSV dans PostgreSQL :

```bash
python migrate.py
```

Cette étape :

* lit les fichiers CSV
* nettoie les données
* insère les données dans PostgreSQL

---

# Lancer l’application

## Étape 5 — Démarrer le backend FastAPI

```bash
uvicorn app:app --reload --port 5000
```

```bash
python app.py
```

---

## Étape 6 — Démarrer le frontend React

Ouvrir un nouveau terminal puis entrer dans le dossier frontend :

```bash
cd frontend
```

Installer les dépendances :

```bash
npm install
```

Lancer le frontend :

```bash
npm run dev
```

---

# Accès à l’application

| URL                         | Description                |
| --------------------------- | -------------------------- |
| http://localhost:5173       | Interface utilisateur      |
| http://localhost:5173/admin | Interface d’administration |
| http://localhost:5000/docs  | Documentation API          |

---

# Fonctionnalités

* Chat intelligent basé sur RAG
* Recherche sémantique avec embeddings
* Support multilingue (français / arabe)
* Reconnaissance vocale (STT)
* Synthèse vocale (TTS)
* Interface d’administration
* Gestion des offres, FAQ et services

---

# Technologies utilisées

* FastAPI
* PostgreSQL
* React
* Sentence Transformers
* Groq API
* Whisper
* Recherche vectorielle

---

# Structure du projet

```text
PFEwithPostgres/
│
├── backend/
│   ├── app.py
│   ├── augmentation.py
│   ├── migrate.py
│   ├── setup_postgres.sql
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── data/
│   └── *.csv
│
└── README.md
```
