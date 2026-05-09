"""
data_resolution_broker.py — UAT Data Resolution Broker (Sprint 9).

Receives a DataReadinessCheckResult with ready=False and a list of
MissingRequirement objects, then turns each into a structured decision
request for the human operator (or for the pipeline to surface via UI/API).

For each missing requirement the broker:
  1. Selects ordered resolution options from qa_uat_data_policy.yml (GENERATE_SQL_SEED
     excluded when the target environment is PROD or UAT — policy.allow_seed=False).
  2. Composes a human-readable question.
  3. Assigns a unique request ID and persists a pending record to qa_data_requests.json.
  4. Writes a data_resolution_request.json artifact.
  5. Emits event data_request_created to execution.jsonl.

PUBLIC API:
  run(readiness_result, ...) -> DataResolutionBrokerResult
  DataResolutionBrokerResult.to_dict() -> dict

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/data_resolution_request.json

PERSISTENCE:
  evidence/<ticket_id>/<run_id>/qa_data_requests.json
  Fields: id, run_id, ticket_id, scenario_id, requirement_id, question,
          required_fields_json, status, created_at, resolved_at,
          resolved_by, resolution_type

EVENT EMITTED:
  data_request_created
  fields: ticket_id, scenario_id, request_id, question, required_fields, status

PIPELINE INTERACTION (Sprint 9 — Stage S9-broker):
  If QA_UAT_BLOCK_ON_MISSING_DATA_CONTRACT=true and there are pending
  data requests, the pipeline emits BLOCKED DATA USER_DATA_REQUIRED.

SECURITY:
  - Never logs or stores unmasked user-supplied data.
  - generate_sql_seed option is filtered out unless policy.allow_seed=True
    for the resolved environment.
  - No DML executed by this module.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.data_resolution_broker")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "data_resolution_broker/1.0"

# ── Option IDs ────────────────────────────────────────────────────────────────

class OptionId:
    PROVIDE_EXISTING_VALUE = "provide_existing_value"
    RUN_DISCOVERY_QUERY    = "run_discovery_query"
    GENERATE_SQL_SEED      = "generate_sql_seed"
    MANUAL_REVIEW          = "manual_review"


# Maps resolution option codes (from data_readiness_checker) to broker option specs.
_OPTION_SPECS: dict[str, dict] = {
    "ASK_USER_FOR_VALUE": {
        "id": OptionId.PROVIDE_EXISTING_VALUE,
        "label": "Ingresar valor existente",
        "requires_input": [],   # filled per-requirement below
    },
    "RUN_DISCOVERY_QUERY": {
        "id": OptionId.RUN_DISCOVERY_QUERY,
        "label": "Buscar candidatos en BD read-only",
        "requires_input": [],
    },
    "GENERATE_SQL_SEED": {
        "id": OptionId.GENERATE_SQL_SEED,
        "label": "Generar script SQL de seed para ambiente QA",
        "requires_input": [],
    },
    "MARK_MANUAL_REVIEW": {
        "id": OptionId.MANUAL_REVIEW,
        "label": "Marcar como revisión manual",
        "requires_input": [],
    },
}

# ── Human-readable question templates ─────────────────────────────────────────

_QUESTION_TEMPLATES: dict[str, str] = {
    "cliente_con_obligaciones": (
        "Necesito un CLCOD que tenga al menos una obligación activa con corredor y riesgo."
    ),
    "catalogo": (
        "Necesito que exista al menos un valor en el catálogo '{alias}' para poder ejecutar "
        "el scenario."
    ),
    "test_entity": (
        "No encontré el/la {entity} requerido/a para el scenario. "
        "Por favor indique un identificador válido existente en ambiente QA."
    ),
    "default": (
        "No encontré datos para '{alias}' ({entity}). "
        "Por favor elija una opción para proveer los datos requeridos."
    ),
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class DecisionOption:
    id: str
    label: str
    requires_input: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataDecision:
    """A single missing-data decision request destined for the human operator."""
    event: str
    ticket_id: object
    scenario_id: str
    missing_requirement: str          # requirement alias
    question_for_user: str
    options: List[DecisionOption]
    request_id: str                   # "datareq-<ticket_id>-<seq>"
    requirement_id: str
    required_fields: List[str]

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "ticket_id": self.ticket_id,
            "scenario_id": self.scenario_id,
            "missing_requirement": self.missing_requirement,
            "question_for_user": self.question_for_user,
            "options": [o.to_dict() for o in self.options],
            "request_id": self.request_id,
            "requirement_id": self.requirement_id,
            "required_fields": self.required_fields,
        }


@dataclass
class PendingDataRequest:
    """Persistent record of a pending data request (stored in qa_data_requests.json)."""
    id: str
    run_id: str
    ticket_id: object
    scenario_id: str
    requirement_id: str
    question: str
    required_fields_json: str       # JSON-serialised list
    status: str                     # pending_user_input|resolved|timeout|rejected
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_type: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataResolutionBrokerResult:
    ok: bool
    ticket_id: object
    scenario_id: str
    decisions: List[DataDecision]
    pending_request_ids: List[str]
    artifact_path: Optional[str] = None
    requests_store_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "ticket_id": self.ticket_id,
            "scenario_id": self.scenario_id,
            "decisions": [d.to_dict() for d in self.decisions],
            "pending_request_ids": self.pending_request_ids,
            "artifact_path": self.artifact_path,
            "requests_store_path": self.requests_store_path,
            "error": self.error,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    readiness_result,              # DataReadinessCheckResult or dict
    run_id: Optional[str] = None,
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    policy_path: Optional[Path] = None,
    environment: Optional[str] = None,   # DEV|QA|UAT|PROD — overrides env-var lookup
) -> DataResolutionBrokerResult:
    """
    Process a DataReadinessCheckResult with ready=False and produce
    one DataDecision per missing requirement.

    Parameters
    ----------
    readiness_result : DataReadinessCheckResult | dict
        Output of data_readiness_checker.check_readiness().
        Must have .missing (list of MissingRequirement) or dict equivalent.
    run_id : str | None
        Pipeline run identifier.  Used as sub-dir and prefix for request IDs.
    exec_logger : ExecutionLogger | None
        If provided, emits data_request_created for each decision.
    evidence_dir : Path | None
        If provided, writes data_resolution_request.json and qa_data_requests.json.
    policy_path : Path | None
        Override path for qa_uat_data_policy.yml.
    environment : str | None
        Target environment name (DEV|QA|UAT|PROD).  If None, read from
        QA_UAT_TARGET_ENVIRONMENT env var; default is "QA".

    Returns
    -------
    DataResolutionBrokerResult
    """
    # Normalise input
    if hasattr(readiness_result, "missing"):
        missing_list = readiness_result.missing
        ticket_id = readiness_result.ticket_id
        scenario_id = readiness_result.scenario_id
    else:
        # dict path
        missing_list = readiness_result.get("missing", [])
        ticket_id = readiness_result.get("ticket_id", 0)
        scenario_id = readiness_result.get("scenario_id", "unknown")

    # Resolve environment
    env = (environment or os.environ.get("QA_UAT_TARGET_ENVIRONMENT", "QA")).upper()

    # Load policy
    policy = _load_policy(policy_path)
    env_policy = _get_env_policy(policy, env)
    allow_seed = env_policy.get("allow_seed", False)

    effective_run_id = run_id or _make_run_id(ticket_id)
    decisions: List[DataDecision] = []
    pending_records: List[PendingDataRequest] = []
    created_at = _utcnow()

    for idx, missing in enumerate(missing_list, start=1):
        # Accept both MissingRequirement objects and dicts
        if hasattr(missing, "alias"):
            alias        = missing.alias
            entity       = missing.entity
            req_id       = missing.requirement_id
            res_options  = missing.resolution_options
            req_fields   = list(getattr(missing, "required_fields", []) or [])
        else:
            alias        = missing.get("alias", "unknown")
            entity       = missing.get("entity", "Unknown")
            req_id       = missing.get("requirement_id", f"data.req.{idx}")
            res_options  = missing.get("resolution_options", [])
            req_fields   = list(missing.get("required_fields", []) or [])

        # Derive required_fields from requirement entity if not explicit
        if not req_fields:
            req_fields = _infer_required_fields(entity, alias)

        request_id = f"datareq-{ticket_id}-{idx:03d}"
        question   = _compose_question(alias, entity, req_fields)

        # Build ordered options, filtering out GENERATE_SQL_SEED if not allowed
        options = _build_options(res_options, allow_seed, req_fields)

        decision = DataDecision(
            event="missing_data_decision_required",
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            missing_requirement=alias,
            question_for_user=question,
            options=options,
            request_id=request_id,
            requirement_id=req_id,
            required_fields=req_fields,
        )
        decisions.append(decision)

        # Persist pending record
        pending_record = PendingDataRequest(
            id=request_id,
            run_id=effective_run_id,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            requirement_id=req_id,
            question=question,
            required_fields_json=json.dumps(req_fields),
            status="pending_user_input",
            created_at=created_at,
        )
        pending_records.append(pending_record)

        # Emit event per decision
        _emit_event(exec_logger, {
            "event": "data_request_created",
            "ticket_id": ticket_id,
            "scenario_id": scenario_id,
            "request_id": request_id,
            "question": question,
            "required_fields": req_fields,
            "status": "pending_user_input",
        })

        logger.info(
            "data_resolution_broker: request_id=%s scenario=%s alias=%s options=%s",
            request_id, scenario_id, alias, [o.id for o in options],
        )

    # Write artifacts
    artifact_path = None
    requests_store_path = None
    if evidence_dir is not None:
        artifact_path = _write_resolution_artifact(
            ticket_id, scenario_id, decisions, evidence_dir, effective_run_id
        )
        requests_store_path = _persist_pending_records(
            pending_records, evidence_dir, effective_run_id
        )

    return DataResolutionBrokerResult(
        ok=True,
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        decisions=decisions,
        pending_request_ids=[d.request_id for d in decisions],
        artifact_path=str(artifact_path) if artifact_path else None,
        requests_store_path=str(requests_store_path) if requests_store_path else None,
    )


# ── Option builder ────────────────────────────────────────────────────────────

def _build_options(
    resolution_option_codes: List[str],
    allow_seed: bool,
    required_fields: List[str],
) -> List[DecisionOption]:
    """
    Convert resolution_option_codes to DecisionOption list.

    Rules:
    - GENERATE_SQL_SEED is excluded when allow_seed=False (enforced by policy).
    - PROVIDE_EXISTING_VALUE gets required_fields populated.
    - Order is preserved from resolution_option_codes.
    """
    seen = set()
    options: List[DecisionOption] = []
    for code in resolution_option_codes:
        spec = _OPTION_SPECS.get(code)
        if spec is None:
            continue
        option_id = spec["id"]
        if option_id in seen:
            continue
        # Filter SQL seed in non-seeding environments
        if option_id == OptionId.GENERATE_SQL_SEED and not allow_seed:
            logger.debug(
                "data_resolution_broker: GENERATE_SQL_SEED excluded — allow_seed=False"
            )
            continue
        inp = list(required_fields) if option_id == OptionId.PROVIDE_EXISTING_VALUE else []
        options.append(DecisionOption(
            id=option_id,
            label=spec["label"],
            requires_input=inp,
        ))
        seen.add(option_id)

    # Always include MANUAL_REVIEW as last fallback if not already present
    if OptionId.MANUAL_REVIEW not in seen:
        options.append(DecisionOption(
            id=OptionId.MANUAL_REVIEW,
            label="Marcar como revisión manual",
            requires_input=[],
        ))
    return options


# ── Question composer ─────────────────────────────────────────────────────────

def _compose_question(alias: str, entity: str, req_fields: List[str]) -> str:
    """Build a human-readable question for the operator."""
    if "obligacion" in alias.lower() or "obligacion" in entity.lower():
        return _QUESTION_TEMPLATES["cliente_con_obligaciones"]
    if "catalogo" in alias.lower() or entity.lower() == "catalogo":
        return _QUESTION_TEMPLATES["catalogo"].format(alias=alias)
    if entity.lower() in ("cliente", "lote"):
        return _QUESTION_TEMPLATES["test_entity"].format(entity=entity)
    field_hint = f" Los campos requeridos son: {', '.join(req_fields)}." if req_fields else ""
    return _QUESTION_TEMPLATES["default"].format(alias=alias, entity=entity) + field_hint


# ── Required-fields inference ─────────────────────────────────────────────────

def _infer_required_fields(entity: str, alias: str) -> List[str]:
    """Infer typical required input fields from the entity type."""
    ent = entity.lower()
    ali = alias.lower()
    if "obligacion" in ent or "obligacion" in ali or "clcod" in ali:
        return ["CLCOD"]
    if "cliente" in ent:
        return ["CLCOD"]
    if "lote" in ent:
        return ["LOTEID"]
    if "usuario" in ent:
        return ["LOGIN"]
    return []


# ── Policy loader ─────────────────────────────────────────────────────────────

def _load_policy(policy_path: Optional[Path]) -> dict:
    """Load qa_uat_data_policy.yml.  Returns empty dict on failure (non-fatal)."""
    if policy_path is None:
        policy_path = Path(__file__).parent / "config" / "qa_uat_data_policy.yml"
    try:
        import yaml  # type: ignore[import-untyped]
        with open(policy_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except ImportError:
        # pyyaml not available — parse manually (simplified)
        return _parse_policy_minimal(policy_path)
    except Exception as exc:
        logger.warning("data_resolution_broker: cannot load policy: %s", exc)
        return {}


def _parse_policy_minimal(path: Path) -> dict:
    """Minimal key-value parser for policy YAML when pyyaml is unavailable."""
    try:
        text = path.read_text(encoding="utf-8")
        result: dict = {"environments": {}}
        current_env: Optional[str] = None
        in_environments: bool = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Detect "environments:" top-level key
            if re.match(r"^environments:\s*$", line):
                in_environments = True
                current_env = None
                continue
            if not in_environments:
                continue
            # Top-level environment block "  QA:" under "environments:"
            env_match = re.match(r"^  ([A-Z]+):\s*$", line)
            if env_match:
                current_env = env_match.group(1)
                result["environments"][current_env] = {}
                continue
            if current_env:
                kv = re.match(r"^    (\w+):\s+(\S+)", line)
                if kv:
                    key, val = kv.group(1), kv.group(2)
                    if val.lower() in ("true", "false"):
                        result["environments"][current_env][key] = val.lower() == "true"
                    elif val.isdigit():
                        result["environments"][current_env][key] = int(val)
                    else:
                        result["environments"][current_env][key] = val
        return result
    except Exception:
        return {}


def _get_env_policy(policy: dict, env: str) -> dict:
    """Return the environment-level policy dict for the given env name."""
    envs = policy.get("environments", {})
    # Try exact match first, then substring match
    if env in envs:
        return envs[env]
    for key, val in envs.items():
        if key.upper() in env or env in key.upper():
            return val
    # Safe default: no seed
    return {"allow_seed": False, "require_human_approval": True}


# ── Artifact writers ──────────────────────────────────────────────────────────

def _write_resolution_artifact(
    ticket_id: object,
    scenario_id: str,
    decisions: List[DataDecision],
    evidence_dir: Path,
    run_id: str,
) -> Optional[Path]:
    """Write data_resolution_request.json to evidence dir."""
    try:
        artifact_dir = evidence_dir / str(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)
        path = artifact_dir / f"data_resolution_request_{safe_id}.json"
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "ticket_id": ticket_id,
            "scenario_id": scenario_id,
            "generated_at": _utcnow(),
            "decisions": [d.to_dict() for d in decisions],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("data_resolution_broker: artifact written: %s", path)
        return path
    except Exception as exc:
        logger.warning("data_resolution_broker: cannot write artifact: %s", exc)
        return None


def _persist_pending_records(
    records: List[PendingDataRequest],
    evidence_dir: Path,
    run_id: str,
) -> Optional[Path]:
    """
    Persist pending data request records to qa_data_requests.json.

    The file is a JSON array.  On each call we append new records.
    If the file exists, existing records are preserved (no overwrite).
    """
    try:
        store_dir = evidence_dir / str(run_id)
        store_dir.mkdir(parents=True, exist_ok=True)
        store_path = store_dir / "qa_data_requests.json"

        existing: list = []
        if store_path.is_file():
            try:
                existing = json.loads(store_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        for rec in records:
            existing.append(rec.to_dict())

        store_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("data_resolution_broker: qa_data_requests persisted: %s", store_path)
        return store_path
    except Exception as exc:
        logger.warning("data_resolution_broker: cannot persist records: %s", exc)
        return None


# ── Timeout checker ───────────────────────────────────────────────────────────

def check_timeouts(
    store_path: Path,
    timeout_hours: Optional[float] = None,
) -> List[str]:
    """
    Scan qa_data_requests.json and mark records that have exceeded
    QA_UAT_DATA_REQUEST_TIMEOUT_HOURS without being resolved.

    Returns list of request IDs that were marked as 'timeout'.

    This function modifies store_path in place (updates status field).
    Call it from the pipeline or a cron-style watchdog, never inline.
    """
    if timeout_hours is None:
        timeout_hours = float(
            os.environ.get("QA_UAT_DATA_REQUEST_TIMEOUT_HOURS", "24")
        )
    if not store_path.is_file():
        return []

    try:
        records = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("data_resolution_broker: cannot read store for timeout check: %s", exc)
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    timed_out: List[str] = []

    for rec in records:
        if rec.get("status") != "pending_user_input":
            continue
        try:
            created = datetime.datetime.fromisoformat(
                rec["created_at"].replace("Z", "+00:00")
            )
            elapsed = (now - created).total_seconds() / 3600
            if elapsed >= timeout_hours:
                rec["status"] = "timeout"
                rec["resolved_at"] = now.isoformat().replace("+00:00", "Z")
                rec["resolution_type"] = "timeout"
                timed_out.append(rec["id"])
        except Exception as exc:
            logger.debug("data_resolution_broker: timeout check error for %s: %s", rec.get("id"), exc)

    if timed_out:
        try:
            store_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("data_resolution_broker: cannot write timeout updates: %s", exc)

    return timed_out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _make_run_id(ticket_id: object) -> str:
    return f"{ticket_id}-{uuid.uuid4().hex[:8]}"


def _emit_event(exec_logger, data: dict) -> None:
    if exec_logger is None:
        return
    try:
        exec_logger.event(data["event"], data)
    except Exception as exc:
        logger.debug("data_resolution_broker: cannot emit event: %s", exc)
