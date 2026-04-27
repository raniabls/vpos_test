import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:rania@localhost:5432/izzy"
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
#  TABLE 1 — OFFRES
# ══════════════════════════════
class Offer(Base):
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
#  TABLE 2 — FAQ  (NOUVEAU)
# ══════════════════════════════
class FAQ(Base):
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
#  TABLE 3 — SERVICES  (NOUVEAU)
# ══════════════════════════════
class Service(Base):
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
#  TABLE 6 — EMBEDDING CACHE
# ══════════════════════════════
class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"
    id           = Column(Integer, primary_key=True)
    content_hash = Column(String(32), nullable=False)
    faiss_path   = Column(String(255), nullable=False)
    offer_count  = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)

# ══════════════════════════════
#  PROMPT PAR DÉFAUT
# ══════════════════════════════
DEFAULT_PROMPT = """You are Izzy, a warm and professional virtual assistant for Djezzy Algeria.

⚠️ CRITICAL : The user is speaking {language_name}. You MUST reply in {language_name} ONLY.
No matter what language the context or data is in, your reply must be in {language_name}.

ABSOLUTE RULES:
2. Never repeat information already given in this conversation.
3. Speak naturally like a human, never copy raw data.
4. Be concise. End with ONE short useful question.
5. For a specific price, ONLY show offers at that EXACT price.
6. Never mention file names or data sources.
7. ONLY use context below — NEVER invent anything not written here.
8. Use conversation history for contextual, coherent answers.
9. NEVER use bullet points, dashes or numbered lists.
   Write in natural flowing sentences only.

Available information:
{context}"""

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables PostgreSQL créées (offers, faq, services, prompts, conversations, embedding_cache)")
    except Exception as e:
        print(f"❌ Erreur connexion PostgreSQL : {e}")
        raise

    db = SessionLocal()
    try:
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