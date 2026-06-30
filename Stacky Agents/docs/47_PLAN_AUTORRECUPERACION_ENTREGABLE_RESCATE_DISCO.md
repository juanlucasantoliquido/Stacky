# Plan 47 — Auto-Recuperación Determinística del Entregable (rescate del disco antes de regenerar)

> **Estado: IMPLEMENTADO 2026-06-19.** Evidencia:
> - F0/F1 módulo: `backend/services/artifact_rescue.py:21` (`find_rescued_html` con `min_mtime`), `:75` (`resolve_outputs_dir`).
> - F2 enganche: `backend/api/tickets.py:5697-5736` (rescate antes de `epic_not_in_output`, flag `STACKY_ARTIFACT_RESCUE_ENABLED`); firma `run_started_at` en `:5670`.
> - F2bis: `backend/services/claude_code_cli_runner.py:1193-1202` (pasa `run_started_at=spawn_epoch`, solo path épica).
> - F3 NamedTuple `recovery_method`: `tickets.py:5661`; sello `metadata["epic_recovery"]`: `claude_code_cli_runner.py:1219-1221`.
> - F4 flag: `backend/services/harness_flags.py` (FlagSpec `STACKY_ARTIFACT_RESCUE_ENABLED`, env_only) + `.env.example`.
> - Tests verdes: `test_artifact_rescue.py` 11, `test_autopublish_rescue.py` 11, `test_harness_flags.py` (caso nuevo), regresión `test_epic_autopublish_backend.py`+`test_epic_narration_guard.py` 18. Total 58/58, 0 fallos.

> **Estado original: PROPUESTO (no implementado) — v2.** Reemplaza al plan 47 anterior ("Veredicto humano → memoria"),
> RECHAZADO por el operador por incremental (capturaba notas humanas que casi nunca existen + agregaba
> botones = pasos nuevos, prohibido por la lección del plan 41).
>
> ## v1 → v2 (CHANGELOG)
> Reescrito tras crítica adversarial verificada contra el código (`tickets.py`, `claude_code_cli_runner.py`,
> `runtime_paths.py`). Cambios:
> - **C1 (BLOQUEANTE):** corregida la afirmación FALSA de "paridad 3 runtimes". El único llamante de
>   producción de `autopublish_epic_from_run` es `_maybe_autopublish_epic` en
>   `claude_code_cli_runner.py:1163` (solo runtime Claude CLI, gated por `agent_type=="business"` +
>   `_one_shot`). Codex/Copilot NO invocan el autopublish hoy → el rescate hereda esa cobertura, no la
>   amplía. Reescrito el KPI, el principio 4 y el glosario para reflejarlo honestamente.
> - **C2 (BLOQUEANTE):** `_AutopublishResult` es un **`NamedTuple`** (`tickets.py:5647`), NO un `@dataclass`.
>   F3 reescrito: se agrega `recovery_method` como campo NamedTuple con default; el sello de
>   `metadata["epic_recovery"]` se hace en el llamante EXACTO `claude_code_cli_runner.py:1208-1219`.
> - **C3 (IMPORTANTE):** `repo_root()` nunca devuelve `None` (firma `-> Path`, sentinel inexistente). F1
>   elimina el `if root is None`; la única validación válida es `out.exists() and out.is_dir()`.
> - **C4 (IMPORTANTE) + [ADICIÓN ARQUITECTO]:** ventana temporal de rescate (`min_mtime = run_started_at`)
>   AHORA es parte del MVP (no "futuro"). Cierra R-STALE de raíz: solo se rescatan artefactos escritos
>   DURANTE esta run, no épicas viejas del mismo proyecto. Default seguro: sin timestamp → no rescatar.
> - **C5 (IMPORTANTE):** documentado el layout real `Agentes/outputs/epic-<id>/<rf>/` y que la épica
>   one-shot aún no tiene `epic-<id>`; combinado con C4 (min_mtime) se acota el barrido.
> - **C6/C7/C8 (MENOR):** test de flag verifica `env_only`; F2 aclara que NO hay `return` tras rescatar
>   (cae al bloque de publicación existente, `tickets.py:5708`); conteos de tests consolidados.

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El bug #1 recurrente y más frustrante de Stacky en Pacífico —"el agente crea
archivos pero no la task en ADO" / "brief→épica nunca crea el ticket"— tiene una causa raíz precisa y
documentada: el agente **SÍ escribe el HTML de la épica en disco** (`Agentes/outputs/`), pero su mensaje
final (`output`/last_message) es **narración**, así que el backend ve `produced_files=[]`, falla con
`epic_not_in_output` (`backend/api/tickets.py:5697`) y degrada a `needs_review` — dejando al operador
varado. Hoy lo único que intenta recuperar es un **reintento ciego de UN tiro** (`epic_repair`,
`backend/services/claude_code_cli_runner.py:893-930`) que (a) **re-genera** en vez de **rescatar** lo que
ya existe en disco, (b) **solo existe en el runtime Claude CLI** (no en Codex ni Copilot), y (c) si falla,
muere. Este plan agrega una **escalera de recuperación determinística y agnóstica al runtime**, invisible
al operador: ante `epic_not_in_output`, **(1) RESCATA** el HTML del último artefacto válido en disco que el
agente ya escribió, **(2) lo valida** con `_looks_like_epic` y, solo si no hay nada rescatable, **(3) cae**
al `epic_repair` existente. El rescate es puro filesystem → funciona idéntico en los 3 runtimes.

**KPI/impacto.** Tasa de `epic_not_in_output` que se resuelve **sin intervención del operador**. **Alcance
honesto (C1):** el rescate engancha en `autopublish_epic_from_run`, cuyo ÚNICO llamante de producción es
`_maybe_autopublish_epic` (`claude_code_cli_runner.py:1163`, gated por `STACKY_EPIC_AUTOPUBLISH_BACKEND` +
`_one_shot` + `agent_type=="business"`). Es decir: hoy el autopublish brief→épica **solo corre bajo el
runtime Claude CLI**; Codex y Copilot NO lo invocan. Por tanto el rescate **hereda exactamente esa
cobertura** — NO amplía la recuperación a Codex/Copilot (eso requeriría enganchar el autopublish en sus
finalizadores, lo cual es **scope futuro explícito**, fuera de este plan). Lo que SÍ aporta dentro del path
Claude CLI: dejar de regenerar (epic_repair quema tokens) cuando el artefacto YA EXISTE en disco. Telemetría
nueva `metadata["epic_recovery"]` con el método que resolvió (`rescued_from_disk` / `published_inline` /
`None`), consumible por el panel de salud (plan 46). Con el flag OFF, comportamiento byte-idéntico al actual.

**Ajuste tras verificación de código (cabecera honesta).** El gap **NO está cubierto**, pero las piezas
para cerrarlo **YA EXISTEN** y este plan las **reusa, no reinventa**:
- `autopublish_epic_from_run` (`backend/api/tickets.py:5663`) ya detecta narración y devuelve el error
  `epic_not_in_output` (`:5697-5706`) con `skipped=False` → el llamante degrada a `needs_review`. **Punto
  exacto de enganche del rescate.**
- `_extract_epic_html` + `_looks_like_epic` (`backend/api/tickets.py:5439`) ya validan forma de épica. El
  rescate los **reusa** sobre el contenido del archivo, no sobre `output`.
- `_collect_produced_files(output_dir)` (`backend/agent_runner.py:60`) ya escanea recursivamente un dir y
  devuelve paths de archivos. El rescate **reusa el mismo patrón** para enumerar candidatos.
- `repo_root()` (`backend/runtime_paths.py:99`) resuelve, **agnóstico al runtime y frozen-safe**, el root
  donde el agente escribe `Agentes/outputs` (override `STACKY_REPO_ROOT`, workspace del proyecto activo, o
  layout de fuentes). **Es la base del rescate; no se inventa ninguna ruta nueva.**
- `epic_repair` (`backend/services/claude_code_cli_runner.py:893-930`) es el reintento in-stream existente
  → este plan lo deja como **último escalón** (no lo toca; solo lo precede con el rescate).

Por tanto el plan **(i)** agrega un módulo puro de rescate que enumera `Agentes/outputs`, ordena por mtime
y devuelve el HTML del candidato más reciente que pasa `_looks_like_epic`; **(ii)** lo invoca dentro de
`autopublish_epic_from_run` ANTES de devolver `epic_not_in_output`; **(iii)** sella telemetría del método de
recuperación. No toca el modal/selector/runner de épicas (plan 42/43), ni el observatorio (44), ni el
catálogo (45), ni el panel (46): lo **alimenta**.

---

## 2. Por qué ahora / gap (apoyado en 41-46)

- **Lección del plan 41 (DESCARTADO):** prohibido todo lo que ponga al humano en un gate/click/decisión
  nueva, AUNQUE sea opt-in. Calidad SÍ, pasos nuevos NO. Este plan es **calidad 100% invisible**: ocurre
  dentro de la publicación que el operador ya disparó; cero pasos nuevos.
- **Plan 46** (Panel de Salud) LISTA runs en `needs_review` por `epic_publish_error`, pero es **pasivo**:
  muestra el fallo, no lo resuelve. Este plan REDUCE cuántas runs llegan a ese bucket.
- **Plan 44** (observatorio de grounding) OBSERVA; no recupera.
- **Causa raíz documentada** (`epic-brief-ado-not-created-root-cause`): *"ESCRIBIÓ/revisó un archivo en
  disco... su mensaje final fue narración. produced_files=[]"*. El reintento actual quema tokens
  regenerando algo que **ya está en disco**. Ningún plan 41-46 RESCATA el artefacto existente.
- El reintento `epic_repair` actual vive solo en `claude_code_cli_runner.py:893`. **Pero el autopublish que
  dispara el error tampoco corre fuera de Claude CLI** (`_maybe_autopublish_epic`, `:1163`). Por tanto, hoy,
  Codex/Copilot ni siquiera autopublican épicas → no llegan a `epic_not_in_output`. El rescate por filesystem
  es agnóstico al runtime POR DISEÑO (puro `Agentes/outputs` vía `repo_root()`), de modo que el día que se
  enganche el autopublish en Codex/Copilot (scope futuro), el rescate funcionará idéntico sin cambios. **No
  obstante, en este plan el beneficio observable es solo en el path Claude CLI** (C1). No se inventa paridad
  inexistente.

---

## 3. Principios y guardarraíles (codificados por fase)

1. **Invisible al operador:** el rescate ocurre dentro de `autopublish_epic_from_run`, que ya corre solo al
   cerrar la run. Cero pasos nuevos, cero config obligatoria. (Riel del plan 41.)
2. **Human-in-the-loop:** el rescate NO decide ni aprueba; solo **encuentra y entrega** el HTML que el
   agente ya produjo, sujeto a la misma validación `_looks_like_epic`. Si nada pasa la validación, NO
   publica nada y degrada igual que hoy (el operador sigue en el lazo). Prohibida la autonomía proactiva.
3. **Determinístico, implementable por modelo menor:** "enumerá archivos bajo outputs, ordená por mtime
   desc, leé el más reciente que pase `_looks_like_epic`, devolvelo". Sin IA, sin ambigüedad.
4. **Agnóstico al runtime POR DISEÑO, pero cobertura = la del autopublish actual (C1):** el rescate es
   **puro filesystem** (lee `Agentes/outputs` vía `repo_root()`), así que es idéntico para los 3 runtimes
   *cuando se lo invoca*. HOY el autopublish que lo invoca corre solo bajo Claude CLI
   (`_maybe_autopublish_epic`, `:1163`). Enganchar el autopublish en Codex/Copilot es **scope futuro
   explícito**. No se afirma paridad que el código no tiene.
4bis. **Ventana temporal de rescate (R-STALE, [ADICIÓN ARQUITECTO]):** el rescate SOLO considera artefactos
   cuyo `mtime > run_started_at`. Así nunca publica una épica VIEJA del mismo proyecto. Sin timestamp de
   inicio → no se rescata (default seguro). Ver F0/F2.
5. **Mono-operador sin auth:** no toca usuarios ni RBAC.
6. **No degradar:** flag default OFF; rescate envuelto en try/except best-effort → si falla, cae al
   comportamiento actual exacto (devuelve `epic_not_in_output`). Reusa `_looks_like_epic` /
   `_collect_produced_files` / `repo_root`; no reinventa rutas ni validación.

---

## 4. Fases

> Entorno de tests (TODAS las fases backend):
> Intérprete: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe`
> cwd: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> Correr **por archivo** (full-suite contaminada): `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`
> Frontend: `npx tsc --noEmit` desde `Stacky Agents/frontend` (no hay vitest). Este plan NO toca frontend.

---

### F0 — Módulo puro de rescate del disco (sin I/O de red, sin Flask)

**Objetivo (1 frase).** Crear un módulo que, dado un directorio de outputs, devuelva el HTML del archivo
más reciente que parece una épica/issue válida, o `None`.
**Valor.** Núcleo determinístico del rescate, testeable en memoria con archivos temporales; agnóstico al
runtime (solo filesystem).

**Archivo a CREAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\artifact_rescue.py`

**Contenido EXACTO (módulo casi puro: solo lee archivos locales que se le pasan):**
```python
"""F0 (plan 47) — Rescate determinístico del entregable desde el disco.

Causa raíz (epic-brief-ado-not-created): el agente ESCRIBE el HTML de la épica
en `Agentes/outputs/` pero su `output` (last_message) es narración, así que el
backend ve produced_files=[] y degrada a needs_review aunque el artefacto EXISTA.

Este módulo busca en un directorio de outputs el archivo más reciente cuyo
contenido pasa un validador de forma (inyectado: `_looks_like_epic`), y devuelve
su HTML extraído. PURO respecto de red/DB/Flask: solo lee archivos del disco.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

# Extensiones candidatas: el agente escribe HTML o markdown con el bloque ```html.
_CANDIDATE_SUFFIXES = (".html", ".htm", ".md", ".txt")
_MAX_BYTES = 512_000  # 500 KB: una épica nunca es más grande; evita leer binarios enormes.


def find_rescued_html(
    output_dir: Path | str | None,
    *,
    extract: Callable[[str | None], str],
    looks_valid: Callable[[str | None], bool],
    min_mtime: float | None = None,
) -> str | None:
    """Devuelve el HTML del artefacto más reciente y válido bajo output_dir, o None.

    - output_dir None / inexistente → None (caller cae al comportamiento actual).
    - Recorre archivos candidatos por extensión, ORDENADOS por mtime DESC (recursivo:
      el layout real es `Agentes/outputs/epic-<id>/<rf>/...`, ver nota de layout abajo).
    - min_mtime (C4/R-STALE): si se pasa, se IGNORA todo archivo con mtime <= min_mtime.
      En producción min_mtime = run_started_at (epoch float) → solo se rescata lo que
      el agente escribió DURANTE esta run, nunca una épica vieja del proyecto.
    - Para cada uno: lee texto (utf-8, errors='ignore'), aplica extract() y
      looks_valid(). Devuelve el primero válido (= el más reciente válido).
    - Best-effort: cualquier excepción por archivo se ignora y se sigue.

    `extract` y `looks_valid` se INYECTAN (en producción: api.tickets._extract_epic_html
    y _looks_like_epic) para no acoplar este módulo a api.tickets ni crear import circular.
    """
    if output_dir is None:
        return None
    base = Path(output_dir)
    if not base.exists() or not base.is_dir():
        return None
    candidates = []
    for f in base.rglob("*"):
        if not (f.is_file() and f.suffix.lower() in _CANDIDATE_SUFFIXES):
            continue
        try:
            st = f.stat()
        except Exception:  # noqa: BLE001
            continue
        # C4/R-STALE: descartar artefactos anteriores al inicio de la run.
        if min_mtime is not None and st.st_mtime <= min_mtime:
            continue
        candidates.append((st.st_mtime, st.st_size, f))
    # Más reciente primero: el último entregable escrito gana.
    candidates.sort(key=lambda t: t[0], reverse=True)
    for _mtime, size, f in candidates:
        try:
            if size > _MAX_BYTES:
                continue
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        html = extract(raw)
        if looks_valid(html):
            return html
    return None
```

> **Nota de layout (C5).** `Agentes/outputs` NO es plano: el modo task usa
> `Agentes/outputs/epic-<id>/<rf>/...` (`output_watcher.py`, `stacky_mcp_tools.py:196`). El HTML de la épica
> one-shot (brief→épica) se escribe ANTES de que exista `epic-<id>`, así que cae suelto bajo `outputs/` o un
> subdir temporal. Por eso el barrido es `rglob` (recursivo) pero acotado por (a) `min_mtime > run_started_at`
> (C4: descarta cualquier `epic-<id>/` viejo) y (b) `_looks_like_epic` (descarta los `.json` de tasks, que
> además no son suffix candidato). Combinados, el riesgo de rescatar un artefacto ajeno es nulo en la práctica.

**Tests PRIMERO.** Archivo a CREAR: `backend\tests\test_artifact_rescue.py`
> Usar `tmp_path` (fixture pytest) para crear archivos. Inyectar `extract`/`looks_valid` falsos
> deterministas (no importar api.tickets en F0): `extract = lambda s: s` y
> `looks_valid = lambda h: bool(h) and "RF-" in h and "<h1" in h`.
Casos:
- `test_no_dir_returns_none` → `find_rescued_html(None, extract=..., looks_valid=...)` → `None`.
- `test_empty_dir_returns_none` → dir vacío → `None`.
- `test_returns_valid_html` → un archivo `ep.html` con `"<h1>Épica</h1>...RF-01..."` → devuelve ese HTML.
- `test_picks_most_recent_valid` → dos archivos válidos con mtime distinto (usar `os.utime`) → devuelve el
  del mtime mayor.
- `test_skips_invalid_files` → un archivo `notas.txt` con narración (sin `RF-`/`<h1`) + uno válido más
  viejo → devuelve el válido, ignora la narración aunque sea más nueva.
- `test_ignores_unreadable_or_huge` → un archivo > 500 KB válido en forma + uno chico válido → devuelve el
  chico (el grande se saltea por tamaño); y un binario `.bin` no candidato no rompe.
- `test_only_candidate_suffixes` → un `.json` válido en forma se ignora (no es suffix candidato) → `None` si
  es el único.
- `test_min_mtime_excludes_stale` (C4/R-STALE) → dos archivos válidos: uno viejo (`os.utime` con mtime
  `t0-100`) y uno nuevo (`t0+100`); llamar `find_rescued_html(..., min_mtime=t0)` → devuelve SOLO el nuevo.
  Y con `min_mtime=t0+200` (posterior a ambos) → `None` (nada escrito durante la run).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_artifact_rescue.py -q`
**Criterio de aceptación BINARIO.** 8 passed, 0 failed.
**Flag que la protege.** Ninguno (módulo inerte hasta que F2 lo invoque).
**Impacto por runtime.** Ninguno (no toca runtime; solo filesystem). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F1 — Resolver el directorio de outputs por proyecto (reuso de `repo_root`, frozen-safe)

**Objetivo (1 frase).** Exponer una función que devuelva el `Path` de `Agentes/outputs` para el proyecto
activo, reusando `runtime_paths.repo_root()`, sin inventar rutas.
**Valor.** Punto único y agnóstico al runtime que F2 usa para saber DÓNDE buscar; honra override de tests
(`STACKY_REPO_ROOT`) y deploy congelado.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\artifact_rescue.py`
**Agregar (al módulo de F0):**
```python
def resolve_outputs_dir() -> Path | None:
    """Devuelve <repo_root>/Agentes/outputs si existe, o None.

    Reusa runtime_paths.repo_root() (override STACKY_REPO_ROOT > workspace del
    proyecto activo > layout de fuentes; frozen-safe). NO inventa rutas: la
    convención `Agentes/outputs` es la misma que documenta runtime_paths.repo_root.

    OJO (C3): repo_root() tiene firma `-> Path` y NUNCA devuelve None: en deploy
    congelado sin proyecto activo devuelve un *sentinel inexistente*
    (`_UNRESOLVED_REPO_ROOT`, runtime_paths.py:135). Por eso la única validación
    válida acá es `out.exists() and out.is_dir()` — NO `if root is None`.
    """
    try:
        from runtime_paths import repo_root  # lazy: evita import en contextos sin proyecto
        root = repo_root()
    except Exception:  # noqa: BLE001
        return None
    out = Path(root) / "Agentes" / "outputs"
    return out if out.exists() and out.is_dir() else None
```

**Casos borde.**
- `repo_root()` devuelve sentinel inexistente (deploy congelado sin proyecto activo, `runtime_paths.py:135`)
  → `out.exists()` es False → `None` (rescate se saltea, cae al comportamiento actual).
- `repo_root()` lanza (improbable, pero el lazy import o el módulo podría fallar) → `None` (no propaga).
- `STACKY_REPO_ROOT` seteado en tests → `repo_root()` lo respeta → `resolve_outputs_dir` apunta ahí.

**Tests PRIMERO.** Archivo a EDITAR: `backend\tests\test_artifact_rescue.py` (agregar casos).
> Patrón: `monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))`. Crear/omitir `tmp_path/Agentes/outputs`.
Casos:
- `test_resolve_outputs_dir_with_env` → setear `STACKY_REPO_ROOT=tmp_path`, crear `tmp_path/Agentes/outputs`
  → `resolve_outputs_dir()` devuelve ese Path.
- `test_resolve_outputs_dir_missing_returns_none` → `STACKY_REPO_ROOT=tmp_path` sin crear `Agentes/outputs`
  → `None`.
- `test_resolve_outputs_dir_repo_root_raises_returns_none` → monkeypatch `runtime_paths.repo_root` a una
  función que lanza → `None` (no propaga).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_artifact_rescue.py -q`
**Criterio de aceptación BINARIO.** 11 passed, 0 failed (8 de F0 + 3 de F1).
**Flag que la protege.** Ninguno (función inerte hasta F2).
**Impacto por runtime.** `repo_root()` abstrae frozen/fuentes y proyecto activo, sin distinguir quién corrió;
la función es agnóstica. Pero recordá (C1): quien la invoca (F2) solo corre bajo Claude CLI hoy. Fallback:
outputs no resoluble → `None` → comportamiento actual.
**Trabajo del operador:** ninguno.

---

### F2 — Enganchar el rescate en `autopublish_epic_from_run` ANTES de fallar (flag OFF)

**Objetivo (1 frase).** Cuando `_looks_like_epic(_extract_epic_html(output))` es False (narración), y el flag
está ON, intentar rescatar el HTML del disco; si se rescata, publicar ESE HTML; si no, devolver
`epic_not_in_output` exactamente como hoy.
**Valor.** Cierra el loop dentro del path Claude CLI (C1): el artefacto que el agente ya escribió en disco se
publica solo, sin tocar al operador, sin regenerar.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py`

**Paso 1 — agregar el kwarg `run_started_at` a la firma (C4, para min_mtime).** En
`autopublish_epic_from_run` (`tickets.py:5663`), agregar un parámetro opcional al final de la firma keyword:
```python
def autopublish_epic_from_run(
    *,
    output: str | None,
    brief: str,
    project_name: str | None,
    already_published_id: int | None,
    run_started_at: float | None = None,   # plan 47: epoch float; min_mtime del rescate. Default None = no rescatar por fecha.
) -> _AutopublishResult:
```
> Backward-compatible: default `None`. Los 14 call-sites de tests existentes no lo pasan y siguen verdes.

**Paso 2 — REEMPLAZAR el bloque del guard `:5697-5706`** (el `if not _looks_like_epic(...): return ...`):
```python
clean_html = _extract_epic_html(output)
if not _looks_like_epic(clean_html):
    # Plan 47 — Rescate del disco ANTES de fallar. El agente a veces ESCRIBE la
    # épica en Agentes/outputs y narra en el output → produced_files=[] pero el
    # artefacto EXISTE. Rescatarlo es más barato y robusto que regenerar.
    import os as _os  # NOTA: hay otro `import os as _os` más abajo (L5709). Dejar UNO solo
                      # (subir este, borrar el de abajo) para no sombrear. Verificar al editar.
    _rescue_enabled = _os.getenv(
        "STACKY_ARTIFACT_RESCUE_ENABLED", "false"
    ).lower() in {"1", "true", "on", "yes"}
    _rescued = None
    if _rescue_enabled:
        try:
            from services import artifact_rescue
            _rescued = artifact_rescue.find_rescued_html(
                artifact_rescue.resolve_outputs_dir(),
                extract=_extract_epic_html,
                looks_valid=_looks_like_epic,
                min_mtime=run_started_at,   # C4/R-STALE: solo artefactos de ESTA run
            )
        except Exception:  # noqa: BLE001
            logger.warning("artifact_rescue falló (no crítico)", exc_info=True)
            _rescued = None
    if _rescued and _looks_like_epic(_rescued):
        clean_html = _rescued
        _recovery_method = "rescued_from_disk"   # F3: se sella en el return de éxito
        # IMPORTANTE (C7): NO hay `return` acá. Se deja CAER al bloque existente de
        # abajo (grounding preflight L5708 + _publish_epic_to_ado L5722). No duplicar
        # la publicación: el flujo normal usa `clean_html`, que ya apunta al rescatado.
    else:
        return _AutopublishResult(
            ado_id=None,
            error=(
                "epic_not_in_output: el agente devolvió narración en vez del HTML de "
                "la épica (probablemente la escribió en un archivo). Revisar/reintentar "
                "la generación de la épica desde el brief."
            ),
            skipped=False,
        )
else:
    _recovery_method = "published_inline"   # F3: output ya era épica
```
> **C7 — anclaje exacto.** Tras reasignar `clean_html`, el control sigue en el código existente
> (`tickets.py:5708` grounding preflight → `:5722` `_publish_epic_to_ado` → `:5752` return de éxito). El
> único cambio en ese return es sellar `recovery_method=_recovery_method` (F3). NO se agrega un segundo
> `_publish_epic_to_ado`.

**Aclaración crítica.** El rescate NO publica nada que no pase `_looks_like_epic` (doble validación: en
`find_rescued_html` y de nuevo acá). Si el flag está OFF o no hay nada rescatable, la función devuelve
**exactamente** el mismo `_AutopublishResult(epic_not_in_output)` de hoy → comportamiento byte-idéntico.

**Casos borde.**
- Flag OFF → `_rescued=None` → camino actual exacto.
- Flag ON, sin outputs dir resoluble → `find_rescued_html(None,...)` → `None` → camino actual.
- Flag ON, `run_started_at=None` (no se pasó) → todo artefacto tiene `mtime <= None`? **NO**: con
  `min_mtime=None` el filtro de fecha se DESACTIVA (mtime DESC puro). El llamante real (F2bis) SÍ pasa el
  timestamp; solo los tests que no lo pasan corren sin filtro de fecha (controlado por mocks).
- Flag ON, hay archivo válido reciente → publica ese HTML por el path normal de ADO (`_publish_epic_to_ado`).
- Flag ON, `artifact_rescue` lanza → log + `None` → camino actual (no rompe la publicación).
- El HTML rescatado sería de una épica VIEJA → `min_mtime=run_started_at` lo descarta (C4); la doble
  validación es defensa adicional. Ver Riesgos R-STALE.

**Paso 3 (F2bis) — pasar `run_started_at` desde el llamante real (C1, `claude_code_cli_runner.py:1193`).**
El único llamante de producción es `_maybe_autopublish_epic` (`claude_code_cli_runner.py:1163`). En la
llamada `_publish(output=..., brief=..., project_name=..., already_published_id=...)` (`:1193-1198`), agregar
`run_started_at=<epoch de inicio de la run>`. **Verificación previa OBLIGATORIA (citar en PR):** localizar
en ese scope la variable de inicio de run (p. ej. `run_start`, `_started_at`, o derivar de la fila de
`Execution`); si no existe una accesible, capturar `time.time()` al entrar al runner y pasarla. Si NO hay
forma segura de obtener el inicio → pasar `run_started_at=None` (default seguro: rescate por mtime DESC sin
ventana, comportamiento idéntico a v1; documentar el riesgo R-STALE residual). **Nota:** `publish_issue_from_run`
(`tickets.py:5878`) NO recibe rescate en este plan (MVP = épica; ver Fuera de scope).

**Tests PRIMERO.** Archivo a CREAR: `backend\tests\test_autopublish_rescue.py`
> Parchear en su módulo origen: `services.artifact_rescue.resolve_outputs_dir` y
> `services.artifact_rescue.find_rescued_html`, y `api.tickets._publish_epic_to_ado` (para no tocar ADO).
> Mockear `_publish_epic_to_ado` devolviendo un objeto con `.ado_id=123` y `.url="http://x"`.
Casos:
- `test_rescue_disabled_returns_epic_not_in_output` → flag unset, `output="narración sin épica"` →
  `_AutopublishResult.error` empieza con `"epic_not_in_output"`, `ado_id is None`, `skipped is False`.
  `find_rescued_html` NO invocado (assert_not_called).
- `test_rescue_enabled_with_disk_artifact_publishes` → `monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED","true")`,
  `find_rescued_html` mock devuelve `"<h1>E</h1>...<h2>RF-01..."`, `_publish_epic_to_ado` mock OK →
  resultado `ado_id==123`, `error is None`, `skipped is False`.
- `test_rescue_enabled_no_artifact_falls_back_to_error` → flag ON, `find_rescued_html` devuelve `None` →
  `error` empieza con `"epic_not_in_output"`.
- `test_rescue_enabled_but_rescued_invalid_falls_back` → flag ON, `find_rescued_html` devuelve `"hola"`
  (no pasa `_looks_like_epic`) → `epic_not_in_output` (doble validación lo descarta).
- `test_rescue_exception_falls_back_safely` → flag ON, `find_rescued_html` mock lanza Exception →
  `epic_not_in_output`, no propaga, logger.warning registrado.
- `test_already_published_skips_rescue` → `already_published_id=99` → `skipped is True`, `ado_id==99`,
  `find_rescued_html` NO invocado (el guard de idempotencia, `tickets.py:5685`, gana primero).
- `test_valid_output_does_not_trigger_rescue` → `output` YA es épica válida (pasa `_looks_like_epic`) → se
  publica sin invocar `find_rescued_html` (camino feliz intacto).
- `test_run_started_at_passed_as_min_mtime` (C4) → flag ON, `find_rescued_html` mock; llamar
  `autopublish_epic_from_run(..., run_started_at=12345.0)` → assert que el mock recibió `min_mtime==12345.0`
  (usar `find_rescued_html.assert_called_once_with(... min_mtime=12345.0)` o inspeccionar `call_args.kwargs`).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_autopublish_rescue.py -q`
**Criterio de aceptación BINARIO.** 8 passed, 0 failed.
**Flag que la protege.** `STACKY_ARTIFACT_RESCUE_ENABLED` (bool, default `false`). Default seguro: OFF →
comportamiento idéntico al actual.
**Impacto por runtime (CORREGIDO C1).**
- **Claude Code CLI**: ES el único runtime donde el autopublish corre hoy (`_maybe_autopublish_epic`,
  `:1163`, gated por `agent_type=="business"` + `_one_shot`). Acá el rescate aporta beneficio observable.
- **Codex CLI / GitHub Copilot Pro**: HOY NO invocan `autopublish_epic_from_run` → el rescate no se ejecuta
  para ellos (no quedan ni mejor ni peor; siguen como hoy). Enganchar el autopublish en sus finalizadores es
  **scope futuro**; cuando se haga, el rescate (filesystem puro) funcionará sin cambios.
- Fallback general: si el runtime no escribe a `Agentes/outputs` o no hay artefacto reciente →
  `find_rescued_html` → `None` → `epic_repair`/`epic_not_in_output` actual. Ningún runtime queda peor.
**Trabajo del operador:** ninguno (opt-in vía flag; default off = sin cambios).

---

### F3 — Telemetría del método de recuperación (sellar `metadata["epic_recovery"]`)

**Objetivo (1 frase).** Sellar en el resultado/metadata QUÉ método resolvió la publicación
(`rescued_from_disk` / `published_inline` / `None` si no se publicó) para que el panel de salud (plan 46) lo lea.
**Valor.** Visibilidad sin trabajo: el operador (o el panel pasivo) ve cuántas épicas se auto-rescataron.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py`

**CRÍTICO (C2): `_AutopublishResult` es un `NamedTuple` (`tickets.py:5647`), NO un `@dataclass`.** NO usar
`@dataclass`/`field(default_factory=...)` — rompería los call-sites posicionales y no existe `field` en
NamedTuple. Agregar el campo como atributo NamedTuple **con default** (los campos con default van AL FINAL):
```python
class _AutopublishResult(NamedTuple):
    ado_id: int | None
    error: str | None
    skipped: bool = False
    grounding_warnings: list = []  # type: ignore[assignment]
    epic_summary: dict | None = None
    recovery_method: str | None = None  # plan 47: "published_inline" | "rescued_from_disk" | None
```
> Como ya tiene campos con default (`skipped=False`, etc.), agregar `recovery_method` al final es seguro y
> backward-compatible: los returns existentes que no lo pasan reciben `None`.

**Poblar `recovery_method` en los `return` de `autopublish_epic_from_run`:**
- Return de éxito (`tickets.py:5752`): `recovery_method=_recovery_method` (variable de F2: `"published_inline"`
  o `"rescued_from_disk"`).
- Returns de `epic_not_in_output` / ADO error / skip: dejar el default `None` (no pasar el campo).

**El llamante REAL (C2, NO grep ciego): `_maybe_autopublish_epic` en `claude_code_cli_runner.py:1208-1219`.**
Ahí ya se sella `metadata[_seal_key]`, `metadata["grounding_warnings"]` y `metadata["epic_summary"]`. Agregar,
en el mismo bloque (después de `:1218`):
```python
if _res.recovery_method:
    metadata["epic_recovery"] = _res.recovery_method
```
> No usar el grep ciego de v1: el único llamante de producción ya está identificado
> (`claude_code_cli_runner.py:1163`, sella en `:1208-1219`). `publish_issue_from_run` no setea
> `recovery_method` (queda `None`), coherente con MVP = épica.

**Tests PRIMERO.** Archivo a EDITAR: `backend\tests\test_autopublish_rescue.py` (agregar casos).
Casos:
- `test_recovery_method_inline_on_valid_output` → output ya épica → `result.recovery_method=="published_inline"`.
- `test_recovery_method_rescued_on_disk_artifact` → rescate exitoso (flag ON, mock disk) →
  `result.recovery_method=="rescued_from_disk"`.
- `test_recovery_method_none_on_unrecoverable` → narración + sin rescate → `result.recovery_method is None`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_autopublish_rescue.py -q`
**Criterio de aceptación BINARIO.** 11 passed, 0 failed (8 de F2 + 3 de F3).
**Flag que la protege.** Mismo `STACKY_ARTIFACT_RESCUE_ENABLED` (el campo `recovery_method` es informativo;
con flag OFF nunca toma valor `rescued_from_disk`). Default seguro.
**Impacto por runtime.** Ninguno (campo informativo, agnóstico). Fallback: si el llamante no setea
metadata, el campo simplemente no aparece (no rompe nada).
**Trabajo del operador:** ninguno.

---

### F4 — Registrar el flag en el arnés (visible/togglable en UI existente)

**Objetivo (1 frase).** Declarar `STACKY_ARTIFACT_RESCUE_ENABLED` en `FLAG_REGISTRY` (plan 33) y
documentarlo en `.env.example`.
**Valor.** Gobernanza consistente: el operador ve y togglea el flag desde el panel de flags existente, sin
código nuevo de frontend.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\harness_flags.py`
**Agregar a `FLAG_REGISTRY` (después del último FlagSpec):**
```python
FlagSpec(
    key="STACKY_ARTIFACT_RESCUE_ENABLED",
    type="bool",
    label="Rescate de épica desde disco",
    description=("Plan 47 — Si ON, cuando el agente narra en vez de devolver el HTML "
                 "de la épica, el backend rescata el artefacto que el agente ya escribió "
                 "en Agentes/outputs y lo publica. Default OFF."),
    group="global",
    env_only=True,  # se lee con os.getenv en F2 → env_only=True (igual criterio que otros flags os.getenv)
),
```
> Nota: usar `env_only=True` porque F2 lee el flag con `os.getenv` (no como atributo de `Config`). En este
> repo, un FlagSpec no-env_only exige atributo en `Config`; si se quiere toggle-sin-restart vía atributo de
> Config, agregarlo en `config.py` y leerlo de ahí en F2. El default seguro NO cambia (OFF) en ningún caso.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.env.example`
```
# Plan 47 — rescatar el HTML de la épica desde Agentes/outputs cuando el agente narró en vez de devolverlo. Default OFF.
STACKY_ARTIFACT_RESCUE_ENABLED=false
```

**Tests PRIMERO.** Archivo a EDITAR: `backend\tests\test_harness_flags.py`
Caso a agregar:
- `test_artifact_rescue_flag_registered` → buscar en `FLAG_REGISTRY` un FlagSpec con
  `key=="STACKY_ARTIFACT_RESCUE_ENABLED"`, `type=="bool"`, `group=="global"`, `env_only is True` (C6).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q`
**Criterio de aceptación BINARIO.** El archivo pasa con el caso nuevo, 0 failed.
**Flag que la protege.** El propio flag se declara aquí. Default seguro: `false`.
**Impacto por runtime.** Ninguno (declarativo). Fallback: N/A.
**Trabajo del operador:** ninguno (solo expone el toggle).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **R-STALE**: rescatar una épica VIEJA del mismo proyecto (no la de este brief) | **Mitigación AHORA en MVP (C4/[ADICIÓN ARQUITECTO]):** `find_rescued_html(min_mtime=run_started_at)` descarta TODO artefacto con `mtime <= inicio de la run` → solo se rescata lo escrito DURANTE esta run. Si el llamante no logra obtener `run_started_at`, pasa `None` → degrada al mtime-DESC de v1 (riesgo residual documentado, pero el default seguro recomendado es no rescatar sin timestamp si el operador no confía). Defensa adicional: orden mtime DESC + doble `_looks_like_epic`. |
| Publicar narración basura como épica | Doble validación `_looks_like_epic`: en `find_rescued_html` y de nuevo en F2 antes de publicar. Si no pasa, NO publica. |
| El rescate rompe la publicación legacy | F2 envuelve todo en try/except; ante cualquier fallo cae al `epic_not_in_output` exacto de hoy. Flag default OFF. |
| Runtime que no escribe a `Agentes/outputs` (Codex/Copilot con otro cwd) | `find_rescued_html` no encuentra candidato → `None` → cae al `epic_repair`/error actual. Ningún runtime queda peor que hoy. |
| `repo_root()` no resoluble (deploy congelado sin proyecto activo) | `repo_root()` devuelve sentinel inexistente (`runtime_paths.py:135`), `out.exists()` es False → `resolve_outputs_dir` devuelve `None` → rescate se saltea (C3: NUNCA `if root is None`). |
| Leer archivos enormes/binarios del dir outputs | `_MAX_BYTES=500KB` + filtro por extensión candidata; `errors='ignore'` en lectura. |
| Doble publicación (rescate + handshake del frontend) | Guard de idempotencia preexistente: `already_published_id != None → skipped` (`tickets.py:5685`) corre ANTES del rescate. |

---

## 6. Fuera de scope (NO hacer)

- NO tocar el modal/selector de modelo/effort ni el runner de generación (plan 42/43).
- NO modificar el observatorio de grounding (44) ni el catálogo (45); solo se alimenta el panel (46) vía
  `metadata["epic_recovery"]`.
- NO agregar botones ni pasos nuevos al operador (lección plan 41).
- NO eliminar ni modificar el `epic_repair` in-stream existente (`claude_code_cli_runner.py:893-930`): queda
  como último escalón, intacto.
- NO migrar schema (todo en `metadata_json` + dataclass en memoria).
- NO disparar acciones automáticas más allá de publicar el artefacto YA producido por el agente (prohibida
  la autonomía proactiva: el rescate no genera contenido nuevo, solo entrega el que existe).
- NO generalizar todavía el rescate a tasks funcionales/issues (posible plan futuro; MVP = épica).

---

## 7. Glosario, orden de implementación, DoD

**Glosario (dominio Stacky).**
- **`autopublish_epic_from_run`**: función que publica la épica en ADO al cerrar la run (`tickets.py:5663`).
  Es un **`NamedTuple`** el que retorna (`_AutopublishResult`, `:5647`), NO un dataclass (C2).
- **`epic_not_in_output`**: error que indica que el `output` del agente es narración, no la épica
  (`tickets.py:5701`). El llamante degrada la run a `needs_review`.
- **`_looks_like_epic` / `_extract_epic_html`**: validador de forma de épica y extractor del bloque HTML
  (`tickets.py:5439`). Reusados, no reescritos.
- **`Agentes/outputs`**: convención de directorio donde el agente escribe sus artefactos; su root lo
  resuelve `runtime_paths.repo_root()` (`runtime_paths.py:99`), frozen-safe.
- **`epic_repair`**: reintento in-stream existente que pide re-emitir el HTML (solo Claude CLI,
  `claude_code_cli_runner.py:893`). Último escalón tras el rescate.
- **`produced_files`**: lista de archivos que el runner detectó (hoy a veces `[]` aunque el archivo exista).
- **3 runtimes**: Codex CLI, Claude Code CLI, GitHub Copilot Pro. **CORRECCIÓN C1:** HOY solo Claude CLI
  invoca `autopublish_epic_from_run` (vía `_maybe_autopublish_epic`, `claude_code_cli_runner.py:1163`).
  Codex/Copilot NO lo invocan. El rescate es filesystem agnóstico, pero su cobertura efectiva = la del
  autopublish actual (Claude CLI). No afirmar paridad inexistente.
- **`run_started_at`**: epoch float del inicio de la run, pasado del runner a `autopublish_epic_from_run`
  como `min_mtime` del rescate (C4/R-STALE). `None` = sin ventana temporal (default seguro).

**Orden de implementación (numerado, por dependencia).**
1. **F0** — módulo `artifact_rescue.find_rescued_html` (con `min_mtime`) + tests (sin dependencias).
2. **F1** — `artifact_rescue.resolve_outputs_dir` (reusa `repo_root`) + tests (depende de F0 en el archivo).
3. **F2** — kwarg `run_started_at` + enganche en `autopublish_epic_from_run` + F2bis (pasar timestamp desde
   `claude_code_cli_runner.py:1193`) + tests (depende de F0/F1).
4. **F3** — campo NamedTuple `recovery_method` + sello `epic_recovery` en `claude_code_cli_runner.py:1208-1219`
   + tests (depende de F2; llamante YA identificado, sin grep ciego — C2).
5. **F4** — registrar flag + `.env.example` + test (independiente; habilita F2/F3 en UI).

**Definición de Hecho (DoD) global — binaria.**
- [ ] `test_artifact_rescue.py` → 11 passed, 0 failed (F0 8 + F1 3).
- [ ] `test_autopublish_rescue.py` → 11 passed, 0 failed (F2 8 + F3 3).
- [ ] `test_harness_flags.py` → pasa con el caso nuevo (incl. `env_only is True`), 0 failed.
- [ ] Con `STACKY_ARTIFACT_RESCUE_ENABLED` unset (default), `autopublish_epic_from_run` ante narración
  devuelve `epic_not_in_output` byte-idéntico al actual (verificado por `test_rescue_disabled_*`).
- [ ] Con flag ON y un artefacto válido en `Agentes/outputs`, la épica se publica con
  `recovery_method=="rescued_from_disk"` (verificado por test con mock de disco y ADO).
- [ ] El rescate NUNCA publica algo que no pase `_looks_like_epic` (doble validación, verificado).
- [ ] Cualquier excepción del rescate cae al comportamiento actual sin propagar (verificado).
- [ ] `epic_repair` legacy y el path inline feliz no tienen regresión (correr `test_epic_narration_guard.py`
  y `test_epic_autopublish_backend.py` existentes → 0 failed).
- [ ] Sin migración de schema; sin cambios de frontend.
- [ ] R-STALE (C4): con `run_started_at` pasado, `find_rescued_html` ignora artefactos previos al inicio de
  la run (verificado por `test_min_mtime_excludes_stale` y `test_run_started_at_passed_as_min_mtime`).
- [ ] `_AutopublishResult` sigue siendo `NamedTuple` (C2): el campo `recovery_method` se agregó con default,
  los 14 call-sites existentes (incl. tests) siguen verdes sin pasarlo.
- [ ] Cobertura honesta (C1): el rescate corre bajo Claude CLI (único llamante hoy); Codex/Copilot no quedan
  peor. NO se afirma paridad de recuperación que el código no tiene.
