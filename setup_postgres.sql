-- ══════════════════════════════════════════════════════════════════
-- setup_postgres.sql — Configuration initiale PostgreSQL
-- 
-- À exécuter UNE SEULE FOIS dans pgAdmin ou psql :
-- psql -U postgres -f setup_postgres.sql
-- ══════════════════════════════════════════════════════════════════


-- ── Étape 1 : Créer l'utilisateur ────────────────────────────────
-- Remplace 'motdepasse' par un vrai mot de passe
CREATE USER izzy_user WITH PASSWORD 'rania';


-- ── Étape 2 : Créer la base de données ───────────────────────────
CREATE DATABASE izzy_db
    WITH OWNER     = izzy_user
    ENCODING       = 'UTF8'        -- supporte l'arabe, le français, l'anglais
    LC_COLLATE     = 'fr_FR.UTF-8' -- tri alphabétique français
    LC_CTYPE       = 'fr_FR.UTF-8'
    TEMPLATE       = template0;


-- ── Étape 3 : Donner les droits ───────────────────────────────────
GRANT ALL PRIVILEGES ON DATABASE izzy_db TO izzy_user;


-- ── Étape 4 : Se connecter à la base (dans psql) ─────────────────
-- \c izzy_db izzy_user


-- ══════════════════════════════════════════════════════════════════
-- Les tables sont créées automatiquement par SQLAlchemy au démarrage
-- de l'application (init_db() dans database.py)
-- ══════════════════════════════════════════════════════════════════


-- ── Commandes utiles PostgreSQL ───────────────────────────────────

-- Lister les bases de données
-- \l

-- Lister les tables
-- \dt

-- Voir le contenu des offres
-- SELECT id, category, is_active, LEFT(content, 60) FROM offers LIMIT 10;

-- Voir le prompt
-- SELECT name, LEFT(content, 100) FROM prompts;

-- Compter les conversations
-- SELECT session_id, COUNT(*) FROM conversations GROUP BY session_id;

-- Supprimer toutes les données (reset complet)
-- TRUNCATE offers, prompts, conversations, embedding_cache RESTART IDENTITY CASCADE;
