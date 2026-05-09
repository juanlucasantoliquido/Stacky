"""
uat_data_contract_compiler.py — UAT Data Contract Compiler (Sprint 8b).

Extracts data requirements from a compiled UAT scenario (ticket + plan funcional +
steps) and produces a machine-readable data contract that downstream modules
(data_readiness_checker, data_resolution_broker, sql_seed_generator) consume.

This is the bridge between "what steps does the scenario have" and
"what data must exist before we can execute those steps".

Design principles (from Roadmap v2.0):
  - Data is a first-class artifact, not an afterthought.
  - Requirements are extracted heuristically (keyword + screen context), never LLM-only.
  - Schema-unknown entities produce a contract with schema_known=False and
    require human mapping before SQL seed generation.
  - This module is read-only: it NEVER executes DML or queries the DB.

PUBLIC API:
  compile_data_contract(scenario_input: dict) -> DataContractResult
  DataContractResult.to_dict() -> dict   (schema-valid against data_contract/1.0)
  DataContractResult.to_event() -> dict  (for execution.jsonl)

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/data_contract.json  (schema data_contract/1.0)

EVENT EMITTED:
  event: data_contract_compiled
  fields: ticket_id, scenario_id, requirements_count, blocking_requirements, entities

CLI (diagnostic):
  python uat_data_contract_compiler.py --ticket 120 --scenario RF-007-CA-01
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.data_contract_compiler")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "data_contract/1.0"
_CONTRACT_VERSION = "1.0"

# ── Heuristic extraction tables ───────────────────────────────────────────────
#
# Each entry maps a set of step/screen/feature keywords to a data requirement
# template.  The compiler tries each rule in order; first match wins for a
# given scenario step.
#
# db_table / db_key_column are left null when the schema is not yet confirmed;
# schema_known=False signals downstream that SQL seed generation requires a
# human mapping step.

_REQUIREMENT_RULES: list[dict] = [
    # ── Grid / list entities ─────────────────────────────────────────────────
    {
        "keywords": [
            "obligacion", "obligaciones", "gridobligaciones",
            "lista obligaciones", "ver lista de obligaciones",
        ],
        "requirement_template": {
            "entity": "Obligacion",
            "alias": "cliente_con_obligaciones",
            "required_fields": ["CLCOD"],
            "constraints": [
                "cliente existe",
                "cliente tiene al menos una obligacion activa",
                "obligacion tiene corredor",
                "obligacion tiene riesgo",
            ],
            "candidate_sources": ["live_db_readonly", "user_input", "sql_seed"],
            "blocking": True,
            "db_table": None,
            "db_key_column": None,
            "schema_known": False,
            "inferred_from": "step_keywords",
        },
    },
    {
        "keywords": [
            "corredor", "columna corredor", "riesgo", "columna riesgo",
        ],
        "requirement_template": {
            "entity": "Obligacion",
            "alias": "obligacion_con_corredor_y_riesgo",
            "required_fields": ["CLCOD", "Corredor", "Riesgo"],
            "constraints": [
                "obligacion tiene valor no nulo en columna Corredor",
                "obligacion tiene valor no nulo en columna Riesgo",
            ],
            "candidate_sources": ["live_db_readonly", "user_input", "sql_seed"],
            "blocking": True,
            "db_table": None,
            "db_key_column": None,
            "schema_known": False,
            "inferred_from": "step_keywords",
        },
    },
    {
        "keywords": ["lote", "gridbandeja", "bandeja"],
        "requirement_template": {
            "entity": "Lote",
            "alias": "lote_asignado",
            "required_fields": ["AGLOTE"],
            "constraints": [
                "lote existe en RAGEN",
                "lote tiene perfil asignado",
            ],
            "candidate_sources": ["live_db_readonly", "user_input", "sql_seed"],
            "blocking": True,
            "db_table": "RAGEN",
            "db_key_column": "AGLOTE",
            "schema_known": True,
            "inferred_from": "step_keywords",
        },
    },
    {
        "keywords": ["cliente", "detalle cliente", "frmdetalleclie"],
        "requirement_template": {
            "entity": "Cliente",
            "alias": "cliente_existente",
            "required_fields": ["CLCOD"],
            "constraints": ["cliente existe en BD"],
            "candidate_sources": ["live_db_readonly", "user_input", "sql_seed"],
            "blocking": True,
            "db_table": "RCLIE",
            "db_key_column": "CLCOD",
            "schema_known": True,
            "inferred_from": "step_keywords",
        },
    },
    # ── Combo / dropdown / catalog entities ──────────────────────────────────
    {
        "keywords": [
            "combo", "dropdown", "select", "catalogo", "catálogo",
            "ddl_", "comb", "lista de valores",
        ],
        "requirement_template": {
            "entity": "Catalogo",
            "alias": "catalogo_combo_opciones",
            "required_fields": ["IDCODIGO", "DESCRIPCION"],
            "constraints": [
                "catalogo tiene al menos una opcion activa",
                "catalogo no esta vacio",
            ],
            "candidate_sources": ["live_db_readonly", "sql_seed"],
            "blocking": True,
            "db_table": None,
            "db_key_column": None,
            "schema_known": False,
            "inferred_from": "step_keywords",
        },
    },
    # ── User / permissions ────────────────────────────────────────────────────
    {
        "keywords": [
            "usuario qa", "usuario de prueba", "credenciales qa", "login",
            "iniciar sesion", "autenticacion",
        ],
        "requirement_template": {
            "entity": "UsuarioQA",
            "alias": "usuario_qa_activo",
            "required_fields": ["Username", "Password"],
            "constraints": [
                "usuario existe en el sistema",
                "usuario tiene acceso a la pantalla de prueba",
            ],
            "candidate_sources": ["user_input"],
            "blocking": True,
            "db_table": "RASIST",
            "db_key_column": "CODUSR",
            "schema_known": True,
            "inferred_from": "functional_context",
        },
    },
    # ── Ridioma / script SQL parametros ──────────────────────────────────────
    {
        "keywords": ["ridioma", "idtexto", "parametro de texto", "param"],
        "requirement_template": {
            "entity": "RidiomaScript",
            "alias": "ridioma_script_aplicado",
            "required_fields": ["IDTEXTO"],
            "constraints": [
                "script RIDIOMA ha sido aplicado en BD QA",
            ],
            "candidate_sources": ["live_db_readonly"],
            "blocking": True,
            "db_table": "RIDIOMA",
            "db_key_column": "IDTEXTO",
            "schema_known": True,
            "inferred_from": "explicit_precondition",
        },
    },
    # ── Agenda / gestión ─────────────────────────────────────────────────────
    {
        "keywords": ["agenda", "frmgestiones", "gestion", "gestiones"],
        "requirement_template": {
            "entity": "GestionAgenda",
            "alias": "gestion_en_agenda",
            "required_fields": ["AGPERFIL", "AGLOTE"],
            "constraints": [
                "existe al menos una gestion asignada al agente QA",
            ],
            "candidate_sources": ["live_db_readonly", "user_input"],
            "blocking": True,
            "db_table": "RAGEN",
            "db_key_column": "AGPERFIL",
            "schema_known": True,
            "inferred_from": "step_keywords",
        },
    },
]


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DataRequirement:
    """A single data requirement for a UAT scenario."""
    requirement_id: str
    entity: str
    alias: str
    required_fields: List[str]
    constraints: List[str]
    candidate_sources: List[str]
    blocking: bool
    inferred_from: str
    schema_known: bool
    db_table: Optional[str] = None
    db_key_column: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataContractResult:
    """Output of compile_data_contract()."""
    ok: bool
    scenario_id: str
    ticket_id: object       # int for ADO, str for freeform
    feature: Optional[str]
    screen: Optional[str]
    data_contract_version: str
    compiled_at: str
    compiled_by: str
    requirements: List[DataRequirement]
    artifact_path: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

    @property
    def blocking_requirements(self) -> List[DataRequirement]:
        return [r for r in self.requirements if r.blocking]

    @property
    def entities(self) -> List[str]:
        seen: list[str] = []
        for r in self.requirements:
            if r.entity not in seen:
                seen.append(r.entity)
        return seen

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "scenario_id": self.scenario_id,
            "ticket_id": self.ticket_id,
            "feature": self.feature,
            "screen": self.screen,
            "data_contract_version": self.data_contract_version,
            "compiled_at": self.compiled_at,
            "compiled_by": self.compiled_by,
            "requirements": [r.to_dict() for r in self.requirements],
            "summary": {
                "total": len(self.requirements),
                "blocking": len(self.blocking_requirements),
                "entities": self.entities,
            },
            "ok": self.ok,
            "error": self.error,
            "artifact_path": self.artifact_path,
        }

    def to_event(self) -> dict:
        """Produce the data_contract_compiled event dict for execution.jsonl."""
        return {
            "event": "data_contract_compiled",
            "ticket_id": self.ticket_id,
            "scenario_id": self.scenario_id,
            "requirements_count": len(self.requirements),
            "blocking_requirements": len(self.blocking_requirements),
            "entities": self.entities,
            "schema_known_count": sum(1 for r in self.requirements if r.schema_known),
            "schema_unknown_count": sum(1 for r in self.requirements if not r.schema_known),
            "artifact_path": self.artifact_path,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def compile_data_contract(
    scenario_input: dict,
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> DataContractResult:
    """
    Compile a data contract from a scenario input dict.

    Parameters
    ----------
    scenario_input : dict
        Must contain at minimum:
          - scenario_id (str)
          - ticket_id (int|str)
        Optional enrichment fields:
          - feature (str)
          - screen (str)
          - steps (list[str|dict]) — scenario step descriptions
          - functional_context (str) — plain-text functional description
          - technical_context (str) — plain-text technical description
          - preconditions (list[str]) — explicit precondition strings

    exec_logger : ExecutionLogger | None
        If provided, emits data_contract_compiled event.

    evidence_dir : Path | None
        If provided, writes data_contract.json artifact.

    run_id : str | None
        Sub-directory for artifact placement.

    Returns
    -------
    DataContractResult
    """
    scenario_id: str = str(scenario_input.get("scenario_id") or "unknown")
    ticket_id = scenario_input.get("ticket_id", 0)
    feature: Optional[str] = scenario_input.get("feature")
    screen: Optional[str] = scenario_input.get("screen")
    steps = scenario_input.get("steps") or []
    functional_context: str = scenario_input.get("functional_context") or ""
    technical_context: str = scenario_input.get("technical_context") or ""
    preconditions: list = scenario_input.get("preconditions") or []

    # Build a combined search text for keyword matching
    search_corpus = _build_search_corpus(
        steps=steps,
        feature=feature,
        screen=screen,
        functional_context=functional_context,
        technical_context=technical_context,
        preconditions=preconditions,
    )

    # Extract requirements from corpus
    requirements = _extract_requirements(
        search_corpus=search_corpus,
        scenario_id=scenario_id,
    )

    compiled_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    result = DataContractResult(
        ok=True,
        scenario_id=scenario_id,
        ticket_id=ticket_id,
        feature=feature,
        screen=screen,
        data_contract_version=_CONTRACT_VERSION,
        compiled_at=compiled_at,
        compiled_by=f"uat_data_contract_compiler/{_TOOL_VERSION}",
        requirements=requirements,
    )

    # Write artifact
    artifact_path = _write_artifact(result, evidence_dir, run_id, scenario_id)
    if artifact_path:
        result.artifact_path = str(artifact_path)

    # Emit event
    _emit_event(exec_logger, result)

    logger.info(
        "data_contract compiled: scenario=%s requirements=%d blocking=%d entities=%s",
        scenario_id,
        len(requirements),
        len(result.blocking_requirements),
        result.entities,
    )

    return result


def compile_all_contracts(
    scenarios: list[dict],
    ticket_id: object = 0,
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> list[DataContractResult]:
    """Compile data contracts for a list of scenarios.

    Suitable for pipeline stage integration — receives the compiler_result.scenarios list.
    Each scenario dict is enriched with ticket_id before compilation.
    """
    results: list[DataContractResult] = []
    for sc in scenarios:
        enriched = dict(sc)
        enriched.setdefault("ticket_id", ticket_id)
        # Normalize scenario_id: accept both 'scenario_id' and 'id' keys
        if not enriched.get("scenario_id"):
            enriched["scenario_id"] = enriched.get("id", "unknown")
        # Map 'pantalla' → 'screen', 'pasos' → 'steps' (legacy compiler format)
        if not enriched.get("screen"):
            enriched["screen"] = enriched.get("pantalla")
        if not enriched.get("steps"):
            enriched["steps"] = enriched.get("pasos", [])
        result = compile_data_contract(
            scenario_input=enriched,
            exec_logger=exec_logger,
            evidence_dir=evidence_dir,
            run_id=run_id,
        )
        results.append(result)
    return results


# ── Extraction engine ─────────────────────────────────────────────────────────

def _build_search_corpus(
    steps: list,
    feature: Optional[str],
    screen: Optional[str],
    functional_context: str,
    technical_context: str,
    preconditions: list,
) -> str:
    """Build a normalised search string from all available scenario context."""
    parts: list[str] = []

    # Steps can be strings or dicts with 'action'/'description' keys
    for s in steps:
        if isinstance(s, str):
            parts.append(s)
        elif isinstance(s, dict):
            for key in ("description", "action", "target", "alias_semantic", "valor"):
                if s.get(key):
                    parts.append(str(s[key]))

    if feature:
        parts.append(feature)
    if screen:
        parts.append(screen)
    if functional_context:
        parts.append(functional_context)
    if technical_context:
        parts.append(technical_context)
    for prec in preconditions:
        if isinstance(prec, str):
            parts.append(prec)

    corpus = " ".join(parts)
    return corpus.lower()


def _extract_requirements(
    search_corpus: str,
    scenario_id: str,
) -> List[DataRequirement]:
    """
    Heuristically extract data requirements from the search corpus.

    Rules are applied in order; a requirement alias is only emitted once
    (no duplicates). Rule matching is keyword-in-corpus with any() logic.
    """
    seen_aliases: set[str] = set()
    requirements: List[DataRequirement] = []
    req_counter = 0

    for rule in _REQUIREMENT_RULES:
        keywords: list[str] = rule["keywords"]
        tmpl: dict = rule["requirement_template"]

        # Check if any keyword appears in corpus
        if not any(kw in search_corpus for kw in keywords):
            continue

        alias = tmpl["alias"]
        if alias in seen_aliases:
            continue
        seen_aliases.add(alias)
        req_counter += 1

        req_id = f"data.req.{alias}"
        req = DataRequirement(
            requirement_id=req_id,
            entity=tmpl["entity"],
            alias=alias,
            required_fields=list(tmpl["required_fields"]),
            constraints=list(tmpl["constraints"]),
            candidate_sources=list(tmpl["candidate_sources"]),
            blocking=tmpl["blocking"],
            inferred_from=tmpl["inferred_from"],
            schema_known=tmpl["schema_known"],
            db_table=tmpl.get("db_table"),
            db_key_column=tmpl.get("db_key_column"),
            notes=None,
        )
        requirements.append(req)

    return requirements


# ── Artifact & event ──────────────────────────────────────────────────────────

def _write_artifact(
    result: DataContractResult,
    evidence_dir: Optional[Path],
    run_id: Optional[str],
    scenario_id: str,
) -> Optional[Path]:
    """Write data_contract.json artifact; returns path or None."""
    if evidence_dir is None:
        return None
    try:
        if run_id:
            artifact_dir = evidence_dir / str(run_id)
        else:
            artifact_dir = evidence_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        # One file per scenario to avoid collisions across scenarios
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)
        artifact_path = artifact_dir / f"data_contract_{safe_id}.json"
        artifact_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("data_contract artifact written: %s", artifact_path)
        return artifact_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("data_contract: cannot write artifact: %s", exc)
        return None


def _emit_event(exec_logger, result: DataContractResult) -> None:
    """Emit data_contract_compiled event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("data_contract_compiled", result.to_event())
    except Exception as exc:  # noqa: BLE001
        logger.debug("data_contract: cannot emit event: %s", exc)


# ── CLI (diagnostic) ─────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="UAT Data Contract Compiler — extract data requirements from scenario."
    )
    p.add_argument("--ticket", type=int, default=0, help="Ticket ID (for logging).")
    p.add_argument("--scenario", default="unknown", help="Scenario ID (e.g. RF-007-CA-01).")
    p.add_argument("--feature", default=None, help="Feature name.")
    p.add_argument("--screen", default=None, help="Screen name (e.g. FrmDetalleClie.aspx).")
    p.add_argument("--steps", default=None,
                   help="JSON array of step strings (e.g. '[\"ver lista\", \"validar columnas\"]').")
    p.add_argument("--context", default="", help="Functional context text.")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    steps = []
    if args.steps:
        try:
            steps = json.loads(args.steps)
        except Exception:
            steps = [args.steps]

    scenario_input = {
        "ticket_id": args.ticket,
        "scenario_id": args.scenario,
        "feature": args.feature,
        "screen": args.screen,
        "steps": steps,
        "functional_context": args.context,
    }

    result = compile_data_contract(scenario_input)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
