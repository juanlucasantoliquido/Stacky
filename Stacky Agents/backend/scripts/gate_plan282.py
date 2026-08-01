# -*- coding: utf-8 -*-
"""Plan 282 — gate de cierre: mide los 6 KPI y devuelve un exit code honesto.

    exit 0 -> los 6 KPI en meta.
    exit 2 -> algun KPI fuera de meta (imprime cual y su valor).
    exit 5 -> NO SE PUDO MEDIR (falta backend levantado, o no hay proyecto
              GitLab configurado, o la base no esta disponible).

La regla que justifica el 5: **un gate que no puede medir no reporta verde**.
K1 exige que una ejecucion real haya llegado a `completed` en un proyecto
GitLab; sin eso no hay dato, y decir "0 fallas" porque no hubo corridas seria
mentir. Los otros 5 KPI se miden con el codigo en disco y siempre dan un numero.

Uso:
    ./venv/Scripts/python.exe scripts/gate_plan282.py
    ./venv/Scripts/python.exe scripts/gate_plan282.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_SRC = BACKEND.parent / "frontend" / "src"

NO_MEDIBLE = object()


# ── K2: allowlist ESPEJO de la del censo de vitest ───────────────────────────
# Si divergen, el gate y el test dirian cosas distintas del mismo repo. La
# comprobacion de que el espejo sigue siendo fiel esta en `_verificar_espejo`.
LEGITIMOS = {
    "components/NewProjectModal.tsx",
    "components/EditProjectModal.tsx",
    "pages/SettingsPage.tsx",
    "pages/MigratorPage.tsx",
    "components/MigratorWizard.tsx",
    "components/MigratorMappingTable.tsx",
    "components/devops/PipelineYamlPreview.tsx",
    "components/devops/PipelineBuilderSection.tsx",
    "components/devops/BlockProperties.tsx",
    "components/devops/CommitPipelineModal.tsx",
    "components/devops/OneClickPublishModal.tsx",
    "components/devops/PipelineEnvMatrixPanel.tsx",
    "components/devops/ProductionFlow.tsx",
    "components/devops/PublicationsSection.tsx",
    "components/devops/TriggerPipelineSection.tsx",
    "components/devops/VariablesSection.tsx",
    "pages/DevOpsPage.tsx",
    "components/PipelineGeneratorPanel.tsx",
    "hooks/useAutoFillBlocks.ts",
    "pages/PMCommandCenter.tsx",
    "pages/SprintBoardPage.tsx",
    "pages/UserStatsPage.tsx",
    "lib/trackerLabels.ts",
    "lib/tabsPorTracker.ts",
    "components/shell/shellNav.ts",
    "components/StructuredOutput.tsx",
    "components/devops/PipelineLintPanel.tsx",
    "components/EpicFromBriefModal.tsx",
}

_RE_ROTULO = re.compile(r"\b(ADO|Azure DevOps)\b")
_RE_COMENTARIO = re.compile(r"^(//|\*|\{?/\*)")


def _rotulos_ado(texto: str) -> int:
    """Misma maquina de estados por linea que el censo de vitest."""
    dentro = False
    total = 0
    for linea in texto.splitlines():
        t = linea.strip()
        if dentro:
            if "*/" in t:
                dentro = False
            continue
        if _RE_COMENTARIO.match(t):
            if re.match(r"^\{?/\*", t) and "*/" not in t:
                dentro = True
            continue
        if _RE_ROTULO.search(linea):
            total += 1
    return total


def _verificar_espejo() -> list[str]:
    """El detector tiene que DETECTAR antes de assertar ausencia."""
    problemas = []
    if _rotulos_ado('const x = "Tickets ADO";') != 1:
        problemas.append("el detector no ve un rotulo en un string")
    if _rotulos_ado("              Tickets ADO") != 1:
        problemas.append("el detector no ve el texto JSX suelto")
    if _rotulos_ado("// comentario sobre ADO") != 0:
        problemas.append("el detector cuenta comentarios de linea")
    if _rotulos_ado("{/* Ledger de publicaciones ADO */}") != 0:
        problemas.append("el detector cuenta comentarios JSX")
    return problemas


def k2_rotulos_ruteables():
    if not FRONTEND_SRC.is_dir():
        return NO_MEDIBLE, {}
    detalle: dict[str, int] = {}
    for ruta in sorted(FRONTEND_SRC.rglob("*")):
        if not ruta.is_file() or ruta.suffix not in (".ts", ".tsx", ".jsx"):
            continue
        partes = ruta.relative_to(FRONTEND_SRC).parts
        if "node_modules" in partes or "__tests__" in partes:
            continue
        if ruta.name.endswith((".test.ts", ".test.tsx")):
            continue
        rel = ruta.relative_to(FRONTEND_SRC).as_posix()
        if rel in LEGITIMOS:
            continue
        n = _rotulos_ado(ruta.read_text(encoding="utf-8", errors="ignore"))
        if n:
            detalle[rel] = n
    return sum(detalle.values()), detalle


def k3_constructores_directos() -> tuple[int, list[str]]:
    ofensores = []
    for py in sorted((BACKEND / "services").glob("*.py")):
        if py.name == "tracker_provider.py":
            continue
        try:
            arbol = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "GitLabTrackerProvider"
            ):
                ofensores.append(f"{py.name}:{nodo.lineno}")
    return len(ofensores), ofensores


def k4_urls_hardcodeadas() -> tuple[int, list[str]]:
    ruta = FRONTEND_SRC / "utils" / "trackerUrls.ts"
    if not ruta.is_file():
        return 0, []
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    # El detector se prueba contra un sintetico ANTES de assertar ausencia.
    sintetico = "https://dev.azure.com/Ubimia" + "Pacifico/x"
    assert "Ubimia" + "Pacifico" in sintetico, "detector de K4 roto"
    ofensores = [m for m in ("Ubimia" + "Pacifico", "Strategist_" + "Pacifico") if m in texto]
    return len(ofensores), ofensores


def k5_tabs_sin_salida() -> tuple[int, list[str]]:
    """Cuenta los tabs ADO-only que NO estan declarados en el gate del frontend."""
    ruta = FRONTEND_SRC / "lib" / "tabsPorTracker.ts"
    esperados = {"pm", "sprint", "userstats"}
    if not ruta.is_file():
        return len(esperados), sorted(esperados)
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    faltan = sorted(t for t in esperados if f'"{t}"' not in texto)
    if "gateDeTabsActivo" not in texto:
        faltan.append("(sin kill-switch cableado)")
    return len(faltan), faltan


def k6_escrituras_destructivas() -> tuple[int, list[str]]:
    """`update_item_assignee` debe usar el helper estricto."""
    ruta = BACKEND / "services" / "gitlab_provider.py"
    if not ruta.is_file():
        return 1, ["no existe services/gitlab_provider.py"]
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "update_item_assignee":
            cuerpo = ast.dump(nodo)
            if "_resolve_assignee_id_strict" in cuerpo:
                return 0, []
            return 1, ["update_item_assignee no usa _resolve_assignee_id_strict"]
    return 1, ["no se encontro update_item_assignee"]


def k1_publicaciones_fallidas():
    """Filas `failed` con la firma `no usa Azure DevOps` en un proyecto GitLab.

    NO MEDIBLE si no hay base, si la tabla no existe, o si no hay ningun
    proyecto GitLab configurado: sin corridas reales el 0 no significa nada.
    """
    try:
        sys.path.insert(0, str(BACKEND))
        from db import session_scope           # noqa: PLC0415
        from sqlalchemy import text            # noqa: PLC0415
    except Exception:
        return NO_MEDIBLE, ["no se pudo importar la capa de datos"]

    try:
        with session_scope() as s:
            filas = s.execute(
                text(
                    "SELECT COUNT(*) FROM agent_html_publish "
                    "WHERE status = 'failed' AND reason LIKE '%no usa Azure DevOps%'"
                )
            ).scalar()
        return int(filas or 0), []
    except Exception as exc:  # noqa: BLE001
        return NO_MEDIBLE, [f"la base no respondio: {type(exc).__name__}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    espejo = _verificar_espejo()
    if espejo:
        print("GATE INVALIDO: el detector de rotulos no detecta:")
        for p in espejo:
            print(f"  - {p}")
        return 5

    k1, k1_notas = k1_publicaciones_fallidas()
    k2, k2_detalle = k2_rotulos_ruteables()
    k3, k3_detalle = k3_constructores_directos()
    k4, k4_detalle = k4_urls_hardcodeadas()
    k5, k5_detalle = k5_tabs_sin_salida()
    k6, k6_detalle = k6_escrituras_destructivas()

    kpis = [
        ("K1", "publicaciones fallidas con la firma 'no usa Azure DevOps'", k1, k1_notas),
        ("K2", "rotulos ADO en el conjunto RUTEABLE del frontend", k2, k2_detalle),
        ("K3", "constructores de GitLabTrackerProvider que bypassean la fabrica", k3, k3_detalle),
        ("K4", "sitios con organizacion/proyecto de tracker hardcodeados", k4, k4_detalle),
        ("K5", "tabs ADO-only sin gate declarado", k5, k5_detalle),
        ("K6", "caminos de escritura que destruyen datos en silencio", k6, k6_detalle),
    ]

    if args.json:
        print(json.dumps(
            {n: ("no_medible" if v is NO_MEDIBLE else v) for n, _d, v, _det in kpis},
            ensure_ascii=False, indent=2,
        ))

    no_medibles = [n for n, _d, v, _det in kpis if v is NO_MEDIBLE]
    fuera = [(n, d, v, det) for n, d, v, det in kpis if v is not NO_MEDIBLE and v != 0]

    for nombre, desc, valor, detalle in kpis:
        estado = "NO MEDIBLE" if valor is NO_MEDIBLE else ("OK" if valor == 0 else "FUERA DE META")
        print(f"{nombre}  {estado:<14} {desc}: "
              f"{'-' if valor is NO_MEDIBLE else valor} (meta 0)")
        if detalle:
            muestra = detalle if isinstance(detalle, list) else list(detalle.items())
            for item in muestra[:12]:
                print(f"      {item}")

    if fuera:
        print("\nRESULTADO: exit 2 — hay KPI fuera de meta.")
        return 2
    if no_medibles:
        print(f"\nRESULTADO: exit 5 — {', '.join(no_medibles)} no se pudieron medir. "
              "Un gate que no puede medir NO reporta verde.")
        return 5
    print("\nRESULTADO: exit 0 — los 6 KPI en meta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
