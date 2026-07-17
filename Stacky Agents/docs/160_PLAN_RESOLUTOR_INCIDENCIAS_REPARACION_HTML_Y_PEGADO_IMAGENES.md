# Plan 160 — Resolutor de Incidencias: reparación automática del desglose HTML + pegado de imágenes desde el portapapeles

**Estado:** IMPLEMENTADO F0-F1 (2026-07-17) — ver `plan-160-status.md`

## Versión: v1 -> v2 (crítica adversarial aplicada)

**CHANGELOG v1 -> v2:**
- **C1 (IMPORTANTE, resuelto):** el `onPaste` se mueve del div del paso intake al div raíz
  del modal (`styles.modal`, línea 260) con gate `step === "intake"` DENTRO del handler —
  el paste funciona con el foco en cualquier control del modal (header, footer, botón
  cerrar), no solo dentro del body del intake.
- **C2 (IMPORTANTE, resuelto):** `extractPastedImageFiles` ya NO defaultea a `.png` para
  MIME desconocidos: un MIME `image/*` fuera del allowlist (p.ej. `image/svg+xml`,
  `image/tiff`) se IGNORA. Renombrarlo a `.png` colaba por `validateFiles` (valida por
  extensión) contenido cuya extensión real el backend rechaza, y SVG es vector activo de
  scripting. Test nuevo agregado (7 casos frontend, no 6).
- **C3 (IMPORTANTE, resuelto):** eliminado el hedge "si `create_incident` no existe con
  esa firma...". Firma VERIFICADA contra el código: `create_incident(text: str, files:
  list[tuple[str, bytes]]) -> dict` (`services/incident_store.py:106`). Cero inferencia.
- **C4 (IMPORTANTE, resuelto):** documentada la interacción con el cierre one-shot: el
  runner cierra stdin apenas ve `_result_ok_seen` (runner `:1054-1055` -> `:1327-1334`)
  SIN considerar repair pendiente, con gracia de 20s (`:1335-1343`). El turno de reintento
  debe completar dentro de esa gracia. `sent: true` en metadata NO garantiza re-emisión
  completada — contrato aclarado en §4.0.2 y fila nueva en Riesgos (§5).
- **C5 (MENOR, resuelto):** precisiones literales: los comandos con `&&` se corren en
  Git Bash (NO PowerShell 5.1); la línea 1 de `incidentModel.test.ts`
  (`import { describe, it, expect } from "vitest";`) NO se toca al editar el bloque de
  imports.
- **C6 (MENOR, resuelto):** conteos de tests actualizados en criterios y DoD (backend 6,
  frontend 7) tras C2 y la adición del arquitecto.
- **C7 (MENOR, resuelto):** anotado que el campo `repair` del 422 de publish no tiene
  consumidor UI hoy (el modal maneja publish por excepción) — es diagnóstico para
  API/curl; prohibido removerlo en limpiezas futuras.
- **[ADICIÓN ARQUITECTO] Transparencia del repair exitoso:** cuando el reintento SÍ
  recupera el HTML, el operador se entera: `GET /incident-preview` OK ahora también
  devuelve `repair`, y el modal muestra una nota discreta en el paso preview ("Stacky
  detectó un fallo de formato y lo reparó automáticamente"). Cero acciones automáticas
  invisibles (coherente con Planes 134/135); test backend nuevo incluido.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los nombres de símbolos, las rutas, los
> literales de mensajes y los comandos son LITERALES: prohibido desviarse de los nombres
> exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido acá.
> Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1 `&&` es error de
> parser).

**Dependencias:** ninguna dura. Reusa: el guard anti-narración y el pase correctivo de
épica ya existentes (Plan 51 `harness/epic_gate.py`, fix robusto brief→épica
`claude_code_cli_runner.py:1006-1237`), el Resolutor de Incidencias (Plan 131,
`STACKY_INCIDENT_RESOLVER_ENABLED`, ya IMPLEMENTADO), y el pipeline de validación/subida
de archivos del modal (`incidentModel.ts::validateFiles`, `IncidentResolverModal.tsx::
handleFilesSelected`).
**Ortogonal a:** Plan 159 (catálogo unificado de modelos/efforts) — el selector de
modelo Claude del modal (`CLAUDE_MODELS` hardcodeado en
`IncidentResolverModal.tsx:26-30`) es candidato futuro a consumir ese catálogo, pero
esta fase NO lo toca ni lo reimplementa; queda fuera de scope (ver §6).

---

## 1. Objetivo + KPI

Dos incidencias reales reportadas por el operador sobre el mismo componente (el
Resolutor de Incidencias, botón "🚑 Resolver incidencia" en Tickets):

**Incidencia A (bug, prioridad alta):** al cargar una incidencia, el operador recibe
"El agente narró en vez de devolver el desglose HTML. Revisá la consola y reintentá."
Causa raíz confirmada: el agente de incidencias (`IncidentAgent`, prompt en
`backend/agents/incident.py`) a veces devuelve narración en prosa en vez del HTML
puro exigido, EXACTAMENTE el mismo fallo de forma que sufre el agente de épicas
(`BusinessAgent`) — pero a diferencia de épica, el resolutor de incidencias **no tiene
ningún pase correctivo**: el guard `_looks_like_incident()` (`api/tickets.py:6142-6154`)
solo detecta el fallo, nunca lo repara. El operador queda sin recurso salvo relanzar
todo el análisis desde cero.

**Incidencia B (feature):** el operador quiere pegar (Ctrl+V) una imagen copiada al
portapapeles directamente en el modal, en vez de tener que guardarla a disco primero y
usar el selector de archivos o drag&drop.

Este plan resuelve ambas en dos fases independientes del mismo componente:

- **F0** agrega un pase correctivo automático (reintento) al resolutor de incidencias,
  reusando EXACTAMENTE el patrón ya probado de `epic_repair` (fix robusto brief→épica),
  más diagnóstico accionable en la consola de ejecución y en la respuesta de preview/
  publish cuando el reintento no alcanza, y transparencia en el preview cuando el
  reintento SÍ alcanza ([ADICIÓN ARQUITECTO]).
- **F1** agrega pegado de imágenes desde el portapapeles al modal, reusando el mismo
  pipeline de validación/subida que ya usan drag&drop y el selector de archivos.

**KPI / impacto esperado:**
- Incidencia A: el porcentaje de análisis de incidencia que terminan en
  `incident_not_in_output` sin haber tenido oportunidad de auto-corregirse baja a 0 (todo
  fallo de forma pasa primero por el reintento automático, igual que ya ocurre en
  brief→épica desde el fix robusto de julio 2026). Cuando el reintento no alcanza, el
  operador ve en el modal que YA se reintentó (no repite el mismo intento a mano
  esperando un resultado distinto). Cuando el reintento alcanza, el operador ve que hubo
  una reparación automática (cero acciones invisibles).
- Incidencia B: 0 pasos manuales de "guardar captura a disco → abrir selector de
  archivos → buscarla" para adjuntar una captura de pantalla; Ctrl+V la agrega
  directamente.

---

## 2. Por qué ahora / gap que cierra

El Resolutor de Incidencias (Plan 131) quedó IMPLEMENTADO con paridad completa de
publish/preview/attachments/grafo documental, pero **nunca heredó** el mecanismo de
auto-reparación que el flujo hermano (brief→épica) sí tiene. Ambos agentes comparten el
mismo riesgo estructural (un LLM conversacional que a veces "explica lo que va a hacer"
en vez de devolver el artefacto pedido) y el mismo runtime (`claude_code_cli_runner.py`,
modo one-shot, `ado_id` en `_ONE_SHOT_ADO_IDS`). El gap no es de diseño nuevo: es que la
implementación de Plan 131 (2026-07-14) fue anterior/paralela al fix robusto de
brief→épica y no lo reusó. Cerrarlo es mecánico: mismo patrón, mismo runner, mismo
archivo, condición espejada por `agent_type`.

El pegado de imágenes es un gap de UX puro: el modal ya soporta 2 de 3 formas estándar
de adjuntar (drag&drop, selector de archivos) pero no la tercera (portapapeles), que es
la más rápida para el caso de uso real (el operador toma un screenshot y lo pega).

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad, degradación explícita donde ya hay precedente aceptado.**
  El pase correctivo de F0 vive DENTRO del wiring inline de `claude_code_cli_runner.py`
  (igual que `epic_repair`, `criteria_repair` y `run_repair`) — es decir, **Claude Code
  CLI-only por diseño ya aceptado en este repo** (ver comentario literal en
  `harness/epic_gate.py:9-11`: "El WIRING del pase correctivo inline es Claude-CLI-only
  ... Codex/Copilot degradan a needs_review"). F0 seguirá EXACTAMENTE ese mismo
  precedente: en Codex CLI y GitHub Copilot Pro, el resolutor de incidencias sigue
  funcionando igual que hoy (sin reintento automático, error `incident_not_in_output`
  visible), degradación YA aceptada por el repo para el mismo patrón en épica — no es una
  excepción nueva, es continuidad de una decisión ya tomada. F1 (pegado de imágenes) es
  100% frontend, no depende de runtime: funciona igual en los 3.
- **Cero trabajo extra para el operador.** F0 es invisible (reintento automático antes de
  que el operador vea nada) y su flag `STACKY_INCIDENT_REPAIR_ENABLED` viene default
  **ON** (mismo patrón que `STACKY_EPIC_REPAIR_ENABLED`, sin excepción dura aplicable: no
  bypasea revisión humana — el HTML reparado sigue pasando por preview+confirm antes de
  publicar —, no es destructivo, no depende de un prerequisito no garantizado, no reduce
  seguridad). F1 es invisible/automático: pegar una imagen simplemente funciona, sin
  configuración, sin flag nueva (es puro frontend, gateado por el flag ya existente
  `STACKY_INCIDENT_RESOLVER_ENABLED` que ya protege todo el modal).
- **Human-in-the-loop innegociable.** El reintento de F0 es "el agente vuelve a intentar
  ANTES de mostrarle el resultado al operador para su revisión" — nunca auto-publica.
  El botón "Publicar" sigue exigiendo `confirm:true` explícito del operador
  (`api/tickets.py:7391-7397`, sin cambios). F0 NO toca esa exigencia. Además, toda
  reparación automática queda VISIBLE para el operador ([ADICIÓN ARQUITECTO], §4.0.6):
  ninguna acción automática es invisible.
- **Mono-operador sin auth real.** Nada de RBAC. No aplica a ninguna de las dos fases.
- **No degradar. Reusar, no reinventar.** F0 reusa el patrón `epic_repair` símbolo por
  símbolo (mismas variables shadow, mismo presupuesto de reintentos, mismo
  `_send_system_message`, mismo lugar de sellado en `metadata`). F1 reusa
  `handleFilesSelected`/`validateFiles` — CERO lógica de validación nueva. F0 NO agrega
  superficie XSS nueva: el HTML reparado fluye por el MISMO pipeline
  `_extract_epic_html_raw` → preview → `dangerouslySetInnerHTML`
  (`IncidentResolverModal.tsx:376-380`) que el HTML de primer intento — superficie
  preexistente del Plan 131, sin cambios de sanitización en este plan.

---

## 4. Fases

### F0 — Pase correctivo automático del resolutor de incidencias + diagnóstico accionable

**Objetivo en 1 frase:** cuando el agente de incidencias narra en vez de HTML, Stacky le
pide UNA vez que re-emita el HTML antes de cerrar la sesión (mismo patrón que
brief→épica), y el operador SIEMPRE se entera del desenlace: si el reintento no alcanzó,
lo ve con evidencia concreta; si alcanzó, ve que hubo reparación automática.

**Valor:** convierte un error duro sin recurso en un fallo autocorregible en la mayoría de
los casos (mismo comportamiento que ya redujo esta clase de error en brief→épica), y
cuando no se autocorrige, el mensaje deja de ser engañoso ("revisá la consola" ahora
tiene algo real que mostrar).

**Runtime:** Claude Code CLI (mecanismo activo). Codex CLI / GitHub Copilot Pro:
degradación explícita a comportamiento actual sin cambios (mismo precedente que
`epic_repair`, ver §3). No hay trabajo a implementar en `codex_cli_runner.py` ni en el
runner de Copilot para esta fase — su comportamiento no cambia.

**Flag:** `STACKY_INCIDENT_REPAIR_ENABLED`, tipo `bool`, **default `true`**. Sin excepción
dura aplicable (ver §3). Sin entrada en `services/harness_flags.py` (sin `FlagSpec`, sin
panel de operador) — **precedente literal**: `STACKY_EPIC_REPAIR_ENABLED`
(`config.py:964-966`) tampoco tiene `FlagSpec` en `harness_flags.py` (verificado por
grep: cero coincidencias). Es un kill-switch interno env-only, igual que su hermano.
**NO agregues** una entrada `FlagSpec` para esta flag — haría inconsistente el par con
`STACKY_EPIC_REPAIR_ENABLED` y no lo exige ningún test existente.

**Trabajo del operador: ninguno.**

#### Archivos a editar (ninguno nuevo salvo el test)

1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/claude_code_cli_runner.py`
3. `Stacky Agents/backend/api/tickets.py`
4. `Stacky Agents/backend/tests/test_incident_repair_guard.py` (NUEVO)
5. `Stacky Agents/backend/scripts/run_harness_tests.sh`
6. `Stacky Agents/frontend/src/incidents/incidentModel.ts`
7. `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`

#### 4.0.1 — `backend/config.py`: nueva flag

Ubicá el bloque existente (líneas 960-966 en la versión actual del archivo, puede haber
corrido — ubicalo por el símbolo `STACKY_EPIC_REPAIR_ENABLED`):

```python
    STACKY_EPIC_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_EPIC_REPAIR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

Inmediatamente DESPUÉS de ese bloque (antes del siguiente comentario `# C0/C1 —
Trazabilidad...`), insertá:

```python
    # Plan 160 F0 — pase correctivo del resolutor de incidencias: si el
    # IncidentAgent (one-shot, ado_id=-8) devuelve narración en vez del HTML
    # del desglose, se le pide UNA vez por stdin que re-emita SOLO el HTML
    # antes de cerrar la sesión. Espejo de STACKY_EPIC_REPAIR_ENABLED. Reusa
    # el presupuesto de reintentos del autocorrect. OFF -> solo fallo ruidoso
    # (incident_not_in_output), sin retry.
    STACKY_INCIDENT_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_REPAIR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

#### 4.0.2 — `backend/services/claude_code_cli_runner.py`: el pase correctivo

**Paso A.** Ubicá (por el símbolo `_epic_repair_done`, cerca de la línea 1009-1010):

```python
        _epic_repair_result: list[dict | None] = [None]       # [0] = meta o None
        _epic_repair_done: list[bool] = [False]               # flag mutable para closure
```

Inmediatamente DESPUÉS, agregá:

```python
        # Plan 160 F0 — pase correctivo del resolutor de incidencias (flag ON
        # default). Espejo de _epic_repair_result/_epic_repair_done, gateado
        # por agent_type=="incident" en vez de "business".
        _incident_repair_result: list[dict | None] = [None]
        _incident_repair_done: list[bool] = [False]
```

**Paso B.** Dentro de `_on_stream_event`, ubicá el bloque completo `epic_repair` (empieza
con el comentario `# Fix robusto brief→épica — pase correctivo de épica` cerca de la
línea 1111 y termina con `log("warn", f"epic_repair falló (no crítico): {_exc_er}")`
dentro de su propio `except Exception as _exc_er:` cerca de la línea 1237). Este bloque
completo NO se toca. Inmediatamente DESPUÉS de que ese bloque `try/except` cierra (mismo
nivel de indentación que el `if` de epic_repair, es decir sigue dentro de
`_on_stream_event` pero es un `if` HERMANO nuevo, NO anidado dentro del de épica),
agregá:

```python
            # Plan 160 F0 — pase correctivo del resolutor de incidencias
            # (último turno, solo una vez, stdin todavía abierto). Si el
            # IncidentAgent one-shot devolvió narración en vez del HTML del
            # desglose, le pedimos UNA vez que re-emita SOLO el HTML.
            if (
                not _incident_repair_done[0]
                and event.get("type") == "result"
                and getattr(config, "STACKY_INCIDENT_REPAIR_ENABLED", False)
                and _one_shot
                and (agent_type or "").lower() == "incident"
            ):
                _incident_repair_done[0] = True
                try:
                    from api.tickets import _extract_epic_html_raw, _looks_like_incident

                    _current_output_inc = "\n".join(final_output) if final_output else ""
                    _clean_inc = _extract_epic_html_raw(_current_output_inc)
                    if not _looks_like_incident(_clean_inc):
                        _ac_used_inc = autocorrect.attempts if autocorrect is not None else 0
                        _ac_budget_inc = config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES
                        if _ac_used_inc < _ac_budget_inc:
                            _INCIDENT_REPAIR_MSG = (
                                "Tu último mensaje no cumple el contrato del desglose de "
                                "incidencia. Re-emití AHORA, como único contenido del "
                                "mensaje, EXCLUSIVAMENTE el HTML del desglose con las "
                                "secciones RESUMEN EJECUTIVO, CONTEXTO DE NEGOCIO, ANALISIS "
                                "FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, "
                                "CRITERIOS DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, "
                                "EPICA RELACIONADA, PRIORIDAD Y ESTIMACION. SIN narración, "
                                "SIN preámbulo, SIN escribirlo en un archivo."
                            )
                            _sent_inc = _send_system_message(execution_id, _INCIDENT_REPAIR_MSG)
                            _incident_repair_result[0] = {
                                "attempted": True,
                                "reason": "narration_not_incident",
                                "sent": bool(_sent_inc),
                            }
                            log("info", f"incident_repair: reintento solicitado (sent={_sent_inc})")
                        else:
                            _incident_repair_result[0] = {
                                "attempted": False,
                                "reason": "narration_not_incident",
                                "budget_exhausted": True,
                            }
                            log("info", "incident_repair: presupuesto agotado, no se reintenta")
                except Exception as _exc_ir:  # noqa: BLE001
                    log("warn", f"incident_repair falló (no crítico): {_exc_ir}")
```

`agent_type` y `final_output` ya son variables disponibles en ese closure (usadas por el
bloque de épica inmediatamente anterior; no las declares de nuevo).

**Interacción con el cierre one-shot (C4 — leer antes de implementar, NO modificar):**
el loop principal cierra stdin apenas `_result_ok_seen[0]` es True
(`claude_code_cli_runner.py:1327-1334`) y arma una gracia de 20s
(`_one_shot_close_deadline`, `:1334-1343`) tras la cual TERMINA el proceso. El mensaje
de reintento se escribe al stdin DENTRO del procesamiento del mismo evento `result`
(reader thread), antes de que el loop principal alcance el cierre — el CLI lo consume
como un turno más aunque el stdin se cierre después. Consecuencia: **el turno de
reintento debe completar dentro de esa gracia**; si tarda más, el proceso se termina y
el output reparado puede quedar truncado. Esta mecánica es EXACTAMENTE la misma que ya
rige para `epic_repair` (aceptada en producción) — NO extiendas el deadline ni toques
`_result_ok_seen`/`_one_shot_close_deadline` en este plan: cambiaría el comportamiento
de épica y excede el scope.

**Paso C.** Ubicá (por el símbolo, cerca de la línea 1466-1467):

```python
        # Fix robusto brief→épica — sello del pase correctivo de épica (aditivo).
        if _epic_repair_result[0] is not None:
            metadata["epic_repair"] = _epic_repair_result[0]
```

Inmediatamente DESPUÉS, agregá:

```python
        # Plan 160 F0 — sello del pase correctivo de incidencia (aditivo).
        if _incident_repair_result[0] is not None:
            metadata["incident_repair"] = _incident_repair_result[0]
```

Contrato de la clave nueva de metadata (nunca renombrar): `metadata["incident_repair"]
= {"attempted": bool, "reason": "narration_not_incident", "sent": bool}` o
`{"attempted": False, "reason": "narration_not_incident", "budget_exhausted": True}`.
`None` (ausente) si nunca se disparó (HTML ya era válido, flag OFF, runtime sin resume, u
otro `agent_type`). **Semántica de `sent` (C4):** `sent: true` significa "el mensaje de
reintento se escribió al stdin del CLI"; NO garantiza que el turno de reintento haya
completado antes del cierre one-shot (gracia de 20s, ver arriba). El veredicto final de
si el HTML quedó válido lo da SIEMPRE `_looks_like_incident` sobre el output final en
preview/publish — nunca infieras éxito desde `sent`.

#### 4.0.3 — `backend/api/tickets.py`: diagnóstico accionable en preview/publish

**GET /incident-preview (rama de fallo).** Ubicá (por el símbolo, cerca de la línea
7337-7348):

```python
    execution_id = int(execution_id_str)
    with session_scope() as db:
        run = _get_run_for_preview(execution_id, db=db)
        if run is None:
            return jsonify({"ok": False, "error": "run_not_found"}), 404
        output = run.output

    html = _extract_epic_html_raw(output)
    if not _looks_like_incident(html):
        return jsonify({
            "ok": False, "error": "incident_not_in_output", "publishable": False,
        }), 200
```

Reemplazalo por:

```python
    execution_id = int(execution_id_str)
    with session_scope() as db:
        run = _get_run_for_preview(execution_id, db=db)
        if run is None:
            return jsonify({"ok": False, "error": "run_not_found"}), 404
        output = run.output
        repair_meta = run.metadata_dict.get("incident_repair")

    html = _extract_epic_html_raw(output)
    if not _looks_like_incident(html):
        return jsonify({
            "ok": False, "error": "incident_not_in_output", "publishable": False,
            "repair": repair_meta,
        }), 200
```

**GET /incident-preview (rama OK) — [ADICIÓN ARQUITECTO].** Ubicá (mismo endpoint, el
return final exitoso, cerca de la línea 7358-7364):

```python
    return jsonify({
        "ok": True,
        "title": title,
        "html": html,
        "related_epic": related,
        "publishable": True,
    }), 200
```

Reemplazalo por:

```python
    return jsonify({
        "ok": True,
        "title": title,
        "html": html,
        "related_epic": related,
        "publishable": True,
        "repair": repair_meta,
    }), 200
```

(`repair_meta` ya quedó asignada arriba por el primer reemplazo; con run sin repair vale
`None` y el frontend no muestra nada — backward-compatible.)

**POST /incidents/publish.** Ubicá (por el símbolo, cerca de la línea 7417-7424):

```python
    with session_scope() as db:
        run = _get_run_for_preview(execution_id, db=db)
        output = run.output if run is not None else None
        project_name = getattr(run, "project_name", None) if run is not None else None

    html = _extract_epic_html_raw(output)
    if not _looks_like_incident(html):
        return jsonify({"ok": False, "error": "incident_not_in_output"}), 422
```

Reemplazalo por:

```python
    with session_scope() as db:
        run = _get_run_for_preview(execution_id, db=db)
        output = run.output if run is not None else None
        project_name = getattr(run, "project_name", None) if run is not None else None
        repair_meta = run.metadata_dict.get("incident_repair") if run is not None else None

    html = _extract_epic_html_raw(output)
    if not _looks_like_incident(html):
        return jsonify({"ok": False, "error": "incident_not_in_output", "repair": repair_meta}), 422
```

`run.metadata_dict` es una property existente (`models.py:260-261`) que SIEMPRE devuelve
un `dict` (nunca `None`), así que `.get("incident_repair")` es seguro sin chequeo
adicional de tipo.

**Nota (C7):** el campo `repair` del 422 de publish NO tiene consumidor UI hoy (el modal
maneja los fallos de publish por excepción, `IncidentResolverModal.tsx:241-245`); existe
como diagnóstico para consumo por API/curl y para paridad de contrato con preview. NO
removerlo en limpiezas futuras por "no tener callers".

#### 4.0.4 — Tests PRIMERO: `backend/tests/test_incident_repair_guard.py` (NUEVO)

Creá el archivo con EXACTAMENTE este contenido:

```python
"""tests/test_incident_repair_guard.py — Plan 160 F0.

Guard anti-narración del pase correctivo del resolutor de incidencias.
Espejo de tests/test_epic_narration_guard.py (predicado de disparo +
flag de gobierno), pero para _looks_like_incident/_extract_epic_html_raw
y el agent_type=="incident" del pase correctivo embebido en
claude_code_cli_runner.py. NO arranca subprocesos ni toca red/DB real:
prueba la lógica pura + endpoints con run mockeado, al estilo
test_stall_watchdog.
"""
from __future__ import annotations


NARRATION_OUTPUT = (
    "Voy a leer los archivos adjuntos de la incidencia.\n\n"
    "Rol adoptado: Analista de Incidencias.\n\n"
    "Ya reuní el contexto de negocio y funcional. Genero el desglose "
    "y lo guardo en el archivo de salida."
)

VALID_INCIDENT_HTML = (
    "<h1>Error al guardar cliente duplicado</h1>"
    "<h2>RESUMEN EJECUTIVO</h2><p>Resumen.</p>"
    "<h2>ANALISIS FUNCIONAL</h2><p>Detalle funcional.</p>"
    "<h2>ANALISIS TECNICO</h2><p>Detalle técnico.</p>"
    "<h2>PASOS DE REPRODUCCION</h2><p>1. Paso uno.</p>"
    "<h2>CRITERIOS DE ACEPTACION</h2><p>Criterio uno.</p>"
)

REPAIR_META_SENT = {"attempted": True, "reason": "narration_not_incident", "sent": True}


def _incident_repair_should_fire(current_output: str) -> bool:
    """Espejo de la condición de disparo del pase correctivo de incidencia
    en claude_code_cli_runner.py (Plan 160 F0)."""
    from api.tickets import _extract_epic_html_raw, _looks_like_incident

    return not _looks_like_incident(_extract_epic_html_raw(current_output))


def _make_fake_run(output_text: str):
    class _FakeRun:
        output = output_text
        project_name = "Pacifico"

        @property
        def metadata_dict(self):
            return {"incident_repair": dict(REPAIR_META_SENT)}

    return _FakeRun()


def test_incident_repair_fires_on_narration():
    """Narración pura como output del último turno -> se pide el reintento."""
    assert _incident_repair_should_fire(NARRATION_OUTPUT) is True


def test_incident_repair_does_not_fire_on_valid_incident():
    """Output ya es un desglose válido (>=3 de 4 secciones + heading) -> NO
    se reintenta (no malgastar turnos/costo)."""
    assert _incident_repair_should_fire(VALID_INCIDENT_HTML) is False


def test_incident_repair_send_message_only_on_narration():
    """Simula el closure: send_fn se invoca SOLO ante narración, una vez."""
    sent: list[str] = []

    def fake_send(msg: str) -> bool:
        sent.append(msg)
        return True

    if _incident_repair_should_fire(NARRATION_OUTPUT):
        fake_send("Re-emití AHORA ... EXCLUSIVAMENTE el HTML del desglose ...")
    assert len(sent) == 1
    assert "HTML del desglose" in sent[0]

    sent.clear()
    if _incident_repair_should_fire(VALID_INCIDENT_HTML):
        fake_send("no debería enviarse")
    assert sent == []


def test_incident_repair_flag_exists_default_on():
    """El flag de gobierno existe y viene ON por default (mismo patrón que
    STACKY_EPIC_REPAIR_ENABLED)."""
    from config import config

    assert isinstance(config.STACKY_INCIDENT_REPAIR_ENABLED, bool)
    assert config.STACKY_INCIDENT_REPAIR_ENABLED is True


def test_incident_preview_repair_field_present_when_repaired(monkeypatch):
    """GET /incident-preview: si metadata["incident_repair"] existe en el
    run, el campo "repair" del JSON de fallo lo refleja (diagnóstico
    accionable, Plan 160 F0). Fallo sigue en incident_not_in_output."""
    from services import incident_store

    incident = incident_store.create_incident(text="algo se rompió", files=[])

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda *a, **k: _make_fake_run(NARRATION_OUTPUT))
    monkeypatch.setattr(t_mod.config.config, "STACKY_INCIDENT_RESOLVER_ENABLED", True)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    data = resp.get_json()
    assert data["error"] == "incident_not_in_output"
    assert data["repair"] == REPAIR_META_SENT


def test_incident_preview_ok_includes_repair_field(monkeypatch):
    """[ADICIÓN ARQUITECTO] GET /incident-preview OK: si el run fue reparado
    (metadata["incident_repair"].attempted) y el HTML quedó válido, la
    respuesta OK también incluye "repair" — el modal muestra la nota de
    transparencia (cero acciones automáticas invisibles)."""
    from services import incident_store

    incident = incident_store.create_incident(text="algo se rompió", files=[])

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda *a, **k: _make_fake_run(VALID_INCIDENT_HTML))
    monkeypatch.setattr(t_mod.config.config, "STACKY_INCIDENT_RESOLVER_ENABLED", True)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    data = resp.get_json()
    assert data["ok"] is True
    assert data["repair"] == REPAIR_META_SENT
```

Firma VERIFICADA contra el código (C3, cero inferencia): `create_incident(text: str,
files: list[tuple[str, bytes]]) -> dict` en `services/incident_store.py:106` — la
llamada `create_incident(text="algo se rompió", files=[])` es válida tal cual está
escrita arriba; NO la "ajustes".

**Comando (Git Bash):**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_incident_repair_guard.py -q
```

**Criterio de aceptación (binario):** el comando anterior sale con `0 failed` (exit code
0). Los 6 tests declarados arriba están en verde.

#### 4.0.5 — Registrar el test nuevo en el ratchet

`backend/tests/test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests`
falla si un `tests/test_*.py` nuevo no está listado en `HARNESS_TEST_FILES`
(`backend/scripts/run_harness_tests.sh`) ni en el allowlist. Ubicá en
`backend/scripts/run_harness_tests.sh` el bloque de tests de Plan 131 (busca la línea
`tests/test_plan131_incident_preview_publish.py`) y agregá, inmediatamente después de
`tests/test_plan131_incident_api.py` (línea 446 en la versión actual):

```
  tests/test_incident_repair_guard.py
```

**Criterio de aceptación (binario):**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
sale en verde (el test nuevo queda clasificado).

#### 4.0.6 — Frontend: tipo `repair` + mensaje de error más útil + nota de transparencia

**`frontend/src/incidents/incidentModel.ts`.** Ubicá:

```ts
export interface IncidentPreviewDTO {
  ok: boolean;
  title?: string | null;
  html?: string | null;
  related_epic?: IncidentRelatedEpicDTO | null;
  publishable: boolean;
  error?: string | null;
}
```

Reemplazalo por:

```ts
export interface IncidentRepairMetaDTO {
  attempted: boolean;
  reason: string;
  sent?: boolean;
  budget_exhausted?: boolean;
}

export interface IncidentPreviewDTO {
  ok: boolean;
  title?: string | null;
  html?: string | null;
  related_epic?: IncidentRelatedEpicDTO | null;
  publishable: boolean;
  error?: string | null;
  repair?: IncidentRepairMetaDTO | null;
}
```

**`frontend/src/components/IncidentResolverModal.tsx` — mensaje de error.** Ubicá (dentro
de `loadPreview`, por el string exacto `p.error === "incident_not_in_output"`, cerca de
la línea 189-193):

```tsx
        setErrorMsg(
          p.error === "incident_not_in_output"
            ? "El agente narró en vez de devolver el desglose HTML. Revisá la consola y reintentá."
            : `No se pudo generar el preview: ${p.error ?? "error desconocido"}`
        );
```

Reemplazalo por:

```tsx
        setErrorMsg(
          p.error === "incident_not_in_output"
            ? p.repair?.attempted
              ? "El agente narró en vez de devolver el desglose HTML. Stacky ya reintentó automáticamente una vez y no se recuperó. Revisá la consola de la ejecución y reintentá manualmente."
              : "El agente narró en vez de devolver el desglose HTML. Revisá la consola y reintentá."
            : `No se pudo generar el preview: ${p.error ?? "error desconocido"}`
        );
```

**`IncidentResolverModal.tsx` — nota de transparencia [ADICIÓN ARQUITECTO].** Ubicá el
paso preview (por el string exacto, cerca de la línea 373-375):

```tsx
        {step === "preview" && preview && (
          <div className={styles.body}>
            {preview.title && <div className={styles.previewTitle}>{preview.title}</div>}
```

Reemplazalo por:

```tsx
        {step === "preview" && preview && (
          <div className={styles.body}>
            {preview.repair?.attempted && (
              <p className={styles.hint}>
                ℹ️ Stacky detectó un fallo de formato en la primera respuesta del agente
                y lo reparó automáticamente. Revisá el desglose antes de publicar.
              </p>
            )}
            {preview.title && <div className={styles.previewTitle}>{preview.title}</div>}
```

(`styles.hint` ya existe y se usa en este mismo componente, línea 327 — cero CSS nuevo,
cero inline-style: compatible con el uiDebtRatchet del Plan 138.)

**Criterio de aceptación (binario):**
```
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
sale sin errores (exit code 0) — el tipo `IncidentRepairMetaDTO` y el campo opcional
`repair` no rompen ningún consumidor existente de `IncidentPreviewDTO` (campo opcional,
backward-compatible).

**Impacto por runtime:** el campo `repair` puede venir `null`/ausente en Codex CLI y
GitHub Copilot Pro (nunca se disparó el pase correctivo, ver §3) — el mensaje de error
cae al branch corto de siempre y la nota de transparencia no se muestra
(`p.repair?.attempted` es falsy con `undefined`/`null`), CERO cambio de comportamiento
visible en esos runtimes.

---

### F1 — Pegar imágenes desde el portapapeles en el modal de incidencias

**Objetivo en 1 frase:** Ctrl+V con una imagen copiada la agrega directamente a los
archivos adjuntos de la incidencia, sin pasar por disco.

**Valor:** elimina 3 pasos manuales (guardar captura → abrir selector → buscar el
archivo) para el caso de uso más común del resolutor (adjuntar un screenshot del bug).

**Runtime:** ninguno — F1 es 100% frontend (React + Clipboard API del navegador),
idéntico en los 3 runtimes porque no depende de qué agente/runtime procesa la
incidencia después. No aplica impacto/fallback por runtime.

**Flag:** ninguna nueva. Gateado por el flag ya existente `STACKY_INCIDENT_RESOLVER_ENABLED`
que ya protege todo el modal (si el modal no se muestra, tampoco el paste). No hay nada
que agregar a `config.py` ni a `harness_flags.py` para esta fase.

**Trabajo del operador: ninguno.**

#### Archivos a editar (uno nuevo: ninguno; se extiende código existente)

1. `Stacky Agents/frontend/src/incidents/incidentModel.ts`
2. `Stacky Agents/frontend/src/incidents/incidentModel.test.ts`
3. `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`

#### 4.1.1 — Tests PRIMERO: función pura `extractPastedImageFiles`

La lógica de extracción se implementa como función PURA en `incidentModel.ts` (mismo
archivo que ya aloja `validateFiles`/`canAnalyze`, testeable con Vitest sin DOM real —
este repo NO tiene `@testing-library/react`/jsdom instalados, así que toda lógica nueva
debe quedar testeable sin renderizar el componente).

Agregá a `frontend/src/incidents/incidentModel.test.ts`, DESPUÉS del último test
existente del archivo, el bloque `describe` de abajo, e incorporá
`extractPastedImageFiles` y `type ClipboardFileItem` al bloque
`import { ... } from "./incidentModel"` de las líneas 2-10. **La línea 1 del archivo
(`import { describe, it, expect } from "vitest";`) NO se toca (C5).** El bloque de
imports queda así:

```ts
import {
  validateFiles,
  canAnalyze,
  summarizeRelatedEpic,
  pickResumableIncident,
  extractPastedImageFiles,
  type IncidentStatusDTO,
  type IncidentDTO,
  type IncidentPreviewDTO,
  type ClipboardFileItem,
} from "./incidentModel";
```

Y el bloque de tests nuevo:

```ts
describe("extractPastedImageFiles", () => {
  function mockItem(kind: string, type: string, file: File | null): ClipboardFileItem {
    return { kind, type, getAsFile: () => file };
  }

  it("extrae una imagen pegada y la renombra con nombre único", () => {
    const png = new File(["a"], "image.png", { type: "image/png" });
    const items = [mockItem("file", "image/png", png)];
    const result = extractPastedImageFiles(items);
    expect(result).toHaveLength(1);
    expect(result[0].name).toMatch(/^pegado-\d+-0\.png$/);
    expect(result[0].type).toBe("image/png");
  });

  it("ignora items de texto (kind='string') sin bloquear", () => {
    const items = [mockItem("string", "text/plain", null)];
    expect(extractPastedImageFiles(items)).toEqual([]);
  });

  it("ignora archivos no-imagen pegados junto con imágenes", () => {
    const png = new File(["a"], "image.png", { type: "image/png" });
    const pdf = new File(["b"], "doc.pdf", { type: "application/pdf" });
    const items = [
      mockItem("file", "image/png", png),
      mockItem("file", "application/pdf", pdf),
    ];
    const result = extractPastedImageFiles(items);
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("image/png");
  });

  it("MIME image/* fuera del allowlist (svg) se ignora, no se renombra a .png", () => {
    const svg = new File(["<svg onload=alert(1)/>"], "image.svg", { type: "image/svg+xml" });
    const items = [mockItem("file", "image/svg+xml", svg)];
    expect(extractPastedImageFiles(items)).toEqual([]);
  });

  it("item de imagen sin File real (getAsFile null) se ignora sin lanzar", () => {
    const items = [mockItem("file", "image/png", null)];
    expect(extractPastedImageFiles(items)).toEqual([]);
  });

  it("sin items -> array vacío", () => {
    expect(extractPastedImageFiles([])).toEqual([]);
  });

  it("2 imágenes en el mismo evento -> 2 nombres distintos", () => {
    const png1 = new File(["a"], "image.png", { type: "image/png" });
    const png2 = new File(["b"], "image.png", { type: "image/jpeg" });
    const items = [
      mockItem("file", "image/png", png1),
      mockItem("file", "image/jpeg", png2),
    ];
    const result = extractPastedImageFiles(items);
    expect(result).toHaveLength(2);
    expect(result[0].name).not.toBe(result[1].name);
    expect(result[1].name).toMatch(/\.jpg$/);
  });
});
```

**Comando (Git Bash):**
```
cd "Stacky Agents/frontend" && npx vitest run src/incidents/incidentModel.test.ts
```

**Criterio de aceptación (binario):** el comando anterior sale con todos los tests en
verde (exit code 0), incluidos los 7 casos nuevos de `extractPastedImageFiles`.

#### 4.1.2 — Implementación: `extractPastedImageFiles` en `incidentModel.ts`

Agregá al final de `frontend/src/incidents/incidentModel.ts`:

```ts
/** Item mínimo compatible con DataTransferItem (estructural: permite pasar un
 * DataTransferItem real del DOM o un mock en tests sin depender de jsdom). */
export interface ClipboardFileItem {
  kind: string;
  type: string;
  getAsFile: () => File | null;
}

/** MIME -> extensión, alineada 1:1 con IMAGE_EXTENSIONS del backend
 * (services/incident_store.py:27) para que validateFiles nunca rechace una
 * imagen pegada por extensión desconocida. Es un ALLOWLIST cerrado (C2):
 * un MIME image/* que no esté acá (p.ej. image/svg+xml, image/tiff) se
 * IGNORA en vez de renombrarse a .png — renombrar colaría por validateFiles
 * (que valida por extensión) contenido cuya extensión real el backend
 * rechaza, y SVG además es vector activo de scripting. Esos archivos siguen
 * pudiendo adjuntarse por selector/drag&drop, donde conservan su extensión
 * real y la validación existente decide. */
const CLIPBOARD_IMAGE_EXT: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "image/bmp": ".bmp",
};

/**
 * Extrae SOLO los items de imagen del allowlist de un evento `paste`,
 * ignorando (sin bloquear) items no-imagen: texto (`kind === "string"`,
 * p.ej. el usuario pegando texto normal en el textarea) y archivos
 * no-imagen (p.ej. un PDF copiado desde el explorador junto con una
 * captura). Cada imagen se renombra "pegado-<timestamp>-<índice><ext>"
 * porque el navegador entrega clipboard images con nombres genéricos
 * ("image.png") que colisionarían en la lista de archivos si se pegan
 * varias veces. Pura salvo por `getAsFile()`/`Date.now()`; segura ante
 * lista vacía o `getAsFile()` que devuelve null.
 */
export function extractPastedImageFiles(items: ClipboardFileItem[]): File[] {
  const out: File[] = [];
  const ts = Date.now();
  items.forEach((item, idx) => {
    if (item.kind !== "file" || !item.type.startsWith("image/")) return;
    const ext = CLIPBOARD_IMAGE_EXT[item.type];
    if (!ext) return; // C2 — MIME image/* fuera del allowlist: ignorar.
    const file = item.getAsFile();
    if (!file) return;
    out.push(new File([file], `pegado-${ts}-${idx}${ext}`, { type: item.type }));
  });
  return out;
}
```

#### 4.1.3 — Implementación: handler `onPaste` en `IncidentResolverModal.tsx`

**Paso A — import.** Ubicá el bloque de import existente:

```tsx
import {
  validateFiles,
  canAnalyze,
  summarizeRelatedEpic,
  pickResumableIncident,
  type IncidentStatusDTO,
} from "../incidents/incidentModel";
```

Reemplazalo por:

```tsx
import {
  validateFiles,
  canAnalyze,
  summarizeRelatedEpic,
  pickResumableIncident,
  extractPastedImageFiles,
  type IncidentStatusDTO,
} from "../incidents/incidentModel";
```

**Paso B — handler.** Ubicá `handleDrop` (por el símbolo, cerca de la línea 121-124):

```tsx
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    if (e.dataTransfer.files?.length) handleFilesSelected(e.dataTransfer.files);
  }
```

Inmediatamente DESPUÉS, agregá:

```tsx
  function handlePaste(e: React.ClipboardEvent) {
    // C1 — el handler vive en el div raíz del modal pero solo actúa en el
    // paso intake (en preview/running/error/done, pegar no hace nada).
    if (step !== "intake") return;
    const items = e.clipboardData?.items;
    if (!items) return;
    const imageFiles = extractPastedImageFiles(Array.from(items));
    if (imageFiles.length > 0) {
      e.preventDefault();
      handleFilesSelected(imageFiles);
    }
    // Sin imágenes en el portapapeles (solo texto, p.ej. pegando en el
    // textarea): NO se llama preventDefault, el paste de texto sigue su
    // curso normal hacia el input/textarea enfocado.
  }
```

**Paso C — wiring en el JSX (C1).** Ubicá el div raíz del modal (por el string exacto,
cerca de la línea 260):

```tsx
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Resolver incidencia">
```

Reemplazalo por:

```tsx
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Resolver incidencia" onPaste={handlePaste}>
```

**Por qué el div raíz y no el body del intake (C1):** el evento `paste` se despacha en el
elemento con foco y burbujea por el árbol sintético de React. Con el handler en el body
del intake, Ctrl+V se pierde si el foco está en el header, en el botón cerrar o en
cualquier control fuera de ese div. En el raíz del modal cubre el foco en CUALQUIER
control del modal; el caso inicial (modal recién abierto) ya está cubierto porque el
textarea tiene `autoFocus` (línea 313). El gate por paso vive DENTRO del handler (Paso
B), así el wiring es un único atributo. NO usar un listener global de `document`
(descartado: riesgo de stale-closure sobre el estado `files` y captura de pastes ajenos
al modal).

**Paso D — hint de descubribilidad (sin la cual el operador no se entera de que Ctrl+V
funciona).** Ubicá (por el string exacto, cerca de la línea 327):

```tsx
              <p className={styles.hint}>Arrastrá capturas o logs acá, o hacé click para elegir archivos.</p>
```

Reemplazalo por:

```tsx
              <p className={styles.hint}>Arrastrá capturas o logs acá, pegá una imagen (Ctrl+V) o hacé click para elegir archivos.</p>
```

**Caso borde — límite máximo de archivos:** `handleFilesSelected` (sin cambios, ya
existente) ya llama a `validateFiles(merged, status)` con la lista completa (existentes +
nuevos) cada vez que se agregan archivos, sea por drag&drop, selector o paste — el límite
`status.max_files` (10, `incident_store.py:23`) y el tamaño máximo por archivo
(`status.max_file_mb`) se validan IDÉNTICO para imágenes pegadas, sin código nuevo de
validación. Si pegar excede el máximo, `validationErrors` se puebla exactamente igual que
hoy con drag&drop (mismo mensaje: `"Máximo <N> archivos (subiste <M>)."`).

**Criterio de aceptación (binario):**
```
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
sale sin errores (exit code 0).

**Impacto por runtime:** ninguno — F1 no ejecuta ni depende de ningún runtime de agente;
es intake de UI antes de lanzar el análisis.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El reintento de F0 tampoco alcanza (el modelo sigue narrando tras el pase correctivo) | Presupuesto acotado (comparte `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES` con autocorrect/criteria_repair/epic_repair — nunca reintenta más de una vez para incidente, nunca indefinidamente); el operador ve el mensaje enriquecido ("ya se reintentó y no se recuperó") en vez de uno genérico, y puede relanzar el análisis completo desde el modal (`handleAnalyze`, sin cambios). |
| (C4) El turno de reintento no completa dentro de la gracia one-shot (~20s tras el cierre de stdin, runner `:1327-1343`) y el proceso se termina con el output reparado truncado | Limitación PREEXISTENTE compartida con `epic_repair` (aceptada en producción; la re-emisión es re-formateo de contenido ya computado, típicamente rápida). El contrato de metadata lo hace explícito: `sent: true` ≠ reparación completada; el veredicto lo da `_looks_like_incident` en preview/publish. NO se toca el deadline en este plan (cambiaría épica; ver §4.0.2). Si la telemetría de `metadata["incident_repair"]` muestra truncamientos frecuentes, un plan futuro evalúa extender la gracia para AMBOS pases. |
| El pase correctivo de incidente compite con el de épica si algún día un run mixto tuviera ambos `agent_type` | No aplica: son condiciones mutuamente excluyentes (`agent_type=="business"` vs `agent_type=="incident"`), y cada `_on_stream_event` corresponde a UNA ejecución con UN `agent_type` fijo (`IncidentAgent.type = "incident"`, `backend/agents/incident.py:8`). |
| El HTML reparado introduce contenido malicioso que la UI renderiza (`dangerouslySetInnerHTML`) | Sin superficie nueva: el HTML reparado pasa por el MISMO pipeline (`_extract_epic_html_raw` → preview → render, `IncidentResolverModal.tsx:376-380`) que el de primer intento, con la misma (no-)sanitización preexistente del Plan 131. Este plan no cambia esa superficie ni en más ni en menos (ver §3 y §6). |
| Pegar un archivo NO-imagen (p.ej. copiar un `.docx` desde el explorador de Windows) dispara `handlePaste` sin agregarlo | Comportamiento esperado y ya cubierto por el test "ignora archivos no-imagen": `extractPastedImageFiles` filtra por `type.startsWith("image/")` + allowlist de MIME (C2); el operador sigue pudiendo adjuntar ese archivo con el selector o drag&drop existentes (sin regresión, sin bloqueo). |
| (C2) Imagen pegada con MIME `image/*` exótico (svg/tiff/heic) renombrada a `.png` colaría contenido mislabeled por la validación por extensión | Resuelto por diseño: allowlist cerrado `CLIPBOARD_IMAGE_EXT`; MIME fuera del mapa se ignora (test dedicado con `image/svg+xml`). El archivo puede adjuntarse por selector/drag&drop, donde conserva su extensión real y decide la validación existente. |
| Pegar texto normal en el textarea deja de funcionar por el nuevo `onPaste` | Mitigado por diseño: `handlePaste` solo llama `e.preventDefault()` cuando `imageFiles.length > 0`; con clipboard de solo texto (`kind === "string"`), `imageFiles` queda vacío y el paste nativo del navegador continúa sin interferencia (cubierto por el test "ignora items de texto"). |
| (C1) Ctrl+V con el foco fuera del modal (p.ej. `document.body` tras un click en zona no focuseable) no dispara el handler | Residual aceptado: el `onPaste` en el div raíz cubre el foco en cualquier control del modal, y el `autoFocus` del textarea (línea 313) cubre el flujo principal (abrir modal → pegar). El listener global de `document` se descartó explícitamente (stale-closure sobre `files` + captura de pastes ajenos al modal). Si el paste "no anda", un click en el textarea lo restablece — y el hint (Paso D) ancla la expectativa. |
| Doble pase correctivo confunde el log de consola (epic_repair + incident_repair loguean con el mismo prefijo genérico) | Prefijos de log distintos y explícitos ya en el pseudocódigo: `"epic_repair: ..."` vs `"incident_repair: ..."` — mismo patrón de logging que ya distingue `criteria_repair`/`run_repair`/`epic_repair` entre sí hoy. |

---

## 6. Fuera de scope

- Migrar el selector de modelo Claude del modal (`CLAUDE_MODELS` hardcodeado,
  `IncidentResolverModal.tsx:26-30`) al catálogo unificado del Plan 159. Queda como
  dependencia declarada para un plan futuro — Plan 159 no se toca ni se reimplementa acá.
- Extender el pase correctivo a Codex CLI o GitHub Copilot Pro (requeriría wiring de
  stdin-vivo equivalente en `codex_cli_runner.py`/runner de Copilot, que hoy NO existe ni
  para `epic_repair`; es un problema estructural más grande que excede esta incidencia
  puntual — ver precedente citado en §3).
- Extender la gracia post-result del cierre one-shot (`_one_shot_close_deadline`, 20s,
  runner `:1327-1343`) — compartida con `epic_repair`; tocarla acá cambiaría el
  comportamiento de épica (C4).
- Bucle de convergencia multi-iteración estilo Plan 58 (`STACKY_QUALITY_CONVERGENCE_ENABLED`)
  para incidencias. F0 replica la rama "legacy" single-shot de `epic_repair`
  (líneas 1183-1237 de `claude_code_cli_runner.py`), NO la rama de convergencia
  (líneas 1128-1182) — un solo reintento es proporcional al problema reportado.
  Extenderlo a convergencia queda para un plan futuro si la telemetría de
  `metadata["incident_repair"]` muestra que un solo reintento no alcanza en la práctica.
- Sanitización nueva del HTML del desglose antes del render (superficie preexistente del
  Plan 131, idéntica con o sin repair — ver §3 y Riesgos).
- Pegar archivos no-imagen desde el portapapeles (p.ej. texto largo como adjunto .txt).
  El pedido del operador fue específicamente sobre imágenes; texto pegado sigue yendo al
  campo de texto libre, que es su destino natural.
- Preview/recorte/edición de la imagen pegada antes de subirla. Se sube tal cual, como ya
  ocurre con drag&drop y el selector de archivos.

---

## 7. Glosario

- **Resolutor de Incidencias / IncidentAgent:** agente unificado (Plan 131) que analiza
  una incidencia multimodal (texto + archivos) y devuelve un desglose HTML dev-ready.
  `backend/agents/incident.py`, `type = "incident"`.
- **Pase correctivo (repair):** mecanismo por el cual, si el agente devuelve un output
  que no cumple el contrato de formato esperado, Stacky le pide UNA vez (por stdin, con
  la sesión todavía viva) que re-emita el artefacto correcto, antes de considerar el run
  terminado. Precedentes: `epic_repair`, `criteria_repair`, `run_repair` — todos en
  `backend/harness/` o inline en `claude_code_cli_runner.py`.
- **One-shot (`_ONE_SHOT_ADO_IDS`):** modo de ejecución donde el runner cierra la sesión
  apenas llega el primer evento `result` terminal, sin esperar input del operador por
  consola (usado por brief→épica `-1`, Documentador `-7`, Resolutor de Incidencias `-8`).
  `services/claude_code_cli_runner.py:216-223`.
- **Gracia one-shot (C4):** ventana de ~20s entre el cierre de stdin post-result y la
  terminación forzada del proceso (`_one_shot_close_deadline`,
  `claude_code_cli_runner.py:1327-1343`). El turno de reintento de cualquier pase
  correctivo one-shot (épica o incidencia) vive dentro de esa ventana.
- **Guard anti-narración:** validador puro (`_looks_like_epic`/`_looks_like_incident`)
  que distingue el artefacto HTML real de una narración en prosa del agente explicando lo
  que va a hacer en vez de hacerlo.
- **`_extract_epic_html_raw`:** extrae el bloque HTML crudo (sin sanitizar) de la
  respuesta del agente, buscando un fence ```html ... ``` con tags reales; si no hay
  fence, devuelve el texto tal cual. Compartido entre épica e incidencia.
- **`_send_system_message`:** función que escribe un mensaje al stdin todavía abierto del
  proceso Claude Code CLI en curso — el mecanismo de transporte de TODOS los pases
  correctivos (autocorrect, criteria_repair, epic_repair, y ahora incident_repair).
- **`ClipboardFileItem`:** interfaz estructural mínima (F1) que describe un
  `DataTransferItem` del navegador (`kind`, `type`, `getAsFile()`) sin acoplar el código
  de extracción de imágenes al DOM real, para poder testearlo con Vitest sin jsdom.

## Orden de implementación

1. F0 — `config.py` (flag nueva).
2. F0 — `claude_code_cli_runner.py` (pase correctivo inline).
3. F0 — `api/tickets.py` (diagnóstico en preview/publish + campo `repair` en la rama OK).
4. F0 — `tests/test_incident_repair_guard.py` + registro en `run_harness_tests.sh` +
   correr ambos comandos de test hasta verde.
5. F0 — frontend: tipo `repair` + mensaje de error enriquecido + nota de transparencia +
   `tsc --noEmit` verde.
6. F1 — `incidentModel.ts` (`extractPastedImageFiles`) + `incidentModel.test.ts` (tests
   primero, correrlos en rojo, luego implementar hasta verde).
7. F1 — `IncidentResolverModal.tsx` (import + `handlePaste` + wiring en el div raíz +
   hint) + `tsc --noEmit` verde.
8. Smoke manual del operador (opcional, no bloqueante): abrir el modal, copiar un
   screenshot (PrtScn/Win+Shift+S), Ctrl+V dentro del modal, confirmar que aparece en la
   lista de archivos con nombre `pegado-...`.

F0 y F1 son independientes entre sí — se pueden implementar y verificar en cualquier
orden relativo, o en paralelo por dos sesiones distintas, casi sin conflicto de archivos
(F0 toca `config.py`/`claude_code_cli_runner.py`/`api/tickets.py`/test backend; F1 toca
`incidentModel.ts`/`incidentModel.test.ts`/`IncidentResolverModal.tsx`). Los archivos
compartidos son `incidentModel.ts` (F0 agrega `IncidentRepairMetaDTO`; F1 agrega
`extractPastedImageFiles`) e `IncidentResolverModal.tsx` (F0 agrega la nota de
transparencia y el mensaje enriquecido; F1 agrega el handler `onPaste` y el hint) — si
se implementan en paralelo, el merge es aditivo (símbolos distintos, sin overlap de
líneas salvo bloques de imports/exports). Tras un merge así, correr `npx tsc --noEmit` +
los dos comandos de test (gotcha conocido del repo: el 3-way merge puede duplicar líneas
de cierre sin marcar conflicto).

## Definición de Hecho (DoD) — global

- [x] `STACKY_INCIDENT_REPAIR_ENABLED` existe en `config.py`, default `True`, sin
      `FlagSpec` en `harness_flags.py` (precedente `STACKY_EPIC_REPAIR_ENABLED`).
- [x] El pase correctivo de incidencia está wireado en `claude_code_cli_runner.py`,
      gateado por `agent_type=="incident"`, comparte presupuesto con autocorrect, sella
      `metadata["incident_repair"]`, y NO toca `_result_ok_seen` ni
      `_one_shot_close_deadline` (C4).
- [x] `GET /incident-preview` devuelve el campo `repair` tanto en la rama de fallo
      `incident_not_in_output` como en la rama OK ([ADICIÓN ARQUITECTO]);
      `POST /incidents/publish` lo devuelve en su 422.
- [x] `tests/test_incident_repair_guard.py` — 6 tests, todos verdes, registrado en
      `HARNESS_TEST_FILES` de `run_harness_tests.sh`.
- [x] `tests/test_harness_ratchet_meta.py` — el test nuevo queda clasificado (no
      aparece en el listado de sin-clasificar). El meta-test sigue en rojo por
      DRIFT PREEXISTENTE de otros planes (125/126/139/98/122, confirmado
      reproduciendo el fallo con este cambio stasheado) — ajeno a este plan, no
      corresponde a esta implementación arreglarlo.
- [x] `incidentModel.ts` exporta `extractPastedImageFiles` + `ClipboardFileItem` +
      `IncidentRepairMetaDTO`; `extractPastedImageFiles` ignora MIME fuera del allowlist
      (C2); `incidentModel.test.ts` tiene 7 tests nuevos, todos verdes.
- [x] `IncidentResolverModal.tsx` tiene `handlePaste` con gate interno por paso, wireado
      en `onPaste` del div raíz del modal (`styles.modal`, C1), el hint menciona Ctrl+V,
      y el paso preview muestra la nota de transparencia cuando `preview.repair?.attempted`.
- [x] `npx tsc --noEmit` en `Stacky Agents/frontend` sale 0 errores.
- [x] Cero flags nuevas requieren acción del operador (ambas default ON / sin flag).
- [x] Codex CLI y GitHub Copilot Pro: comportamiento de F0 sin cambios (degradación ya
      aceptada, mismo precedente que `epic_repair`); F1 funciona igual en los 3.
- [x] `git diff` de esta implementación no toca ningún archivo del scope de Plan 159
      (catálogo de modelos) ni reimplementa nada de ese plan.

## Nota de implementación (2026-07-17)

Implementado F0+F1 completos en la rama `feat/plan-160-incident-repair-paste-images`.
Regresión detectada y corregida durante la implementación: el helper `_patch_run` de
`tests/test_plan131_incident_preview_publish.py` (preexistente, NO parte del alcance
original del plan) construía un `MagicMock()` sin `metadata_dict`; el nuevo código de
F0 (`run.metadata_dict.get("incident_repair")`) devolvía otro `MagicMock` no
serializable a JSON → 500. Fix aditivo de una línea (`fake_run.metadata_dict = {}`) en
ese helper, confirmado necesario y suficiente (19/19 tests de ese archivo verdes tras
el fix). Smoke manual de Ctrl+V (paso 8 del Orden de implementación) queda pendiente
para el operador.
