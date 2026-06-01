from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import config
from runtime_paths import data_dir

data_dir().mkdir(parents=True, exist_ok=True)

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
    from models import AgentExecution, ExecutionLog, PackRun, SystemLog, Ticket, User, TicketStateHistory  # noqa: F401
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
    from services.ado_publisher import AgentHtmlPublish  # noqa: F401
    from services.ado_write_outbox import AdoWriteOperation  # noqa: F401  (Fase 2 — outbox ADO)
    from services.ticket_status import TicketStatusEvent  # noqa: F401  (ticket state tracking)
    from services.pm.models import (  # noqa: F401  (PM Intelligence Suite v2 — Fase 1 + 2)
        PmSprintSnapshot,
        PmRiskItem,
        PmWorkItemComment,
        PmAiUsage,
        PmAiRecommendation,
    )
    from services.docs_rag import DocChunk  # noqa: F401  (P1.1 — tabla docs_index)

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
        ("tickets", "external_id", "INTEGER"),
        ("tickets", "stacky_project_name", "VARCHAR(80)"),
        ("tickets", "tracker_type", "VARCHAR(40)"),
        # P6: campo de asignacion ADO en tickets
        ("tickets", "assigned_to_ado", "VARCHAR(200)"),
        ("ticket_state_history", "stacky_project_name", "VARCHAR(80)"),
        # P6: campos de perfil ADO en usuarios
        ("users", "ado_unique_name", "VARCHAR(200)"),
        ("users", "ado_display_name", "VARCHAR(200)"),
        ("users", "skills_json", "TEXT"),
        ("users", "area_paths_json", "TEXT"),
        ("users", "max_active_tickets", "INTEGER DEFAULT 5"),
        # Fase 1 plan creacion-tareas-comentarios-100-efectiva (2026-05-29):
        # Mapeo explicito de columnas operativas en agent_executions que antes
        # se seteaban como atributos dinamicos y no persistian al cerrar la sesion.
        ("agent_executions", "html_output_path", "VARCHAR(500)"),
        ("agent_executions", "completion_source", "VARCHAR(40)"),
        # Fase 1: trazabilidad de la publicacion ADO del comentario para
        # verificacion y reconciliacion idempotente.
        ("agent_html_publish", "comment_id", "INTEGER"),
        ("agent_html_publish", "marker", "VARCHAR(200)"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in migrations:
            try:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    conn.commit()
            except Exception:
                pass
        _backfill_multi_project_ticket_columns(conn)
        _rebuild_tickets_table_if_needed(conn)
        _backfill_ticket_state_history(conn)


def _backfill_multi_project_ticket_columns(conn) -> None:
    from project_manager import find_project_for_tracker

    try:
        rows = conn.execute(
            text(
                "SELECT id, ado_id, project, external_id, stacky_project_name, tracker_type "
                "FROM tickets"
            )
        ).fetchall()
    except Exception:
        return

    for row in rows:
        tracker_project = row[2]
        stacky_project_name = row[4]
        tracker_type = row[5]
        if stacky_project_name and tracker_type and row[3] is not None:
            continue
        found_name, found_cfg = find_project_for_tracker(tracker_project or "")
        resolved_stacky = (found_name or tracker_project or "").strip() or None
        resolved_tracker_type = (
            ((found_cfg or {}).get("issue_tracker") or {}).get("type") or tracker_type or "azure_devops"
        )
        conn.execute(
            text(
                "UPDATE tickets "
                "SET external_id = COALESCE(external_id, ado_id), "
                "    stacky_project_name = COALESCE(stacky_project_name, :stacky_project_name), "
                "    tracker_type = COALESCE(tracker_type, :tracker_type) "
                "WHERE id = :ticket_id"
            ),
            {
                "stacky_project_name": resolved_stacky,
                "tracker_type": resolved_tracker_type,
                "ticket_id": row[0],
            },
        )
    conn.commit()


def _rebuild_tickets_table_if_needed(conn) -> None:
    try:
        indexes = conn.execute(text("PRAGMA index_list(tickets)")).fetchall()
    except Exception:
        return

    index_names = {row[1] for row in indexes}
    needs_rebuild = "sqlite_autoindex_tickets_1" in index_names
    needs_rebuild = needs_rebuild or "ux_tickets_stacky_tracker_external" not in index_names
    if not needs_rebuild:
        return

    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(
        text(
            """
            CREATE TABLE tickets__new (
                id INTEGER NOT NULL PRIMARY KEY,
                ado_id INTEGER NOT NULL,
                external_id INTEGER,
                project VARCHAR(80) NOT NULL,
                stacky_project_name VARCHAR(80),
                tracker_type VARCHAR(40),
                title VARCHAR(500) NOT NULL,
                description TEXT,
                ado_state VARCHAR(40),
                ado_url VARCHAR(400),
                priority INTEGER,
                work_item_type VARCHAR(40),
                parent_ado_id INTEGER,
                last_synced_at DATETIME,
                created_at DATETIME NOT NULL,
                stacky_status VARCHAR(30),
                assigned_to_ado VARCHAR(200)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO tickets__new (
                id, ado_id, external_id, project, stacky_project_name, tracker_type,
                title, description, ado_state, ado_url, priority, work_item_type,
                parent_ado_id, last_synced_at, created_at, stacky_status, assigned_to_ado
            )
            SELECT
                id,
                ado_id,
                COALESCE(external_id, ado_id),
                project,
                COALESCE(stacky_project_name, project),
                COALESCE(tracker_type, 'azure_devops'),
                title,
                description,
                ado_state,
                ado_url,
                priority,
                work_item_type,
                parent_ado_id,
                last_synced_at,
                created_at,
                stacky_status,
                assigned_to_ado
            FROM tickets
            """
        )
    )
    conn.execute(text("DROP TABLE tickets"))
    conn.execute(text("ALTER TABLE tickets__new RENAME TO tickets"))
    conn.execute(text("CREATE INDEX ix_tickets_project_state ON tickets(project, ado_state)"))
    conn.execute(text("CREATE INDEX ix_tickets_stacky_project ON tickets(stacky_project_name)"))
    conn.execute(
        text(
            "CREATE UNIQUE INDEX ux_tickets_stacky_tracker_external "
            "ON tickets(stacky_project_name, tracker_type, external_id)"
        )
    )
    conn.execute(text("PRAGMA foreign_keys=ON"))
    conn.commit()


def _backfill_ticket_state_history(conn) -> None:
    try:
        conn.execute(
            text(
                """
                UPDATE ticket_state_history
                SET stacky_project_name = (
                    SELECT tickets.stacky_project_name
                    FROM tickets
                    WHERE tickets.id = ticket_state_history.ticket_id
                )
                WHERE stacky_project_name IS NULL
                """
            )
        )
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
