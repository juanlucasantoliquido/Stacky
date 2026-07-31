import logging
import threading
import time
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import config
from runtime_paths import data_dir

logger = logging.getLogger("stacky.db")

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


# ── Plan 253 F2 — concurrencia SQLite ────────────────────────────────────────
# Estado EFECTIVO, leido de vuelta del motor. Lo consume el guard de
# /api/diag/health. Nunca se "asume": siempre se relee.
_CONCURRENCY_STATE: dict = {
    "journal_mode_effective": None,
    "wal_status": "unknown",     # ok | in_memory | rejected | disabled | not_sqlite
    "busy_timeout_ms": None,
    "synchronous": None,
    "last_applied_at": None,
}
_IS_SQLITE = _effective_url.startswith("sqlite")
_IS_MEMORY_DB = "mode=memory" in _effective_url or _effective_url.endswith(":memory:")
if not _IS_SQLITE:
    _CONCURRENCY_STATE["wal_status"] = "not_sqlite"


def apply_sqlite_pragmas(dbapi_conn) -> dict:
    """Plan 253 F2 — aplica los PRAGMA de concurrencia a UNA conexion sqlite3 cruda.

    Devuelve el estado EFECTIVO releido del motor (no lo que pedimos).
    NUNCA levanta: cualquier fallo degrada al comportamiento de hoy.
    """
    state = {"journal_mode_effective": None, "wal_status": "disabled",
             "busy_timeout_ms": None, "synchronous": None,
             "last_applied_at": time.time()}
    cur = dbapi_conn.cursor()
    try:
        if config.STACKY_SQLITE_WAL_ENABLED:
            cur.execute("PRAGMA journal_mode=WAL")
            mode = str((cur.fetchone() or [""])[0]).lower()
            state["journal_mode_effective"] = mode
            if mode == "wal":
                state["wal_status"] = "ok"
            elif mode == "memory":
                # Base en memoria (tests / DB compartida en RAM). NO es un rechazo
                # del filesystem: WAL no aplica por definicion. Medido: devuelve 'memory'.
                state["wal_status"] = "in_memory"
            else:
                state["wal_status"] = "rejected"
        else:
            cur.execute("PRAGMA journal_mode")
            state["journal_mode_effective"] = str((cur.fetchone() or [""])[0]).lower()
            state["wal_status"] = "disabled"

        cur.execute(f"PRAGMA busy_timeout={int(config.STACKY_SQLITE_BUSY_TIMEOUT_MS)}")
        cur.execute("PRAGMA busy_timeout")
        state["busy_timeout_ms"] = (cur.fetchone() or [None])[0]

        if config.STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED:
            cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA synchronous")
        state["synchronous"] = (cur.fetchone() or [None])[0]
    except Exception:  # noqa: BLE001 — la concurrencia jamas impide abrir la base
        logger.warning("sqlite: no se pudieron aplicar los PRAGMA de concurrencia", exc_info=True)
    finally:
        cur.close()
    return state


if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _rec):
        """Plan 253 F2 — PRAGMA en TODA conexion nueva del pool."""
        st = apply_sqlite_pragmas(dbapi_conn)
        _CONCURRENCY_STATE.update(st)
        if st["wal_status"] == "rejected":
            from services.log_throttle import log_throttled
            log_throttled(
                "db.wal_rejected", logger, logging.WARNING,
                "sqlite: el sistema de archivos rechazo WAL (journal_mode=%s); "
                "se sigue en ese modo con espera por lock de %d ms",
                st["journal_mode_effective"], int(config.STACKY_SQLITE_BUSY_TIMEOUT_MS),
                min_interval_s=300.0,
            )


def sqlite_concurrency_state() -> dict:
    """Plan 253 F2 — copia del estado efectivo, para el guard de salud."""
    return dict(_CONCURRENCY_STATE)


# ── Plan 253 F3 — barrera de ESCRITURAS DE ARRANQUE (no de esquema) ──────────
_STARTUP_WRITES_DONE = threading.Event()
_BARRIER_ARMED = threading.Event()


def arm_startup_writes() -> None:
    """Plan 253 F3 — declara que empieza la fase de escritura del arranque.

    Se llama UNA vez por create_app(). Es idempotente y re-armable: si
    create_app() corre dos veces (medido: pasa), la segunda vuelve a cerrar la
    barrera mientras el segundo arranque escribe. Eso es lo correcto.
    """
    _BARRIER_ARMED.set()
    _STARTUP_WRITES_DONE.clear()


def mark_startup_writes_done() -> None:
    """Plan 253 F3 — libera la barrera. Va SIEMPRE en un finally."""
    _STARTUP_WRITES_DONE.set()


def wait_for_startup_writes(timeout_s: float = 30.0) -> bool:
    """Plan 253 F3 — bloquea hasta que la fase de escritura del arranque termino.

    Devuelve True si se puede trabajar, False si expiro el timeout.
    NUNCA levanta. Si la barrera nunca se armo (proceso empaquetado sin
    create_app, scan ad-hoc del panel de diagnostico, tests que instancian el
    watcher a mano) devuelve True INMEDIATAMENTE: sin armado no hay escritor
    de arranque contra el cual esperar. Esto elimina cualquier riesgo de que un
    daemon quede esperando 30 s por una barrera que nadie va a abrir.
    """
    if not _BARRIER_ARMED.is_set():
        return True
    if timeout_s <= 0:
        return _STARTUP_WRITES_DONE.is_set()
    return _STARTUP_WRITES_DONE.wait(timeout=timeout_s)


def startup_writes_state() -> dict:
    """Plan 253 F3 — para el guard de salud."""
    return {"armed": _BARRIER_ARMED.is_set(), "done": _STARTUP_WRITES_DONE.is_set()}


# ── Plan 253 F4 — reintento por UNIDAD DE TRABAJO ────────────────────────────
_LOCK_MARKERS = ("database is locked", "database table is locked")
_LOCK_STATS = {"retried": 0, "recovered": 0, "exhausted": 0}
_LOCK_STATS_LOCK = threading.Lock()


def lock_stats() -> dict:
    """Plan 253 F4 — contadores acumulados, para el guard de salud."""
    with _LOCK_STATS_LOCK:
        return dict(_LOCK_STATS)


def run_with_retry(fn, *, attempts: int = 3, base_delay_s: float = 0.25, label: str = ""):
    """Plan 253 F4 — reintenta una UNIDAD DE TRABAJO COMPLETA ante lock de SQLite.

    `fn` DEBE abrir su propia sesion/transaccion en cada invocacion (tipicamente
    un `with session_scope() as session:` adentro). PROHIBIDO pasarle una lambda
    que use una Session ya abierta: tras un OperationalError esa Session queda
    con la transaccion abortada y cerrada por el finally de session_scope.

    Reintenta SOLO si es OperationalError cuyo mensaje contiene un marcador de
    lock. Cualquier otra excepcion se re-lanza en el primer intento (no se
    enmascaran bugs). Tras agotar los intentos, re-lanza la ultima.
    Con la flag apagada, ejecuta fn() una sola vez.
    """
    from sqlalchemy.exc import OperationalError
    if not config.STACKY_SQLITE_LOCK_RETRY_ENABLED:
        return fn()
    last = None
    for i in range(attempts):
        try:
            result = fn()
            if i > 0:
                with _LOCK_STATS_LOCK:
                    _LOCK_STATS["recovered"] += 1
            return result
        except OperationalError as exc:
            msg = str(getattr(exc, "orig", None) or exc).lower()
            if not any(m in msg for m in _LOCK_MARKERS):
                raise
            last = exc
            if i < attempts - 1:
                with _LOCK_STATS_LOCK:
                    _LOCK_STATS["retried"] += 1
                time.sleep(base_delay_s * (2 ** i))   # 0.25s, 0.5s
                logger.warning("db lock en %s — reintento %d/%d",
                               label or "operacion", i + 2, attempts)
    with _LOCK_STATS_LOCK:
        _LOCK_STATS["exhausted"] += 1
    raise last


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
    from services.publish_ledger import PublishLedgerEntry  # noqa: F401  (Plan 153 — ledger publicacion)
    from services.ticket_status import TicketStatusEvent  # noqa: F401  (ticket state tracking)
    from services.pm.models import (  # noqa: F401  (PM Intelligence Suite v2 — Fase 1 + 2)
        PmSprintSnapshot,
        PmRiskItem,
        PmWorkItemComment,
        PmAiUsage,
        PmAiRecommendation,
    )
    from services.docs_rag import DocChunk  # noqa: F401  (P1.1 — tabla docs_index)
    from services.memory_store import (  # noqa: F401  (memoria colaborativa local)
        StackyMemoryObservation,
        StackyMemoryRelation,
    )
    from services.memory_validator import (  # noqa: F401  (memoria colaborativa Fase D)
        StackyMemoryFinding,
        StackyMemoryValidationRun,
    )
    from services.memory_git_sync import (  # noqa: F401  (memoria colaborativa Fase E)
        StackyMemorySyncChunk,
        StackyMemorySyncOutbox,
    )
    import services.ci_inference_cache  # noqa: F401  (Plan 71 — caché CI agnóstico)

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
        # Plan 277 F4 — clasificacion local de jerarquia (GitLab sin etiquetas).
        # ADITIVO e idempotente. OJO: `_rebuild_tickets_table_if_needed` (mas abajo)
        # tiene la lista de columnas HARDCODEADA y corre despues de este loop; si
        # una columna nueva no se agrega ALLA TAMBIEN, el ALTER la crea y el rebuild
        # la borra en silencio junto con el dato del operador.
        ("tickets", "local_work_item_type", "VARCHAR(40)"),
        ("tickets", "local_parent_iid", "INTEGER"),
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
        ("webhooks", "format", "VARCHAR(20) DEFAULT 'raw'"),
        # M1.1 — Directiva como ciudadano de primera clase (add-only).
        ("stacky_memory_observations", "enforcement", "VARCHAR(12)"),
        ("stacky_memory_observations", "priority", "INTEGER DEFAULT 0"),
        ("stacky_memory_observations", "applies_to_json", "TEXT"),
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
        _ensure_agent_html_publish_indexes(conn)


def _ensure_agent_html_publish_indexes(conn) -> None:
    statements = [
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_agent_html_publish_execution_sha "
            "ON agent_html_publish (execution_id, html_sha256)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_agent_html_publish_ado_sha_status "
            "ON agent_html_publish (ado_id, html_sha256, status)"
        ),
    ]
    for statement in statements:
        try:
            conn.execute(text(statement))
            conn.commit()
        except Exception:
            pass


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
                assigned_to_ado VARCHAR(200),
                local_work_item_type VARCHAR(40),      -- Plan 277 F4
                local_parent_iid INTEGER               -- Plan 277 F4
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
                parent_ado_id, last_synced_at, created_at, stacky_status, assigned_to_ado,
                local_work_item_type, local_parent_iid
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
                assigned_to_ado,
                -- Plan 277 F4: sin estas dos, el DROP TABLE de abajo borraba la
                -- clasificacion manual del operador sin error y sin log.
                local_work_item_type,
                local_parent_iid
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
