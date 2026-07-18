"""Plan 168 F1 — Store de golden tasks (EvalCase) del arnés de fitness (§4.1/§4.2).

Persistencia tolerante bajo `data_dir()/evolution/evals/`:
  cases.json           — lista completa de EvalCase (nunca se borra: se deshabilita)
  runs.jsonl           — una línea por EvalRun (append-only)
  judge_selfcheck.json — último selfcheck canario del juez (pisado)

Reglas duras (espejo de evolution_store §4.1): `runtime_paths.data_dir()` en CADA
operación (sin cache de módulo — los tests lo monkeypatchean); lecturas tolerantes
(ausente/corrupto → vacío); escrituras bajo `_EVALS_LOCK`.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import runtime_paths

_EVALS_LOCK = threading.Lock()

VALID_SUBJECTS = ("artifact", "output")
VALID_LEVELS = ("deterministic", "execution", "llm_judge")
VALID_ORIGINS = ("seed", "incident", "execution", "manual", "lesson")  # Plan 170 F4
VALID_INPUT_KINDS = ("artifact_text", "golden_ref", "frozen_output")
PATCHABLE_FIELDS = frozenset({"title", "checks", "rubric_id", "weight", "enabled", "input"})


# ── Paths ────────────────────────────────────────────────────────────────────
def evals_root() -> Path:
    return runtime_paths.data_dir() / "evolution" / "evals"


def _cases_path() -> Path:
    return evals_root() / "cases.json"


def _runs_path() -> Path:
    return evals_root() / "runs.jsonl"


def _selfcheck_path() -> Path:
    return evals_root() / "judge_selfcheck.json"


def prompts_dir() -> Path:
    return Path(runtime_paths.backend_root()) / "Stacky" / "agents"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── IO tolerante (NO toman el lock — el caller lo hace) ──────────────────────
def _read_cases() -> list[dict]:
    path = _cases_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — archivo corrupto no tumba el flujo
        return []


def _write_cases(cases: list[dict]) -> None:
    path = _cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


# ── Slugs (v2 C2 — alinear archivo ↔ agents.registry) ────────────────────────
def canonical_agent_slug(raw_slug: str) -> str:
    """Alinea el slug del nombre de archivo con `agents.registry` en lowercase.
    Primer match gana (§F1)."""
    import agents  # import LAZY

    reg = {k.lower() for k in agents.registry}
    raw = (raw_slug or "").lower()
    # 1) match directo
    if raw in reg:
        return raw
    # 2) "<x>agent" -> "<x>"
    if raw.endswith("agent") and raw[: -len("agent")] in reg:
        return raw[: -len("agent")]
    # 3) la clave de reg (len >= 2) MÁS LARGA que sea PREFIJO de raw
    prefix_matches = [k for k in reg if len(k) >= 2 and raw.startswith(k)]
    if prefix_matches:
        return max(prefix_matches, key=len)
    # 4) sin match
    return raw


def slug_for_prompt_file(filename: str) -> str:
    name = filename or ""
    suffix = ".agent.md"
    if name.lower().endswith(suffix):
        base = name[: -len(suffix)]
        return canonical_agent_slug(base.lower())
    stem = Path(name).stem
    return canonical_agent_slug(stem.lower())


def _real_registry_key(slug: str) -> str | None:
    """La clave REAL de agents.registry con k.lower()==slug (o None)."""
    import agents  # lazy

    for k in agents.registry:
        if k.lower() == slug:
            return k
    return None


# ── Validación / construcción de un caso ─────────────────────────────────────
def _normalize_input(inp: dict | None) -> dict:
    inp = inp or {}
    return {
        "kind": inp.get("kind", "artifact_text"),
        "text": inp.get("text"),
        "golden_name": inp.get("golden_name"),
    }


def _validate_case(case: dict) -> None:
    """Valida un caso ya con shape completo. ValueError("invalid_case:<campo>")
    si falla; propaga unknown_check_kind/invalid_check de checks.validate_check_spec."""
    from evals import checks as _checks  # lazy

    if not isinstance(case.get("aspect_key"), str) or not case["aspect_key"]:
        raise ValueError("invalid_case:aspect_key")
    if case.get("subject") not in VALID_SUBJECTS:
        raise ValueError("invalid_case:subject")
    if case.get("level") not in VALID_LEVELS:
        raise ValueError("invalid_case:level")
    if case.get("origin") not in VALID_ORIGINS:
        raise ValueError("invalid_case:origin")
    inp = case.get("input") or {}
    if inp.get("kind") not in VALID_INPUT_KINDS:
        raise ValueError("invalid_case:input")
    weight = case.get("weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValueError("invalid_case:weight")

    checks = case.get("checks") or []
    if not isinstance(checks, list):
        raise ValueError("invalid_case:checks")
    for chk in checks:
        _checks.validate_check_spec(chk)  # unknown_check_kind:<kind> / invalid_check:<campo>

    level = case["level"]
    rubric_id = case.get("rubric_id")
    if level == "deterministic":
        if not checks:
            raise ValueError("invalid_case:checks")
        if rubric_id is not None:
            raise ValueError("invalid_case:rubric_id")
    elif level == "execution":
        if inp.get("kind") not in ("golden_ref", "frozen_output"):
            raise ValueError("invalid_case:input")
        if rubric_id is not None:
            raise ValueError("invalid_case:rubric_id")
    elif level == "llm_judge":
        if not rubric_id:
            raise ValueError("invalid_case:rubric_id")

    # v2 C6 — golden_ref exige agent_type no nulo (load_golden_set(None) rompería)
    if inp.get("kind") == "golden_ref" and not case.get("agent_type"):
        raise ValueError("invalid_case:agent_type")


def _build_case(**fields) -> dict:
    now = _now_iso()
    cid = fields.get("id") or ("case-" + uuid4().hex)
    weight = fields.get("weight", 1.0)
    case = {
        "id": cid,
        "aspect_key": fields.get("aspect_key"),
        "agent_type": fields.get("agent_type"),
        "subject": fields.get("subject"),
        "level": fields.get("level"),
        "title": fields.get("title") or "",
        "input": _normalize_input(fields.get("input")),
        "checks": list(fields.get("checks") or []),
        "rubric_id": fields.get("rubric_id"),
        "weight": weight,
        "origin": fields.get("origin", "manual"),
        "enabled": bool(fields.get("enabled", True)),
        "source_ref": fields.get("source_ref"),
        "created_at": fields.get("created_at") or now,
        "updated_at": fields.get("updated_at") or now,
    }
    _validate_case(case)
    return case


# ── API pública ──────────────────────────────────────────────────────────────
def list_cases(aspect_key: str | None = None, enabled: bool | None = None) -> list[dict]:
    with _EVALS_LOCK:
        cases = _read_cases()
    return [
        c for c in cases
        if (aspect_key is None or c.get("aspect_key") == aspect_key)
        and (enabled is None or bool(c.get("enabled")) == enabled)
    ]


def get_case(case_id: str) -> dict | None:
    with _EVALS_LOCK:
        cases = _read_cases()
    return next((c for c in cases if c.get("id") == case_id), None)


def create_case(**fields) -> dict:
    case = _build_case(**fields)
    with _EVALS_LOCK:
        cases = _read_cases()
        cases.append(case)
        _write_cases(cases)
    return case


def patch_case(case_id: str, **patch) -> dict:
    for key in patch:
        if key not in PATCHABLE_FIELDS:
            raise ValueError("invalid_case:campo_no_editable")
    with _EVALS_LOCK:
        cases = _read_cases()
        idx = next((i for i, c in enumerate(cases) if c.get("id") == case_id), None)
        if idx is None:
            raise KeyError("case_not_found")
        updated = dict(cases[idx])
        for key, value in patch.items():
            if key == "input":
                updated["input"] = _normalize_input(value)
            else:
                updated[key] = value
        updated["updated_at"] = _now_iso()
        _validate_case(updated)
        cases[idx] = updated
        _write_cases(cases)
        return dict(updated)


def list_aspect_keys() -> list[str]:
    return sorted({c.get("aspect_key") for c in list_cases() if c.get("aspect_key")})


# ── Seeds idempotentes (§F1) ─────────────────────────────────────────────────
def _seed_specs() -> list[dict]:
    from evals import golden_runner  # lazy

    specs: list[dict] = []

    # (a) por cada *.agent.md en prompts_dir()
    pdir = prompts_dir()
    if pdir.exists():
        for prompt_file in sorted(pdir.glob("*.agent.md")):
            slug = slug_for_prompt_file(prompt_file.name)
            real_key = _real_registry_key(slug)
            aspect = f"agent_prompts/{slug}"
            specs.append({
                "id": f"case-seed-artifact-{slug}-estructura",
                "aspect_key": aspect, "agent_type": real_key,
                "subject": "artifact", "level": "deterministic",
                "input": {"kind": "artifact_text", "text": None, "golden_name": None},
                "checks": [
                    {"kind": "min_len", "value": 200},
                    {"kind": "regex", "pattern": "(?m)^#{1,6}\\s"},
                    {"kind": "max_len", "value": 400000},
                ],
                "rubric_id": None, "origin": "seed",
                "title": f"Estructura mínima del prompt {slug}",
            })
            specs.append({
                "id": f"case-seed-artifact-{slug}-rubrica",
                "aspect_key": aspect, "agent_type": real_key,
                "subject": "artifact", "level": "llm_judge",
                "input": {"kind": "artifact_text", "text": None, "golden_name": None},
                "checks": [], "rubric_id": "prompt_de_agente", "origin": "seed",
                "title": f"Rúbrica de calidad del prompt {slug}",
            })

    # (b) por cada agent_type con golden set y cada caso
    try:
        golden_agents = golden_runner.list_agents()
    except Exception:  # noqa: BLE001 — G15, dir ausente o corrupto
        golden_agents = []
    for agent_type in golden_agents:
        try:
            golden_cases = golden_runner.load_golden_set(agent_type)
        except Exception:  # noqa: BLE001
            golden_cases = []
        for gc in golden_cases:
            specs.append({
                "id": f"case-seed-golden-{agent_type}-{gc.name}",
                "aspect_key": f"agent_prompts/{agent_type}", "agent_type": agent_type,
                "subject": "output", "level": "execution",
                "input": {"kind": "golden_ref", "text": None, "golden_name": gc.name},
                "checks": [], "rubric_id": None, "origin": "seed",
                "title": f"Golden {agent_type}/{gc.name}",
            })

    # (c) lecciones (knowledge_rag)
    specs.append({
        "id": "case-seed-artifact-leccion-rubrica",
        "aspect_key": "knowledge_rag", "agent_type": None,
        "subject": "artifact", "level": "llm_judge",
        "input": {"kind": "artifact_text", "text": None, "golden_name": None},
        "checks": [], "rubric_id": "leccion_conocimiento", "origin": "seed",
        "title": "Rúbrica de calidad de la lección",
    })
    specs.append({
        "id": "case-seed-artifact-leccion-estructura",
        "aspect_key": "knowledge_rag", "agent_type": None,
        "subject": "artifact", "level": "deterministic",
        "input": {"kind": "artifact_text", "text": None, "golden_name": None},
        "checks": [{"kind": "min_len", "value": 40}, {"kind": "max_len", "value": 8000}],
        "rubric_id": None, "origin": "seed",
        "title": "Estructura mínima de la lección",
    })
    return specs


def ensure_seed_cases() -> list[dict]:
    """Idempotente por ID DETERMINISTA: si el id ya existe NO se recrea ni se pisa
    (respeta ediciones del operador)."""
    with _EVALS_LOCK:
        cases = _read_cases()
        existing = {c.get("id") for c in cases}
        changed = False
        for spec in _seed_specs():
            if spec["id"] in existing:
                continue
            try:
                case = _build_case(**spec)
            except ValueError:
                continue  # tolerante (G15): un seed inválido no tumba el resto
            cases.append(case)
            existing.add(case["id"])
            changed = True
        if changed:
            _write_cases(cases)
        return list(cases)


# ── Runs (append-only) ───────────────────────────────────────────────────────
def append_run(run: dict) -> None:
    with _EVALS_LOCK:
        path = _runs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(run, ensure_ascii=False) + "\n")


def read_runs_tail(aspect_key: str | None = None, limit: int = 20) -> list[dict]:
    """Más nuevo primero, respetando `limit`."""
    rows = _read_jsonl(_runs_path())
    if aspect_key is not None:
        rows = [r for r in rows if r.get("aspect_key") == aspect_key]
    rows.reverse()
    return rows[: max(0, int(limit))]


# ── Selfcheck del juez (pisado) ──────────────────────────────────────────────
def write_judge_selfcheck(d: dict) -> None:
    with _EVALS_LOCK:
        path = _selfcheck_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def read_judge_selfcheck() -> dict | None:
    path = _selfcheck_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None
