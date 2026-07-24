"""tests/test_mg_fixtures_no_pii.py — Plan 217 Batch 5, F7c
([ADICIÓN ARQUITECTO 2] — §15).

Red de seguridad verificable en CI (no promesa): escanea TODOS los
archivos de `backend/tests/fixtures/mg/` (sin asumir nombres — `rglob`) y
FALLA si encuentra:
  - dominios corporativos reales (`@ais-int` / `@imsolutions` / `@ripley`,
    case-insensitive).
  - nombres reales conocidos de esta sesión (`santoliquido`, `juanluca`,
    case-insensitive).

El segundo test (`test_scan_detecta_pii_inyectada_en_directorio_temporal`)
prueba que el DETECTOR funciona de verdad — inyecta PII fake en un
directorio TEMPORAL (nunca en `fixtures/mg/` real) y confirma que el
escaneo la encuentra, para que este test sea una garantía real y no solo
"los fixtures de hoy están limpios por casualidad".
"""
from __future__ import annotations

import re
from pathlib import Path

_FIXTURES_MG_DIR = Path(__file__).resolve().parent / "fixtures" / "mg"

_PII_PATTERNS: "dict[str, re.Pattern[str]]" = {
    "dominio_corporativo": re.compile(r"@ais-int|@imsolutions|@ripley", re.IGNORECASE),
    "nombre_real_santoliquido": re.compile(r"santoliquido", re.IGNORECASE),
    "nombre_real_juanluca": re.compile(r"juanluca", re.IGNORECASE),
}

# Allowlist explícita de excepciones (vacía hoy — documentado en el batch
# "no debería hacer falta, los fixtures ya fueron creados con cuidado").
_ALLOWLIST_RELATIVE_PATHS: "frozenset[str]" = frozenset()


def scan_for_pii(root: Path) -> "list[dict]":
    """Recorre TODOS los archivos bajo `root` (recursivo) y devuelve una
    lista de hallazgos accionables: `{"file": ruta, "pattern": nombre}`
    por cada (archivo, patrón) que matchee. Lista vacía == limpio."""
    findings: "list[dict]" = []
    if not root.exists():
        return findings

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        if rel in _ALLOWLIST_RELATIVE_PATHS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern_name, pattern in _PII_PATTERNS.items():
            if pattern.search(text):
                findings.append({"file": str(path), "pattern": pattern_name})

    return findings


# ── Red de seguridad real: los fixtures existentes deben estar limpios ──


def test_fixtures_mg_no_contienen_pii_real():
    findings = scan_for_pii(_FIXTURES_MG_DIR)
    assert findings == [], (
        "Se detectó PII real en fixtures/mg/ (accionable — revisar cada entrada "
        f"y anonimizar el archivo): {findings}"
    )


# ── El detector funciona de verdad: se prueba con PII inyectada en tmp ──


def test_scan_detecta_dominio_corporativo_inyectado_en_directorio_temporal(tmp_path):
    (tmp_path / "fixture_con_pii.json").write_text(
        '{"reporter_email": "alice@ais-int.net"}', encoding="utf-8"
    )

    findings = scan_for_pii(tmp_path)

    assert len(findings) == 1
    assert findings[0]["pattern"] == "dominio_corporativo"
    assert findings[0]["file"] == str(tmp_path / "fixture_con_pii.json")


def test_scan_detecta_nombre_real_santoliquido_inyectado_en_directorio_temporal(tmp_path):
    (tmp_path / "otro.html").write_text("<td>Reportado por Santoliquido</td>", encoding="utf-8")

    findings = scan_for_pii(tmp_path)

    assert len(findings) == 1
    assert findings[0]["pattern"] == "nombre_real_santoliquido"


def test_scan_detecta_nombre_real_juanluca_inyectado_en_directorio_temporal(tmp_path):
    (tmp_path / "otro2.txt").write_text("autor: juanluca", encoding="utf-8")

    findings = scan_for_pii(tmp_path)

    assert len(findings) == 1
    assert findings[0]["pattern"] == "nombre_real_juanluca"


def test_scan_no_reporta_nada_en_directorio_temporal_limpio(tmp_path):
    (tmp_path / "limpio.json").write_text('{"reporter": "user_placeholder"}', encoding="utf-8")

    findings = scan_for_pii(tmp_path)

    assert findings == []


def test_scan_recorre_subdirectorios_recursivamente(tmp_path):
    sub = tmp_path / "sub" / "anidado"
    sub.mkdir(parents=True)
    (sub / "profundo.html").write_text("contacto@ripley.com", encoding="utf-8")

    findings = scan_for_pii(tmp_path)

    assert len(findings) == 1
    assert findings[0]["file"] == str(sub / "profundo.html")
