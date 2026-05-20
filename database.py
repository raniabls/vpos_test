import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Float
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:rania@localhost:5432/izzy_chroma"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=5, max_overflow=10, pool_pre_ping=True, echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ══════════════════════════════
#  MIXIN — colonnes numériques
#  Partagées par Offer, FAQ, Service
#  pour permettre le SQL search
# ══════════════════════════════
class NumericMixin:
    prix        = Column(Integer,  default=0)
    prix_remise = Column(Integer,  default=0)
    data_go     = Column(Float,    default=0.0)
    illimite    = Column(Boolean,  default=False)
    duree_j     = Column(Integer,  default=30)
    reseau      = Column(String(10), default="4g")
    type_offre  = Column(String(30), default="prepaye")
    roaming     = Column(Boolean,  default=False)
    nom_offre   = Column(String(200), default="")


# ══════════════════════════════
#  TABLE 1 — OFFRES
# ══════════════════════════════
class Offer(NumericMixin, Base):
    __tablename__ = "offers"
    id            = Column(Integer, primary_key=True, index=True)
    content       = Column(Text, nullable=False, unique=True)
    category      = Column(String(100), default="general")
    is_active     = Column(Boolean, default=True)
    needs_reindex = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "content": self.content,
                "category": self.category, "active": self.is_active}

# ══════════════════════════════
#  TABLE 2 — FAQ
# ══════════════════════════════
class FAQ(NumericMixin, Base):
    __tablename__ = "faq"
    id            = Column(Integer, primary_key=True, index=True)
    content       = Column(Text, nullable=False, unique=True)
    category      = Column(String(100), default="faq")
    is_active     = Column(Boolean, default=True)
    needs_reindex = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "content": self.content,
                "category": self.category, "active": self.is_active}

# ══════════════════════════════
#  TABLE 3 — SERVICES
# ══════════════════════════════
class Service(NumericMixin, Base):
    __tablename__ = "services"
    id            = Column(Integer, primary_key=True, index=True)
    content       = Column(Text, nullable=False, unique=True)
    category      = Column(String(100), default="service")
    is_active     = Column(Boolean, default=True)
    needs_reindex = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "content": self.content,
                "category": self.category, "active": self.is_active}

# ══════════════════════════════
#  TABLE 4 — PROMPTS
# ══════════════════════════════
class Prompt(Base):
    __tablename__ = "prompts"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), unique=True, nullable=False)
    content     = Column(Text, nullable=False)
    description = Column(String(255), default="")
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ══════════════════════════════
#  TABLE 5 — CONVERSATIONS
# ══════════════════════════════
class Conversation(Base):
    __tablename__ = "conversations"
    id         = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False, index=True)
    role       = Column(String(20), nullable=False)
    content    = Column(Text, nullable=False)
    lang       = Column(String(5), default="fr")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"role": self.role, "content": self.content}

# ══════════════════════════════
#  PROMPT PAR DÉFAUT
# ══════════════════════════════
DEFAULT_PROMPT = """You are Izzy, a warm and professional virtual assistant for Djezzy Algeria.

⚠️ CRITICAL : The user is speaking {language_name}. You MUST reply in {language_name} ONLY.

ABSOLUTE RULES:
1. Never repeat information already given in this conversation.
2. Speak naturally like a human, never copy raw data.
3. Be concise. End with ONE short useful question only if needed.
4. NEVER use bullet points, dashes or numbered lists. Plain text only.
5. ONLY use context below — NEVER invent anything not written here.

Available information:
{context}"""


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables PostgreSQL créées")
    except Exception as e:
        print(f"❌ Erreur connexion PostgreSQL : {e}")
        raise

    db = SessionLocal()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)

        # Ajouter les nouvelles colonnes si elles n'existent pas (migration douce)
        for table_name in ["offers", "faq", "services"]:
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
            new_cols = {
                "prix": "INTEGER DEFAULT 0",
                "prix_remise": "INTEGER DEFAULT 0",
                "data_go": "FLOAT DEFAULT 0.0",
                "illimite": "BOOLEAN DEFAULT FALSE",
                "duree_j": "INTEGER DEFAULT 30",
                "reseau": "VARCHAR(10) DEFAULT '4g'",
                "type_offre": "VARCHAR(30) DEFAULT 'prepaye'",
                "roaming": "BOOLEAN DEFAULT FALSE",
                "nom_offre": "VARCHAR(200) DEFAULT ''",
            }
            from sqlalchemy import text
            with engine.connect() as conn:
                for col_name, col_def in new_cols.items():
                    if col_name not in existing_cols:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                        ))
                        print(f"  ➕ Colonne '{col_name}' ajoutée à '{table_name}'")
                conn.commit()

        from database import Prompt
        if db.query(Prompt).count() == 0:
            db.add(Prompt(
                name="system_prompt",
                content=DEFAULT_PROMPT,
                description="Prompt principal d'Izzy"
            ))
            db.commit()
            print("✅ Prompt par défaut inséré")

    finally:
        db.close()

    print("✅ Base de données PostgreSQL initialisée")