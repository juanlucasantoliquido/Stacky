from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import config

Path("data").mkdir(exist_ok=True)

engine = create_engine(
    config.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from models import AgentExecution, ExecutionLog, PackRun, Ticket, User  # noqa: F401
    from services.output_cache import OutputCache  # noqa: F401  (FA-31)
    from services.anti_patterns import AntiPattern  # noqa: F401  (FA-11)
    from services.webhooks import Webhook  # noqa: F401  (FA-52)
    from services.decisions import Decision  # noqa: F401  (FA-13)
    from services.translator import TranslationCache  # noqa: F401  (FA-22)
    from services.glossary_builder import GlossaryEntry, GlossaryCandidate  # noqa: F401  (FA-15)
    from services.drift_detector import DriftAlert  # noqa: F401  (FA-16)
    from services.audit_chain import AuditEntry  # noqa: F401  (FA-39)
    from services.constraints import ProjectConstraint  # noqa: F401  (FA-08)
    from services.style_memory import UserStyleProfile  # noqa: F401  (FA-10)
    from services.speculative import SpecExecution  # noqa: F401  (FA-36)
    from services.egress_policies import EgressPolicy  # noqa: F401  (FA-41)
    from services.macros import Macro  # noqa: F401  (FA-51)
    from services.embeddings import ExecutionEmbedding  # noqa: F401  (FA-01)

    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
