from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import config

Path("data").mkdir(exist_ok=True)

# When DATABASE_URL is sqlite:///:memory: (test environments), each new
# connection normally gets its own empty database — tables created by one
# connection would be invisible in background threads (e.g. stacky_logger
# writer thread).  We remap it to a named shared-cache in-memory database
# so that all connections/threads see the same data while each still gets
# its own connection (no StaticPool locking issues).
_effective_url = config.DATABASE_URL
_connect_args: dict = {}

if config.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    if config.DATABASE_URL == "sqlite:///:memory:":
        _effective_url = (
            "sqlite:///file:stacky_shared_mem?mode=memory&cache=shared&uri=true"
        )

engine = create_engine(
    _effective_url,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from models import AgentExecution, ExecutionLog, PackRun, SystemLog, Ticket, User  # noqa: F401
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
    from services.ado_pipeline_inference import PipelineInferenceCache  # noqa: F401
    from services.ticket_status import TicketStatusEvent  # noqa: F401  (ticket state tracking)

    Base.metadata.create_all(engine)
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    """SQLite-safe migration: adds columns that may not exist in older DB files."""
    if not config.DATABASE_URL.startswith("sqlite"):
        return
    migrations = [
        ("tickets", "work_item_type", "VARCHAR(40)"),
        ("tickets", "parent_ado_id", "INTEGER"),
        ("tickets", "stacky_status", "VARCHAR(30)"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in migrations:
            try:
                rows = conn.execute(
                    __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
                ).fetchall()
                existing = {r[1] for r in rows}
                if col not in existing:
                    conn.execute(__import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                    ))
                    conn.commit()
            except Exception:
                pass


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
