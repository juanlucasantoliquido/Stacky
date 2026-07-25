"""tools/migrar_mantis_gitlab/__main__.py — Plan 217 F9a (CLI, último batch de código).

Orquesta TODOS los módulos de los batches anteriores (F1..F8) detrás de 6
subcomandos: `validate | plan | execute | resume | verify | report`. Este es
el ÚNICO módulo del tool que:
  - decide qué adapter de origen instanciar (`api`/`scraping`/`auto`, §8.1
    del plan),
  - implementa el prompt interactivo real de credenciales (`secret_backend.
    SecretPromptRequired` señala que hace falta, pero el prompt en sí vive
    acá, tal como documenta `secret_backend.py`),
  - aplica el gate HITL de `execute` (§13, C8: un scheduler/cron NUNCA debe
    invocar `execute --confirmed` desatendido).

Invocación (desde `Stacky Agents/backend/`, mismo cwd que el resto de la
suite):
    python -m tools.migrar_mantis_gitlab <subcomando> --config <archivo> [flags]

Diseño para testeo (Batch 6, test de integración dry-run): `_build_origin_adapter`
es una función de módulo independiente, pensada para ser monkeypateada por
los tests (inyectar un adapter FAKE sin tocar credenciales/red), en vez de
estar inline dentro de cada `cmd_*`.
"""
from __future__ import annotations

import argparse
import getpass
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from services import secrets_store
from services.mantis_client import MantisClient

from .adapters.api_adapter import MantisApiReadAdapter
from .adapters.scraping_adapter import MantisWebScrapingReadAdapter
from .config_loader import ConfigLoadError, load_config
from .config_schema import (
    ConfigValidationError,
    FieldMappingConfig,
    MigrationConfig,
    UserMappingConfig,
)
from .destination_writer import (
    DestinationMismatchError,
    DryRunGitLabWriter,
    GitLabDestinationWriter,
    assert_target_matches,
)
from .mapping.priority_severity_map import UnmappedPriorityError, map_priority
from .mapping.status_map import map_status
from .migrator_mg_core import compute_plan_hash, plan_migration
from .migrator_mg_executor import (
    MgExecutionResult,
    execute_migration,
    hydrate_map_from_destination_mg,
    resume_migration,
)
from .migrator_mg_links import migrate_relationships
from .migrator_mg_map import (
    get_full_mapping,
    get_plan_snapshot,
    open_map_db,
    save_plan_snapshot,
)
from .migrator_mg_report import generate_report
from .migrator_mg_verify import MgVerificationResult, verify_migration
from . import secret_backend

logger = logging.getLogger("migrar_mantis_gitlab.cli")

_SENSITIVE_FIELDS = frozenset({"password", "token"})


# ─────────────────────────────────────────────────────────────────────────
# Helpers de config/credenciales/rutas derivadas
# ─────────────────────────────────────────────────────────────────────────


def _load_config_or_exit(path: str) -> MigrationConfig:
    try:
        return load_config(path)
    except (ConfigLoadError, ConfigValidationError) as exc:
        print(f"[migrar_mantis_gitlab] ERROR de config: {exc}")
        raise SystemExit(2) from exc


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (value or "").strip("/")) or "proyecto"


def _resolve_map_db_path(config: MigrationConfig, *, dry_run: bool = False) -> str:
    """Deriva la ruta del SQLite propio del tool (§11 del plan) a partir de
    `options.incremental.checkpoint_file` (mismo directorio) o, si no está
    seteado, `run_state/<slug>_map.sqlite3` relativo al cwd.

    `dry_run` se acepta por compatibilidad de firma pero NO cambia la ruta:
    el simulacro trabaja sobre una COPIA EN MEMORIA de esta misma base (ver
    `_open_map_db_for_run`), así arranca del mismo estado real —y por lo
    tanto calcula el mismo hash de plan— sin escribir nada a disco."""
    checkpoint_file = config.options.incremental.checkpoint_file
    slug = _slugify(config.destination.project_path)
    parent = Path(checkpoint_file).parent if checkpoint_file else Path("run_state")
    return str(parent / f"{slug}_map.sqlite3")


def _open_map_db_for_run(map_db_path: str, *, dry_run: bool) -> sqlite3.Connection:
    """Abre el SQLite del mapeo para una corrida.

    En SIMULACRO devuelve una copia EN MEMORIA de la base real: el ensayo
    lee el mismo estado de partida (mismo plan, mismo hash) pero sus
    escrituras se descartan al terminar. Antes el dry-run escribía en la
    base real y dejaba los issues marcados `done` con iids falsos
    (`dryrun-N`), de modo que la migración REAL posterior los salteaba por
    idempotencia: el ensayo impedía la migración de verdad."""
    conn = open_map_db(map_db_path)
    if not dry_run:
        return conn
    memoria = sqlite3.connect(":memory:")
    memoria.row_factory = sqlite3.Row
    conn.backup(memoria)
    conn.close()
    return memoria


def _resolve_checkpoint_path(config: MigrationConfig) -> str:
    return config.options.incremental.checkpoint_file or str(
        Path("run_state") / f"{_slugify(config.destination.project_path)}_checkpoint.json"
    )


def _persist_dpapi_secret(auth_file: str, field: str, value: str) -> None:
    """Persiste `field` cifrado (DPAPI) en `auth_file`, creando el archivo/
    directorio padre si hace falta. Usa `format_field="token_format"` — el
    MISMO nombre hardcodeado que `secret_backend._resolve_dpapi` usa para
    leer (`secret_backend.py`, batch anterior, NO modificado en este batch).
    No es una colisión real: dentro de un mismo `auth_file` todos los campos
    resueltos por este CLI se persisten siempre en formato DPAPI, así que
    compartir la bandera de formato es coherente (no mezcla texto plano con
    cifrado bajo la misma bandera)."""
    payload = secrets_store.load_json_file(auth_file)
    secrets_store.set_encrypted_secret(payload, field, value, format_field="token_format")
    secrets_store.write_json_file(auth_file, payload)


def _prompt_and_resolve_secret(auth_file: str, field: str, backend: str) -> str:
    """Resuelve `field` desde `auth_file` vía `secret_backend.resolve_secret`;
    si señala `SecretPromptRequired`, implementa el prompt interactivo REAL
    (contrato explícito de `secret_backend.py`: "esa implementación vive en
    el CLI, no acá"). `getpass.getpass()` para campos sensibles
    (password/token), `input()` para el resto (username)."""
    try:
        return secret_backend.resolve_secret(auth_file, field, backend)
    except secret_backend.SecretPromptRequired:
        pass

    prompt = f"[migrar_mantis_gitlab] Ingresá '{field}' ({auth_file}): "
    value = getpass.getpass(prompt) if field in _SENSITIVE_FIELDS else input(prompt)

    effective_backend = backend
    if backend == "auto":
        effective_backend = "dpapi" if sys.platform == "win32" else "env"

    if effective_backend == "dpapi":
        _persist_dpapi_secret(auth_file, field, value)
        print(
            f"[migrar_mantis_gitlab] '{field}' persistido cifrado (DPAPI) en {auth_file}; "
            "no se volverá a pedir."
        )
    else:
        print(
            f"[migrar_mantis_gitlab] '{field}' usado SOLO en memoria para esta corrida "
            f"(secret_backend={effective_backend!r}); NO se persiste (C3 del Plan 217)."
        )
    return value


def _field_mapping_to_dict(fm: FieldMappingConfig) -> dict:
    """Reconstruye el dict crudo (forma JSON de `field_mapping`, §4 del
    plan) que esperan `migrator_mg_core._build_payload` y `mapping/*.py` a
    partir del `FieldMappingConfig` ya validado/tipado."""
    status_dict: dict = {
        key: {"gitlab_state": entry.gitlab_state, "label": entry.label}
        for key, entry in fm.status.entries.items()
    }
    status_dict["_unmapped_fallback"] = {
        "gitlab_state": fm.status.unmapped_fallback.gitlab_state,
        "label": fm.status.unmapped_fallback.label,
    }
    return {
        "status": status_dict,
        "priority": {"label_prefix": fm.priority.label_prefix, "scale": dict(fm.priority.scale)},
        "severity": {"label_prefix": fm.severity.label_prefix},
        "category": {"label_prefix": fm.category.label_prefix},
        "tags": {"label_prefix": fm.tags.label_prefix},
        "version": {
            "target_version_as": fm.version.target_version_as,
            "fixed_in_version_as": fm.version.fixed_in_version_as,
            "affects_version_as": fm.version.affects_version_as,
        },
        "relationships": dict(fm.relationships),
        "custom_fields": {"mode": fm.custom_fields.mode},
    }


def _user_mapping_to_dict(um: UserMappingConfig) -> dict:
    return {"default_fallback": um.default_fallback, "map": dict(um.map)}


def _build_verify_origin_issues(issues: "list[dict]", field_mapping_raw: dict) -> "list[dict]":
    """Adapta issues crudos de Mantis al shape que `migrator_mg_verify.
    verify_migration` espera para `origin_issues` (§8.2.4): `mantis_issue_id`,
    `title`, `expected_gitlab_state`, `expected_priority_label` — es decir,
    aplica el MISMO mapeo que ya usó `plan_migration`/`_build_payload`
    (responsabilidad de la orquestación, documentada en el propio módulo de
    verify: "Aplicar el mapeo es responsabilidad de la orquestación (F9)")."""
    status_cfg = field_mapping_raw["status"]
    priority_cfg = field_mapping_raw["priority"]
    out: list[dict] = []
    for issue in issues:
        gitlab_state, _, _ = map_status(issue.get("status", ""), status_cfg)
        expected_priority_label = None
        raw_priority = issue.get("priority")
        if raw_priority not in (None, ""):
            try:
                # Sin `int()`: el scraping entrega el NOMBRE de la prioridad
                # ("alta"/"high"). Con la conversión, `expected` quedaba en
                # None para TODO issue leído por scraping y `verify` marcaba
                # 20 "mismatches" contra labels que en realidad eran
                # correctos — ruido que tapaba hallazgos de verdad.
                expected_priority_label = map_priority(
                    raw_priority,
                    priority_cfg.get("scale") or {},
                    priority_cfg.get("label_prefix", "priority::"),
                )
            except (TypeError, ValueError, UnmappedPriorityError):
                expected_priority_label = None
        out.append(
            {
                "mantis_issue_id": str(issue.get("id") or issue.get("mantis_issue_id") or ""),
                "title": issue.get("summary", ""),
                "expected_gitlab_state": gitlab_state,
                "expected_priority_label": expected_priority_label,
            }
        )
    return out


def _check_unmapped_field_values(issues: "list[dict]", field_mapping: FieldMappingConfig) -> "list[str]":
    """§8.1.4 del plan: barrido previo de valores realmente presentes en los
    issues a migrar vs. lo cubierto por `field_mapping.status`/`.priority` —
    devuelve advertencias (nunca aborta), listando lo que caerá a
    `_unmapped_fallback`/sin label de prioridad."""
    status_cfg = {
        key: {"gitlab_state": e.gitlab_state, "label": e.label}
        for key, e in field_mapping.status.entries.items()
    }
    status_cfg["_unmapped_fallback"] = {
        "gitlab_state": field_mapping.status.unmapped_fallback.gitlab_state,
        "label": field_mapping.status.unmapped_fallback.label,
    }

    seen_status_unmapped: "set[str]" = set()
    seen_priority_unmapped: "set[str]" = set()
    for issue in issues:
        _, _, used_fallback = map_status(issue.get("status", ""), status_cfg)
        if used_fallback:
            seen_status_unmapped.add(str(issue.get("status")))

        raw_priority = issue.get("priority")
        if raw_priority not in (None, ""):
            try:
                # Sin `int()`: el scraping entrega el NOMBRE de la prioridad
                # ("alta"/"high"), no el ID numérico de la API REST.
                # `map_priority` resuelve ambos (ver `resolve_priority_id`).
                map_priority(
                    raw_priority, field_mapping.priority.scale, field_mapping.priority.label_prefix
                )
            except (TypeError, ValueError, UnmappedPriorityError):
                seen_priority_unmapped.add(str(raw_priority))

    warnings: list[str] = []
    if seen_status_unmapped:
        warnings.append(
            f"{len(seen_status_unmapped)} valor(es) de status sin mapeo explícito (caen a "
            f"_unmapped_fallback): {sorted(seen_status_unmapped)}"
        )
    if seen_priority_unmapped:
        warnings.append(
            f"{len(seen_priority_unmapped)} valor(es) de priority sin mapeo/escala (se omite "
            f"el label de prioridad): {sorted(seen_priority_unmapped)}"
        )
    return warnings


def _check_already_fully_migrated(conn, config: MigrationConfig, *, force: bool) -> "Optional[str]":
    """§8.1.7 del plan: evita re-migrar por error un proyecto ya completo.
    Devuelve un mensaje de error si corresponde abortar, o `None` si está OK
    seguir (proyecto nuevo, migración parcial, o `--force` explícito)."""
    mapping_rows = get_full_mapping(conn, config.destination.project_path)
    if not mapping_rows:
        return None
    total = len(mapping_rows)
    done = len([r for r in mapping_rows if r.get("status") == "done"])
    if total > 0 and done == total and not force:
        return (
            f"El proyecto '{config.destination.project_path}' ya tiene una migración COMPLETA "
            f"registrada ({done}/{total} issues en estado 'done'). Si de verdad querés "
            "re-migrar, pasá --force explícito (§8.1.7 del Plan 217)."
        )
    return None


# ─────────────────────────────────────────────────────────────────────────
# Construcción del adapter de origen (Mantis) — inyectable en tests
# ─────────────────────────────────────────────────────────────────────────


def _build_api_adapter(origin) -> MantisApiReadAdapter:
    if len(origin.project_ids) > 1:
        print(
            "[migrar_mantis_gitlab] ADVERTENCIA: extraction_mode=api soporta un único "
            f"project_id (MantisApiReadAdapter envuelve un solo MantisClient); se usa el "
            f"primero de {origin.project_ids}. Para varios project_ids en un mismo run "
            "usá extraction_mode=scraping."
        )
    token = _prompt_and_resolve_secret(origin.auth.auth_file, "token", "auto")
    client = MantisClient(url=origin.base_url, project_id=origin.project_ids[0], token=token)
    return MantisApiReadAdapter(client)


def _build_scraping_adapter(origin) -> MantisWebScrapingReadAdapter:
    username = _prompt_and_resolve_secret(origin.auth.auth_file, "username", "auto")
    password = _prompt_and_resolve_secret(origin.auth.auth_file, "password", "auto")
    return MantisWebScrapingReadAdapter(
        origin.base_url,
        origin.project_ids,
        username,
        password,
        # §4: sin esto Mantis aplica el filtro guardado del usuario, que
        # oculta resueltos/cerrados (contra la instancia real: 11 de 52).
        include_resolved_closed=origin.include_resolved_closed,
    )


def _build_origin_adapter(config: MigrationConfig):
    """Instancia el adapter de origen según `origin.extraction_mode`
    (§8.1 del plan). Función de módulo independiente A PROPÓSITO — el test
    de integración dry-run (Batch 6) la monkeypatea para inyectar un fake
    sin credenciales/red."""
    origin = config.origin
    mode = origin.extraction_mode
    if mode == "api":
        return _build_api_adapter(origin)
    if mode == "scraping":
        return _build_scraping_adapter(origin)
    if mode == "auto":
        try:
            adapter = _build_api_adapter(origin)
            adapter.fetch_all_issues()  # probe liviano: no hay list_projects()/login dedicado
            return adapter
        except Exception as exc:  # noqa: BLE001 - fallback deliberado a scraping
            print(f"[migrar_mantis_gitlab] extraction_mode=auto: API no disponible ({exc}); usando scraping.")
            return _build_scraping_adapter(origin)
    raise ValueError(f"origin.extraction_mode desconocido: {mode!r} (válidos: api|scraping|auto)")


# ─────────────────────────────────────────────────────────────────────────
# Subcomandos
# ─────────────────────────────────────────────────────────────────────────


def cmd_validate(args: argparse.Namespace) -> int:
    config = _load_config_or_exit(args.config)
    print(f"[validate] Config cargado OK: {args.config}")

    try:
        origin_adapter = _build_origin_adapter(config)
    except Exception as exc:
        print(f"[validate] ERROR conectando al origen (Mantis): {exc}")
        return 1
    print("[validate] Conexión a origen (Mantis) OK.")

    try:
        token = _prompt_and_resolve_secret(
            config.destination.auth.auth_file, "token", config.destination.auth.secret_backend
        )
        writer = GitLabDestinationWriter(config.destination, token)
    except Exception as exc:
        print(f"[validate] ERROR conectando al destino (GitLab): {exc}")
        return 1

    try:
        assert_target_matches(writer, config.destination)
    except DestinationMismatchError as exc:
        print(f"[validate] ERROR (gate anti-destino-equivocado, §8.1.8): {exc}")
        return 1
    print(f"[validate] Destino (GitLab) OK: {writer.effective_target()}")

    # NOTA: el gate DURO de §8.1.7 ("proyecto ya migrado por completo") vive
    # SOLO en 'execute' sin --dry-run (la única operación que de verdad
    # podría re-crear todo por error) — 'validate' es diagnóstico, de
    # re-corrida siempre segura (p.ej. para confirmar credenciales antes de
    # una corrida incremental sobre un proyecto ya migrado), así que acá el
    # estado "ya migrado" es a lo sumo informativo, nunca bloqueante.
    map_db_path = _resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        mapping_rows = get_full_mapping(conn, config.destination.project_path)
        if mapping_rows and all(r.get("status") == "done" for r in mapping_rows):
            print(
                f"[validate] INFO (§8.1.7): el proyecto '{config.destination.project_path}' ya "
                f"tiene una migración completa registrada ({len(mapping_rows)} issues 'done'). "
                "'execute' sin --dry-run exigirá --force para re-migrar."
            )

        try:
            issues = origin_adapter.fetch_all_issues()
        except Exception as exc:
            print(f"[validate] ADVERTENCIA: no se pudo leer origen para validar field_mapping: {exc}")
            issues = []
        warnings = _check_unmapped_field_values(issues, config.field_mapping)
    finally:
        conn.close()

    print(
        "[validate] LIMITACIÓN CONOCIDA (§8.1.5): no se valida user_mapping.map contra los "
        "miembros reales del proyecto GitLab — GitLabTrackerProvider/DestinationWriter no "
        "expone hoy un método para listar miembros (GET /projects/:id/members/all)."
    )

    for warning in warnings:
        print(f"[validate] ADVERTENCIA: {warning}")
    print(f"[validate] OK ({len(warnings)} advertencia(s)).")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """SIEMPRE dry-run (§10 del plan): nunca instancia un writer real ni lo
    usa para escribir. Decisión de diseño de este batch: la rehidratación
    contra el destino real (`hydrate_map_from_destination_mg`) NO corre acá
    — requeriría credenciales de GitLab, y `plan` debe poder invocarse
    desatendido por un scheduler/cron (§13, C8) sin pedir NADA interactivo
    de destino. El `existing_map` de `plan` sale solo del SQLite local
    (`get_full_mapping`); la rehidratación real contra GitLab ocurre en
    `execute`/`resume`, justo antes de escribir."""
    config = _load_config_or_exit(args.config)
    origin_adapter = _build_origin_adapter(config)

    # NOTA: el gate §8.1.7 ("proyecto ya migrado por completo") NO se aplica
    # acá a propósito — 'plan' es SIEMPRE dry-run/read-only y debe poder
    # re-correrse indefinidamente (incluso para corridas incrementales sobre
    # un proyecto ya 100% migrado, §13 del plan) sin requerir --force. Ese
    # gate solo protege la escritura real en 'execute' sin --dry-run.
    map_db_path = _resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        existing_map = {
            row["mantis_issue_id"]: row["status"]
            for row in get_full_mapping(conn, config.destination.project_path)
        }
        field_mapping_raw = _field_mapping_to_dict(config.field_mapping)
        user_mapping_raw = _user_mapping_to_dict(config.user_mapping)

        plan = plan_migration(origin_adapter, existing_map, field_mapping_raw, user_mapping_raw)
        plan_hash = compute_plan_hash(plan)
        plan_id = config.destination.project_path
        save_plan_snapshot(conn, plan_id, plan_hash, _plan_to_snapshot_dict(plan))

        print(f"[plan] [SIMULACRO] Plan generado — NINGUNA escritura real (§10 del plan).")
        print(f"[plan] Operaciones por tipo: {plan.counts_by_type}")
        print(f"[plan] Saltados (ya migrados, status=done): {plan.skipped_at_plan}")
        print(f"[plan] Hash del plan (para detectar drift en 'execute'): {plan_hash}")
        if plan.warnings:
            print(f"[plan] {len(plan.warnings)} advertencia(s):")
            for warning in plan.warnings:
                print(f"  - {warning}")
        return 0
    finally:
        conn.close()


def _plan_to_snapshot_dict(plan) -> dict:
    return {
        "ops": [
            {
                "op_kind": op.op_kind,
                "mantis_issue_id": op.mantis_issue_id,
                "dest_parent_mantis_id": op.dest_parent_mantis_id,
                "marker": op.marker,
            }
            for op in plan.ops
        ],
        "counts_by_type": plan.counts_by_type,
        "warnings": plan.warnings,
        "skipped_at_plan": plan.skipped_at_plan,
    }


def cmd_execute(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.confirmed:
        print(
            "[execute] ABORTADO: falta --dry-run o --confirmed explícito. Por diseño "
            "(HITL innegociable, §13/C8 del Plan 217), 'execute' NUNCA corre en modo "
            "ambiguo. Un scheduler/cron NUNCA debe invocar --confirmed desatendido — el "
            "único subcomando apto para cron/desatendido es 'plan' (dry-run puro)."
        )
        return 2

    config = _load_config_or_exit(args.config)
    dry_run = bool(args.dry_run)

    map_db_path = _resolve_map_db_path(config)
    conn = _open_map_db_for_run(map_db_path, dry_run=dry_run)
    try:
        if not dry_run:
            already_migrated_error = _check_already_fully_migrated(conn, config, force=args.force)
            if already_migrated_error:
                print(f"[execute] ERROR (§8.1.7): {already_migrated_error}")
                return 1

        origin_adapter = _build_origin_adapter(config)
        field_mapping_raw = _field_mapping_to_dict(config.field_mapping)
        user_mapping_raw = _user_mapping_to_dict(config.user_mapping)

        existing_map = {
            row["mantis_issue_id"]: row["status"]
            for row in get_full_mapping(conn, config.destination.project_path)
        }
        plan = plan_migration(origin_adapter, existing_map, field_mapping_raw, user_mapping_raw)
        plan_hash = compute_plan_hash(plan)

        plan_id = config.destination.project_path
        snapshot = get_plan_snapshot(conn, plan_id)
        if snapshot is None:
            print("[execute] ABORTADO: no hay un plan guardado para este proyecto. Corré 'plan' primero.")
            return 2
        if snapshot["plan_hash"] != plan_hash:
            print(
                "[execute] ABORTADO: el plan cambió desde la última vez que corriste 'plan' "
                f"(hash guardado={snapshot['plan_hash']}, hash actual={plan_hash}). Volvé a "
                "correr 'plan' y revisá los cambios antes de ejecutar (mismo patrón que el "
                "409 de api/migrator.py, adaptado a CLI)."
            )
            return 9

        if len(config.origin.project_ids) > 1:
            print(
                "[execute] ADVERTENCIA (limitación conocida, batch de executor previo): la "
                "rehidratación por marker (hydrate_map_from_destination_mg) solo cubre UN "
                f"mantis_project_id a la vez; se usa {config.origin.project_ids[0]} de "
                f"{config.origin.project_ids}."
            )
        mantis_project_id = str(config.origin.project_ids[0])

        if dry_run:
            writer = DryRunGitLabWriter(config.destination)
        else:
            token = _prompt_and_resolve_secret(
                config.destination.auth.auth_file, "token", config.destination.auth.secret_backend
            )
            writer = GitLabDestinationWriter(config.destination, token)
            assert_target_matches(writer, config.destination)

            base_url, project_path = writer.effective_target()
            print(f"[execute] Destino efectivo resuelto: base_url={base_url!r} project_path={project_path!r}")
            confirm_input = input(
                "Confirmá el project_path de destino escribiéndolo de nuevo "
                f"({config.destination.project_path}): "
            )
            if confirm_input.strip() != config.destination.project_path:
                print("[execute] ABORTADO: el project_path confirmado no coincide. Cancelando por seguridad.")
                return 2

        hydrate_map_from_destination_mg(
            writer, conn,
            project_path=config.destination.project_path,
            mantis_project_id=mantis_project_id,
        )

        checkpoint_path = _resolve_checkpoint_path(config)
        result = execute_migration(
            plan, writer, conn,
            project_path=config.destination.project_path,
            mantis_project_id=mantis_project_id,
            checkpoint_path=checkpoint_path,
            checkpoint_every=config.options.batch_size,
            # Los adjuntos se descargan del origen EN EJECUCIÓN (el binario
            # no viaja en el plan): el adapter y los límites de tamaño se
            # inyectan acá, no en el payload serializado.
            origin_adapter=origin_adapter,
            attachment_options={
                "max_size_mb": config.options.attachments.max_size_mb,
                "skip_if_over_limit": config.options.attachments.skip_if_over_limit,
            },
        )

        mapping_lookup = {
            row["mantis_issue_id"]: row["gitlab_iid"]
            for row in get_full_mapping(conn, config.destination.project_path)
            if row.get("gitlab_iid")
        }
        all_relationships: list[dict] = []
        for issue in origin_adapter.fetch_all_issues():
            issue_id = str(issue.get("id") or issue.get("mantis_issue_id") or "")
            try:
                rels = origin_adapter.fetch_relationships(issue.get("id"))
            except Exception:
                rels = []
            for rel in rels:
                rel = dict(rel)
                rel.setdefault("source_mantis_id", issue_id)
                all_relationships.append(rel)

        relationship_results = migrate_relationships(
            all_relationships, writer, mapping_lookup, config.field_mapping.relationships
        )

        run_id = f"run-{int(time.time())}"
        if config.options.verify_after_execute:
            origin_issues_raw = origin_adapter.fetch_all_issues()
            verify_origin_issues = _build_verify_origin_issues(origin_issues_raw, field_mapping_raw)
            mapping_rows = get_full_mapping(conn, config.destination.project_path)
            verification = verify_migration(mapping_rows, verify_origin_issues, writer=writer)
            if dry_run:
                # En simulacro no existe nada en GitLab contra qué comparar: el
                # muestreo campo-a-campo devolvería un "mismatch" por cada issue
                # (real=None) que NO es un hallazgo real. Se descarta esa parte
                # para no emitir falsos positivos; los chequeos que sí aplican
                # (conteos, markers duplicados) se conservan intactos.
                verification.sample_mismatches = []
                verification.passed = (
                    verification.count_gap == 0 and not verification.duplicate_markers
                )
            print(f"[execute] Verificación: {'APROBADA' if verification.passed else 'CON HALLAZGOS'}")
        else:
            verification = MgVerificationResult()

        report_paths = generate_report(
            verification,
            result,
            run_id=run_id,
            project_path=config.destination.project_path,
            formats=config.options.report_formats,
            output_dir=config.options.report_output_dir,
            dry_run=dry_run,
            redact_pii=args.redact_pii,
            relationships=relationship_results,
        )
        print(
            f"[execute] Aplicadas: {result.applied}, salteadas (idempotencia): {result.skipped}, "
            f"fallidas: {len(result.failed)}, huérfanas: {len(result.orphaned)}"
        )
        print(f"[execute] Reporte generado: {report_paths}")
        return 0
    finally:
        conn.close()


def cmd_resume(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.confirmed:
        print(
            "[resume] ABORTADO: falta --dry-run o --confirmed explícito (mismo gate HITL que "
            "'execute' — resume también puede escribir de verdad al destino)."
        )
        return 2

    config = _load_config_or_exit(args.config)
    dry_run = bool(args.dry_run)

    map_db_path = _resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        origin_adapter = _build_origin_adapter(config)
        field_mapping_raw = _field_mapping_to_dict(config.field_mapping)
        user_mapping_raw = _user_mapping_to_dict(config.user_mapping)

        existing_map = {
            row["mantis_issue_id"]: row["status"]
            for row in get_full_mapping(conn, config.destination.project_path)
        }
        plan = plan_migration(origin_adapter, existing_map, field_mapping_raw, user_mapping_raw)

        mantis_project_id = str(config.origin.project_ids[0])

        if dry_run:
            writer = DryRunGitLabWriter(config.destination)
        else:
            token = _prompt_and_resolve_secret(
                config.destination.auth.auth_file, "token", config.destination.auth.secret_backend
            )
            writer = GitLabDestinationWriter(config.destination, token)
            assert_target_matches(writer, config.destination)

        checkpoint_path = _resolve_checkpoint_path(config)
        result = resume_migration(
            plan, writer, conn,
            project_path=config.destination.project_path,
            mantis_project_id=mantis_project_id,
            checkpoint_path=checkpoint_path,
            checkpoint_every=config.options.batch_size,
        )
        print(
            f"[resume] Aplicadas: {result.applied}, salteadas: {result.skipped}, "
            f"fallidas: {len(result.failed)}"
        )
        return 0
    finally:
        conn.close()


def cmd_verify(args: argparse.Namespace) -> int:
    config = _load_config_or_exit(args.config)
    map_db_path = _resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        origin_adapter = _build_origin_adapter(config)
        field_mapping_raw = _field_mapping_to_dict(config.field_mapping)

        mapping_rows = get_full_mapping(conn, config.destination.project_path)
        origin_issues_raw = origin_adapter.fetch_all_issues()
        verify_origin_issues = _build_verify_origin_issues(origin_issues_raw, field_mapping_raw)

        token = _prompt_and_resolve_secret(
            config.destination.auth.auth_file, "token", config.destination.auth.secret_backend
        )
        writer = GitLabDestinationWriter(config.destination, token)
        assert_target_matches(writer, config.destination)

        verification = verify_migration(mapping_rows, verify_origin_issues, writer=writer)
        print(
            f"[verify] origen={verification.total_origin} migrados={verification.total_migrated} "
            f"gap={verification.count_gap}"
        )
        print(f"[verify] markers duplicados: {len(verification.duplicate_markers)}")
        print(f"[verify] mismatches de muestreo: {len(verification.sample_mismatches)}")
        print(f"[verify] Resultado: {'APROBADO' if verification.passed else 'CON HALLAZGOS'}")
        return 0 if verification.passed else 1
    finally:
        conn.close()


def cmd_report(args: argparse.Namespace) -> int:
    """Regenera el reporte SOLO desde el estado persistido (mapping SQLite),
    sin re-ejecutar ni re-consultar el origen/destino (§16 fila F9: "solo
    regenera el reporte desde el estado persistido"). Limitación documentada:
    `total_origin` se aproxima con el total de filas del mapeo local (no hay
    forma de saber cuántos issues había en el origen sin re-consultarlo, lo
    cual este subcomando tiene prohibido hacer)."""
    config = _load_config_or_exit(args.config)
    map_db_path = _resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        mapping_rows = get_full_mapping(conn, config.destination.project_path)
        total_migrated = len([r for r in mapping_rows if r.get("status") == "done"])
        failed_rows = [r for r in mapping_rows if r.get("status") in ("partial", "failed")]

        verification = MgVerificationResult(
            total_origin=len(mapping_rows),
            total_migrated=total_migrated,
            count_gap=len(mapping_rows) - total_migrated,
            passed=(len(mapping_rows) - total_migrated) == 0,
        )
        execution = MgExecutionResult(
            applied=total_migrated,
            skipped=0,
            failed=[
                {
                    "mantis_issue_id": row["mantis_issue_id"],
                    "op_kind": "create_item",
                    "error": f"status persistido={row['status']}",
                }
                for row in failed_rows
            ],
        )
        run_id = f"report-{int(time.time())}"
        report_paths = generate_report(
            verification,
            execution,
            run_id=run_id,
            project_path=config.destination.project_path,
            formats=config.options.report_formats,
            output_dir=config.options.report_output_dir,
            dry_run=False,
            redact_pii=args.redact_pii,
        )
        print(f"[report] Regenerado desde el estado persistido (SIN re-ejecutar nada): {report_paths}")
        return 0
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────
# argparse
# ─────────────────────────────────────────────────────────────────────────


def _add_common_flags(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--config", required=True, help="Ruta al migration_config.json")
    subparser.add_argument(
        "--dry-run", action="store_true",
        help="Fuerza modo simulacro: NUNCA escribe en GitLab (§10 del plan).",
    )
    subparser.add_argument(
        "--redact-pii", dest="redact_pii", action="store_true", default=True,
        help="Enmascara PII en el reporte final (default ON, §15 [ADICIÓN ARQUITECTO 2]).",
    )
    subparser.add_argument(
        "--no-redact-pii", dest="redact_pii", action="store_false",
        help="Desactiva el enmascarado de PII en el reporte (usar con cuidado).",
    )
    subparser.add_argument(
        "--force", action="store_true",
        help="Permite re-migrar un proyecto ya completo (§8.1.7 del plan).",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.migrar_mantis_gitlab",
        description=(
            "Migrador Mantis -> GitLab (Plan 217). Herramienta CLI operada por un HUMANO "
            "(NO es un agente bajo runtime IA, §2.1 del plan: paridad de 3 runtimes NO aplica)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sp_validate = subparsers.add_parser(
        "validate", help="Valida config/credenciales/conectividad de origen y destino, sin escribir nada."
    )
    _add_common_flags(sp_validate)

    sp_plan = subparsers.add_parser(
        "plan",
        help=(
            "Genera el plan de migración. SIEMPRE dry-run, apto para invocación desatendida "
            "(scheduler/cron, §13/C8) — el ÚNICO subcomando apto para eso."
        ),
    )
    _add_common_flags(sp_plan)

    sp_execute = subparsers.add_parser(
        "execute",
        help=(
            "Ejecuta la migración. Requiere --dry-run o --confirmed explícito. HITL "
            "INNEGOCIABLE: NUNCA invocar con --confirmed desde un scheduler/cron desatendido."
        ),
    )
    _add_common_flags(sp_execute)
    sp_execute.add_argument(
        "--confirmed", action="store_true",
        help="Confirma escritura REAL contra GitLab (pide re-confirmar el project_path interactivamente).",
    )

    sp_resume = subparsers.add_parser(
        "resume", help="Reanuda una migración cortada a mitad de camino (mismo gate HITL que execute)."
    )
    _add_common_flags(sp_resume)
    sp_resume.add_argument("--confirmed", action="store_true", help="Confirma escritura real.")

    sp_verify = subparsers.add_parser(
        "verify", help="Compara lo migrado contra el origen (§8.2 del plan)."
    )
    _add_common_flags(sp_verify)

    sp_report = subparsers.add_parser(
        "report", help="Regenera el reporte final desde el estado persistido, SIN re-ejecutar nada."
    )
    _add_common_flags(sp_report)

    return parser


_HANDLERS = {
    "validate": cmd_validate,
    "plan": cmd_plan,
    "execute": cmd_execute,
    "resume": cmd_resume,
    "verify": cmd_verify,
    "report": cmd_report,
}


def main(argv: "Optional[list[str]]" = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    handler = _HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
