"""Plan 86 — Centinelas del contenido de ayuda en lenguaje llano.

Contrato: services/harness_flags_help.py es un módulo PURO (sin flask/config/IO)
con PLAIN_HELP cubriendo el 100% de FLAG_REGISTRY, sin keys huérfanas, con
formato fijo (on/off empiezan con "Si "), sin jerga de IA (denylist congelada)
y que NINGÚN módulo de runtime importa.
"""
import re
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY

BACKEND_ROOT = Path(__file__).resolve().parent.parent  # .../backend

# Denylist CONGELADA de jerga prohibida en la ayuda llana (case-insensitive,
# por palabra completa). Cambiarla es decisión consciente con code review.
JARGON_DENYLIST = (
    "MCP", "TF-IDF", "LLM", "stdin", "stdout", "endpoint", "frontmatter",
    "prompt", "token", "regex", "backend", "frontend", "gate", "hook", "runtime",
)
# Prohibido citar keys tipo SCREAMING_SNAKE y referencias a fases de planes ("F1.1").
_KEY_RE = re.compile(r"\b[A-Z]+_[A-Z0-9_]+\b")
_PHASE_RE = re.compile(r"\bF\d")

REGISTRY_KEYS = {spec.key for spec in FLAG_REGISTRY}


def _all_fields(entry) -> list[str]:
    return [entry.what, entry.on_effect, entry.off_effect, entry.example]


def test_plain_help_covers_all_registry_keys():
    from services.harness_flags_help import PLAIN_HELP
    missing = sorted(REGISTRY_KEYS - set(PLAIN_HELP))
    assert missing == [], f"Flags sin ayuda llana: {missing}"


def test_plain_help_has_no_orphan_keys():
    from services.harness_flags_help import PLAIN_HELP
    orphans = sorted(set(PLAIN_HELP) - REGISTRY_KEYS)
    assert orphans == [], f"Ayuda para flags inexistentes: {orphans}"


def test_plain_help_fields_non_empty_and_bounded():
    from services.harness_flags_help import PLAIN_HELP
    for key, entry in PLAIN_HELP.items():
        assert len(entry.what.strip()) >= 10, f"{key}: what demasiado corto"
        assert len(entry.what) <= 200, f"{key}: what > 200 chars"
        assert len(entry.on_effect) <= 240, f"{key}: on_effect > 240 chars"
        assert len(entry.off_effect) <= 240, f"{key}: off_effect > 240 chars"
        assert len(entry.example) <= 300, f"{key}: example > 300 chars"
        for field in _all_fields(entry):
            assert field.strip(), f"{key}: campo vacío"


def test_plain_help_on_off_start_with_si():
    from services.harness_flags_help import PLAIN_HELP
    for key, entry in PLAIN_HELP.items():
        assert entry.on_effect.startswith("Si "), f"{key}: on_effect no empieza con 'Si '"
        assert entry.off_effect.startswith("Si "), f"{key}: off_effect no empieza con 'Si '"


def test_plain_help_avoids_jargon_denylist():
    from services.harness_flags_help import PLAIN_HELP
    violations = []
    for key, entry in PLAIN_HELP.items():
        for field in _all_fields(entry):
            for term in JARGON_DENYLIST:
                # v2/C10 — plural opcional: "token" y "tokens" caen igual.
                if re.search(rf"\b{re.escape(term)}s?\b", field, re.IGNORECASE):
                    violations.append(f"{key}: '{term}'")
            if _KEY_RE.search(field):
                violations.append(f"{key}: cita una key SCREAMING_SNAKE")
            if _PHASE_RE.search(field):
                violations.append(f"{key}: referencia a fase de plan (F<n>)")
    assert violations == [], f"Jerga prohibida en ayuda llana: {violations}"


def test_plain_help_module_is_pure():
    src = (BACKEND_ROOT / "services" / "harness_flags_help.py").read_text(encoding="utf-8")
    for forbidden in ("import flask", "from flask", "from config", "import os", "import requests"):
        assert forbidden not in src, f"harness_flags_help.py no debe contener '{forbidden}'"


# v2/C3 — poda de directorios que NO son código de la app (backend\.venv EXISTE:
# sin poda, rglob leería miles de archivos del venv en cada corrida del ratchet).
_EXCLUDED_DIRS = {".venv", "venv", "__pycache__", "node_modules", "data", "dist", "build"}


def test_no_runtime_imports_plain_help():
    """Centinela de impacto NULO en los 3 runtimes: solo el registry (y este
    módulo/los tests) pueden referirse a harness_flags_help."""
    allowed = {"services/harness_flags.py", "services/harness_flags_help.py"}
    offenders = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if _EXCLUDED_DIRS & set(path.parts):
            continue
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith("tests/") or rel in allowed:
            continue
        if "harness_flags_help" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert offenders == [], f"Módulos fuera del registry que tocan la ayuda llana: {offenders}"


def test_read_current_exposes_plain_help():
    from services.harness_flags import read_current
    flags = {f["key"]: f for f in read_current()}
    ph = flags["CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED"]["plain_help"]
    assert ph is not None
    assert set(ph) == {"what", "on_effect", "off_effect", "example"}
    assert ph["on_effect"].startswith("Si ")
    # Toda flag expone la clave (aunque una futura sin entrada daría None):
    assert all("plain_help" in f for f in flags.values())
