# Plan 50 — Saneamiento determinista de la épica + warnings de grounding (capa invisible de calidad)

> Estado: IMPLEMENTADO 2026-06-19 · **v2**.
>
> Evidencia: F0 (3 flags env_only en services/harness_flags.py:1228 + .env.example:194 + tests/test_harness_flags.py::test_plan50_flags_registered). F1 (api/tickets.py _sanitize_epic_html + _dedup_identical_rf_blocks por tupla heading/cuerpo SIN renumeración (C3) + _extract_epic_html_raw + cableado en _extract_epic_html; tests/test_epic_sanitize.py 20 verdes). F2 (_structural_epic_warnings + extensión de _epic_grounding_warnings; tests/test_epic_structure_warnings.py 7 verdes). F3 (_catalog_grounding_warnings best-effort en autopublish_epic_from_run tras flag OFF; tests/test_catalog_grounding_warnings.py 5 verdes). [ADICIÓN] epic_sanitize_changed sellado en build_epic_summary. F4 NO-OP DOCUMENTADO: warnings ya fluyen por validate_artifact_route (api/agents.py:49,54 → to_dict() key "warnings", artifact_validator.py:93). F5: passthrough flag OFF verde + 0 regresión (53 tests epic existentes verdes). Total plan 50: 58 tests verdes (incl. autopublish/brief). C1 v2 confirmado: paridad por punto de inserción único (autopublish solo claude_code_cli_runner.py:1163), no cobertura efectiva 3 runtimes hoy.
> Implementable por modelo menor (Haiku / Codex / Copilot Pro) sin inferir nada.
> Tipo: capa de post-procesado **determinística** por funciones **puras** sobre el HTML/artefacto de la épica.
> Punto de inserción: opera sobre el HTML en el seam `_extract_epic_html` (tickets.py:5406), por el que pasa **todo** HTML de épica que se publica. **Aclaración de paridad (ver C1):** hoy la autopublicación de épica corre SOLO en el runtime Claude CLI (`claude_code_cli_runner.py:1163`); Codex y Copilot NO autopublican. La mejora es **paridad por punto de inserción único** (futuro-segura), no cobertura efectiva de 3 runtimes hoy.

## v1 → v2 (CHANGELOG — tras crítica adversarial verificada contra el código)

Verificado contra `backend/api/tickets.py` (5406–6005), `backend/services/claude_code_cli_runner.py` (1163–1227), `backend/services/client_profile.py:266`, `backend/services/context_enrichment.py:603`, y el Plan 47 v2 (cuyo C1 ya había corregido este mismo error).

- **C1 (BLOQUEANTE) — Falsa "paridad de 3 runtimes por construcción".** El v1 afirmaba que inyectar en `_extract_epic_html` cubre Codex/Claude/Copilot. FALSO: el único llamante de producción de `autopublish_epic_from_run`/`publish_issue_from_run` es `_maybe_autopublish_epic` en `claude_code_cli_runner.py:1163` (gated `agent_type=="business"`+`_one_shot`). Codex/Copilot no autopublican. Los 4 call sites de `_extract_epic_html` (5623/5695/5852/5925) son por-OPERACIÓN (publish-epic-HTTP / autopublish-epic / publish-issue ×2), no por-runtime. Reescrito principio 5, F1, F2, F5 y glosario: **paridad por punto de inserción único**, no efectiva. (Mismo error que el Plan 47 v2 ya marcó como su C1.)
- **C2 (IMPORTANTE) — Clave de dedup RF ambigua.** Definida clave explícita y segmentación determinística; dedup SOLO de tupla `(heading, cuerpo)` idéntica tras normalizar. Anti-destrucción de RF de cuerpo distinto atado a la clave, no a "byte idéntico" vago.
- **C3 (IMPORTANTE) — Paso (6) renumeración RF eliminado.** Renumerar RF rompe referencias cruzadas (semántica) y no es decidible puro sin falsos positivos. Movido a Fuera de scope; la no-consecutividad la reporta F2 como warning (canal correcto, no destructivo).
- **C4 (IMPORTANTE) — F3 falsos positivos.** Extracción de candidatos endurecida (identificadores CamelCase, stopwords excluidas); caso golden "proceso de carga" → sin warning espurio. Default OFF mantenido; warning siempre suave.
- **C5 (MENOR) — Asimetría de canal de warnings.** Declarado que F2/F3 warnings aplican al path autopublish (sella metadata→Observatorio); HTTP `create_epic_from_brief` e issue quedan fuera de scope de warnings (documentado).
- **C6 (MENOR) — Líneas corregidas.** Sellado real `claude_code_cli_runner.py:1221` (no ~1216); `build_process_dictionary_block` real `context_enrichment.py:603` y recibe `client_profile`; F3 usa `load_client_profile(...).get("process_catalog")`.
- **C7 (MENOR) — Idempotencia emoji+espacios.** Caso golden emoji-entre-palabras agregado.
- **[ADICIÓN ARQUITECTO]** — Telemetría `epic_sanitize_changed` (bool) en `epic_summary` (reusa canal existente, cero UI nueva): permite medir K1 sin inspección manual y detectar si el sanitizado quedó inerte. Ver F1.

---

## 1. Título, objetivo y KPI / impacto esperado

**Título.** Saneamiento determinista de la épica antes de publicar a ADO + warnings estructurales y de catálogo (grounding), todo invisible al operador.

**Objetivo (1 frase).** Mejorar la calidad del HTML de la épica que llega a Azure DevOps mediante funciones puras que normalizan **solo la forma** (nunca la semántica) y emiten warnings de calidad **no bloqueantes**, sin agregar ningún paso, checkbox, config ni input nuevo al operador y sin tocar ningún runtime.

**KPI / impacto esperado (medible con lo que ya existe):**
- **K1 — Limpieza de forma:** 0 épicas publicadas con `RF- 12` (guion + espacio), bloques RF idénticos repetidos, fences ` ``` ` residuales fuera de código o emojis de checklist sueltos. (La numeración RF duplicada/saltada NO se corrige —C3— se REPORTA como warning estructural en F2.) Verificable sobre el golden-set (F1), el flag `epic_sanitize_changed` en `epic_summary` y `metadata["grounding_warnings"]` de runs reales.
- **K2 — Visibilidad de calidad sin UI nueva:** el `GroundingObservatory` EXISTENTE (Plan 44) muestra los nuevos warnings estructurales y de catálogo; aumenta la tasa de runs con `grounding_warnings` poblados sin que el operador haga nada.
- **K3 — Cero regresión de publicación:** la tasa de épicas que caen a `needs_review` por `_looks_like_epic` NO aumenta respecto del baseline (el sanitizado nunca rompe estructura legítima; si rompiera, el guard ya las protege).
- **K4 — Idempotencia garantizada:** `sanitize(sanitize(x)) == sanitize(x)` para todo el golden-set (test binario).

**Impacto.** Calidad perceptible en ADO (épicas prolijas, sin ruido de CLI) y observabilidad de defectos de grounding, sin un solo clic adicional del operador y sin riesgo de escribir en el work item equivocado (no se toca pending-task; ver Fuera de scope §6).

---

## 2. Por qué ahora / gap que cierra

Apoyado en los planes ya implementados:

- **Plan 44 (Observatorio de grounding — IMPLEMENTADO).** Existe `_epic_grounding_warnings` (tickets.py:5461), el sellado en `metadata["grounding_warnings"]` y el `GroundingObservatoryCard` que ya muestra warnings. **Gap:** los warnings actuales son binarios y pobres ("no cita módulos/procesos"); no detectan defectos **estructurales** (RF saltados, duplicados, headings vacíos) ni **de catálogo** (procesos citados que no existen). Este plan los enriquece reusando el canal de visualización existente → **cero UI nueva**.
- **Plan 47 (Veredicto humano → memoria — IMPLEMENTADO).** Demuestra que el operador valora la calidad del output pero que cualquier mejora debe ser invisible/automática. **Gap:** hoy el HTML llega a ADO crudo del runtime (preámbulo + fences + checklist con emojis). `_extract_epic_html` (tickets.py:5406) ya deduplica fences pero NO normaliza forma dentro del HTML elegido. Este plan agrega esa normalización en el mismo seam.
- **Plan 49 (Testing determinista del arnés — PROPUESTO).** Blinda la calidad del arnés con golden-sets de extractores puros. **Gap / no-solapamiento:** el plan 49 testea funciones existentes; este plan 50 **agrega** funciones puras de saneamiento/linting de la épica. No replica el 49: 49 = "no romper lo que hay"; 50 = "mejorar el output". Comparten la disciplina (puro + golden-set + sin captura/replay de CLIs).

**Por qué ahora:** las superficies están verificadas y estables (debate de 2 rondas sobre `backend/api/tickets.py`), y el canal de visualización (Observatorio) ya está cableado. Es el momento de capitalizarlo con mejoras de forma seguras y baratas.

---

## 3. Principios y guardarraíles (no negociables — codificados en cada fase)

1. **Determinismo total.** Solo funciones puras `str -> str` o `(str, list) -> list[str]`. Sin LLM, sin red, sin BD en el camino caliente de saneamiento. Mismo input → mismo output siempre.
2. **Normaliza forma, NUNCA semántica.** El sanitizador no inventa, no resume, no reordena requerimientos, no borra RF con cuerpos distintos. Si hay ambigüedad sobre si un cambio es semántico, **no se hace**.
3. **Idempotencia obligatoria.** `f(f(x)) == f(x)` para todas las funciones de saneamiento (test binario en el golden-set).
4. **Gate suave para warnings, gate duro preexistente para forma.** Los warnings **nunca** bloquean ni auto-corrigen. El único gate duro es el `_looks_like_epic` YA existente, que corre **DESPUÉS** del sanitizado: si el sanitizado rompiera estructura, cae a `needs_review` (no publica basura).
5. **Paridad por punto de inserción único (NO "3 runtimes hoy" — ver C1).** El saneamiento se inyecta DENTRO de `_extract_epic_html`, el único helper por el que pasa todo HTML de épica que se publica (call sites 5623/5695/5852/5925, por-operación). HOY la autopublicación de épica corre SOLO en el runtime Claude CLI (`claude_code_cli_runner.py:1163`); Codex/Copilot no autopublican épicas. Por tanto la mejora beneficia el path real de publicación actual y queda futuro-segura: cualquier runtime que en el futuro publique por estos helpers la hereda automáticamente, sin tocar el runtime. Fallback: si una rama no pasa por el extractor, comportamiento idéntico al actual.
6. **Cero trabajo extra al operador.** Sin pasos, checkboxes, configs, inputs ni prompts nuevos. Invisible y automático. Backward-compatible: clientes que ya mandan `<p>...</p>` directo siguen funcionando.
7. **Human-in-the-loop intacto.** No agrega ni quita decisiones humanas. El veredicto de publicar/revisar sigue donde está.
8. **Mono-operador sin auth.** No se construye RBAC ni se asume protección por roles.
9. **No degradar performance/seguridad/estabilidad/DX.** Las funciones son O(n) sobre el tamaño del HTML (regex acotadas), best-effort ante errores (nunca lanzan), y reusan lo existente.
10. **Reusar lo existente.** `_extract_epic_html`, `_looks_like_epic`, `_epic_grounding_warnings`, `load_client_profile`, `build_process_dictionary_block`, `GroundingObservatory`, `validate_pending_task_file`. Cero infraestructura nueva.

---

## 4. Fases F0..F5

### Convención de tests y comandos (leer una vez)

- Los tests se corren **por archivo** con el **python del .venv del repo** (NO pytest global). El pin `pywin32==306` está roto en py3.13, por eso no se corre la suite completa.
- Comando base (PowerShell, desde la raíz del repo). Ajustar la ruta del intérprete si difiere:
  ```
  & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "<ruta_test>" -q
  ```
- Si `.venv\Scripts\python.exe` no existe, usar el intérprete del backend que ya corre los tests de tickets (mismo que usan los planes 42-49). Verificar con `Test-Path` antes.
- Regla: **escribir el test PRIMERO, confirmar que falla por la razón correcta, implementar, confirmar verde.**

---

### F0 — Flags y andamiaje (sin lógica nueva)

**Objetivo (1 frase).** Definir las 3 flags que protegen las mejoras, con defaults backward-compatibles, antes de tocar lógica.

**Valor.** Permite habilitar/deshabilitar cada mejora de forma independiente sin redeploy de código; default seguro garantiza cero regresión.

**Archivos exactos:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/harness_flags.py` — registrar las flags en el `FLAG_REGISTRY` existente (mismo patrón que las flags `STACKY_*` ya presentes; tipo `bool`).
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.env.example` — documentar las 3 flags con su default y una línea de descripción cada una.

**Flags exactas y defaults (justificados):**

| Flag | Default | Justificación del default |
|---|---|---|
| `STACKY_EPIC_SANITIZE_ENABLED` | `true` (ON) | Mejora de **forma pura e idempotente**, protegida aguas abajo por `_looks_like_epic`. Es seguro por construcción (golden-set obligatorio en F1). ON por defecto para que el operador reciba el beneficio sin tocar nada. Se puede apagar a `false` para volver al comportamiento exacto previo (passthrough). |
| `STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED` | `true` (ON) | Solo agrega entradas a una lista de warnings **no bloqueante** que ya se muestra en el Observatorio. Sin riesgo de publicación. ON para dar visibilidad inmediata. |
| `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` | `false` (env-only, OFF) | Lee `client_profile["process_catalog"]` (best-effort). Riesgo de **falsos positivos** (un proceso legítimo no listado en el catálogo dispara warning). Por prudencia arranca OFF; se enciende por entorno cuando el catálogo del proyecto esté curado. Nunca bloquea aunque esté ON. |

**Lectura de flags.** Usar el helper de lectura existente en `harness_flags.py` (mismo que leen las flags de planes 44/46/47). NO inventar un lector nuevo.

**Tests (PRIMERO):**
- Archivo: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_harness_flags.py` (ya existe; **agregar** casos, no reescribir).
- Casos:
  1. Las 3 flags están registradas en `FLAG_REGISTRY` con tipo `bool`.
  2. Default de `STACKY_EPIC_SANITIZE_ENABLED` = `True`.
  3. Default de `STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED` = `True`.
  4. Default de `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` = `False`.
- Comando:
  ```
  & "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_harness_flags.py" -q
  ```

**Criterio de aceptación (binario).** El comando de arriba pasa con las 4 aserciones nuevas verdes.

**Flag que lo protege.** N/A (esta fase DEFINE las flags).

**Impacto por runtime + fallback.** Ninguno (solo registro de flags). Fallback: si la flag no existe en el `.env`, se usa el default del registry.

**Trabajo del operador: ninguno.**

---

### F1 — `_sanitize_epic_html` (función pura de saneamiento de forma)

**Objetivo (1 frase).** Agregar una función pura que normaliza SOLO la forma del HTML de la épica y cablearla dentro del seam compartido `_extract_epic_html`, protegida por flag y por el guard `_looks_like_epic` posterior.

**Valor.** Épicas prolijas en ADO en los 3 runtimes con un solo punto de inserción; cero riesgo semántico.

**Archivos exactos:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/api/tickets.py` — agregar la función nueva **junto a los extractores** (inmediatamente después de `_extract_epic_html`, que termina en ~5436, y antes de `_looks_like_epic` en 5439, o justo después de él; ubicación exacta a criterio de prolijidad, mientras quede contiguo a los extractores). Cablearla dentro de `_extract_epic_html`.

**Firma exacta:**
```python
def _sanitize_epic_html(html: str) -> str:
    """Plan 50 F1 — Normaliza SOLO la forma del HTML de la épica. NUNCA la semántica.

    Idempotente: _sanitize_epic_html(_sanitize_epic_html(x)) == _sanitize_epic_html(x).
    Pura; nunca lanza; segura ante None/"".

    Normalizaciones (en este orden):
      1. Colapsa "RF- 12" / "RF -12" / "RF -  12" -> "RF-12" (guion pegado al número).
      2. Quita fences residuales ```...``` que hayan quedado FUERA de la épica
         (líneas que son solo backticks) — NO toca <pre>/<code> HTML.
      3. Quita emojis de checklist sueltos (✅ ☑ ✔ ✓ 🟢 ❌ ⬜ □ ▢) que aparezcan
         FUERA de cualquier tag (ruido del resumen final del CLI).
      4. Normaliza entidades/espacios: colapsa runs de espacios/tabs (no newlines),
         normaliza &nbsp; redundantes, trim de líneas.
      5. Deduplica bloques RF IDÉNTICOS según clave EXPLÍCITA (C2):
         key = (norm(heading_RF_completo), norm(cuerpo_hasta_el_siguiente_<h2>_o_EOF)).
         Segmentación determinística: re.split en (?=<h2[^>]*>\\s*RF-). Dos bloques
         colapsan SOLO si la tupla (heading, cuerpo) completa es idéntica tras
         normalizar espacios. RF con el mismo número pero cuerpo distinto -> AMBOS
         se conservan (la clave incluye el cuerpo, así que no colisionan).

    NOTA (C3): NO se renumera RF. Renumerar cambia semántica (rompe referencias
    cruzadas "según RF-3") y no es decidible de forma pura sin falsos positivos.
    La no-consecutividad se REPORTA en F2 como warning estructural (no destructivo).
    """
```

**Pseudocódigo / reglas con casos borde:**
```
def _sanitize_epic_html(html):
    if not html or not str(html).strip():
        return ""
    text = str(html)

    # (1) guion-espacio en RF: "RF-\s+(\d)" -> "RF-\1" ; "RF\s+-\s*(\d)" -> "RF-\1"
    text = re.sub(r"RF\s*-\s*(\d)", r"RF-\1", text)   # cubre "RF- 12", "RF -12", "RF - 12"

    # (2) fences residuales: líneas que SOLO contienen ``` (con/ sin lenguaje)
    #     OJO: solo a nivel de línea completa, para no tocar backticks dentro de <code>.
    text = re.sub(r"(?m)^\s*```[a-zA-Z]*\s*$\n?", "", text)

    # (3) emojis de checklist FUERA de tags. Estrategia conservadora:
    #     eliminarlos solo cuando no están dentro de < >. Implementación simple y segura:
    #     borrar el set fijo de emojis en cualquier posición (no afectan HTML válido).
    CHECK_EMOJIS = "✅☑✔✓🟢❌⬜□▢"
    text = re.sub(f"[{re.escape(CHECK_EMOJIS)}]\\s*", "", text)

    # (4) espacios: colapsar runs de [ \t] (NO \n) ; trim por línea
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # (5) dedup de bloques RF idénticos (clave EXPLÍCITA, C2):
    #     - segmentar: parts = re.split(r"(?=<h2[^>]*>\s*RF-)", text)  -> [preámbulo, bloqueRF, bloqueRF, ...]
    #     - para cada bloque RF: key = norm(parts[i]) donde norm = colapso de espacios + trim
    #       (el bloque INCLUYE su heading Y su cuerpo hasta el siguiente <h2 RF- o EOF)
    #     - conservar el PRIMER bloque por key; descartar bloques posteriores con key idéntica
    #     - mismo RF-N con cuerpo distinto -> key DISTINTA -> ambos se conservan (anti-destrucción)
    #     - el preámbulo (parts[0], antes del primer RF) se conserva siempre
    text = _dedup_identical_rf_blocks(text)   # helper interno privado, puro

    # (NO hay paso 6: renumeración eliminada por C3 — cambia semántica)

    return text.strip()
```
Casos borde a cubrir explícitamente:
- `None` / `""` → `""`.
- HTML sin ningún `RF-` (épica atípica) → solo aplica (1)-(4), paso (5) no-op (un solo segmento = preámbulo).
- Dos `<h2>RF-3</h2><p>X</p>` idénticos → queda uno (misma key).
- Dos `<h2>RF-3</h2>` con cuerpos `<p>X</p>` y `<p>Y</p>` → **quedan los dos** (key distinta porque incluye el cuerpo).
- Secuencia RF-1, RF-3 (falta RF-2) → **NO se toca** (no se renumera); F2 emite el warning.
- `<code>```bash</code>` (backticks dentro de un tag en línea con texto) → **no se toca** (paso 2 solo borra líneas que son *solo* backticks).
- Emoji entre palabras: `A ✅ B` → `A B` (un solo espacio, C7).
- Idempotencia: aplicar dos veces da lo mismo (loop sobre todo el golden-set).

**Cableado dentro de `_extract_epic_html` (tickets.py:5406):**
```python
# al FINAL de _extract_epic_html, justo antes de cada `return`:
#   en vez de `return html_candidates[0]` y `return text`, envolver:
def _extract_epic_html(raw):
    ...
    if html_candidates:
        result = html_candidates[0]
    else:
        result = text
    if _epic_sanitize_enabled():      # lee STACKY_EPIC_SANITIZE_ENABLED (default True)
        result = _sanitize_epic_html(result)
    return result
```
Nota: el guard `_looks_like_epic` corre DESPUÉS en los call sites (5700, 5926) — no se cambia su orden. Si el sanitizado rompiera estructura, `_looks_like_epic` devuelve `False` y el flujo cae a `needs_review` por la rama ya existente.

**[ADICIÓN ARQUITECTO] — Telemetría de efectividad del sanitizado (cero UI nueva).** En `autopublish_epic_from_run`, donde ya se construye `epic_summary` (tickets.py:5772), agregar el flag `epic_sanitize_changed = (clean_html != _pre_sanitize_html)` calculado comparando el HTML antes/después del sanitizado (capturar el `_pre_sanitize_html` justo antes de invocar el extractor, o exponer un retorno opcional). Sellarlo dentro del `epic_summary` existente (no nueva key de metadata, no nueva UI). Beneficio: K1 se vuelve medible sin inspección manual y se detecta si el sanitizado quedó inerte (siempre `False` ⇒ revisar). Respeta todos los rieles: determinístico, cero trabajo del operador, reusa el canal `epic_summary` que el Observatorio ya lee. Protegido por `STACKY_EPIC_SANITIZE_ENABLED` (si OFF, `epic_sanitize_changed=False` trivialmente).

**Tests (PRIMERO):**
- Archivo NUEVO: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_epic_sanitize.py`.
- Golden-set: strings de HTML crudo real (incluir un caso **estilo Pacífico** con bloques RF-N de carga batch, preámbulo en prosa y checklist con emojis al final). Cada caso: `input_str -> expected_str` (comparación exacta).
- Casos obligatorios:
  1. `"RF- 12"` → `"RF-12"`; `"RF -12"` → `"RF-12"`.
  2. Línea ` ``` ` suelta se elimina; backticks dentro de `<code>...</code>` en línea con texto se preservan.
  3. Emojis de checklist fuera de tags eliminados; texto del párrafo intacto.
  4. Dos bloques RF **idénticos** (heading+cuerpo) → uno solo.
  5. Dos bloques con mismo número RF pero **cuerpo distinto** → ambos preservados (anti-destrucción; key incluye el cuerpo).
  6. Secuencia RF-1, RF-3 (falta RF-2) → el HTML **no cambia la numeración** (NO se renumera, C3).
  7. Emoji entre palabras `A ✅ B` → `A B` (un solo espacio, C7).
  8. **Idempotencia:** `_sanitize_epic_html(_sanitize_epic_html(x)) == _sanitize_epic_html(x)` para TODOS los casos del golden-set (loop sobre el set).
  9. `None` y `""` → `""`.
  10. Caso Pacífico completo: el HTML resultante pasa `_looks_like_epic(...) == True` (no rompe estructura).
- Comando:
  ```
  & "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_epic_sanitize.py" -q
  ```

**Criterio de aceptación (binario).** El comando pasa con todos los casos verdes, incluido el test de idempotencia que itera el golden-set, y el caso Pacífico cumple `_looks_like_epic == True`.

**Flag que lo protege.** `STACKY_EPIC_SANITIZE_ENABLED` (default `true`). Con `false`, `_extract_epic_html` devuelve exactamente lo de antes (passthrough verificable con un test que mockea la flag a False y compara con la salida sin sanitizar).

**Impacto por runtime + fallback (C1 corregido).** El saneamiento corre en `_extract_epic_html`, usado por los 4 call sites por-operación (5623 publish-epic-HTTP, 5695 autopublish-epic, 5852/5925 issue). HOY la autopublicación corre solo en el runtime Claude CLI (`claude_code_cli_runner.py:1163`); Codex/Copilot no autopublican. La mejora beneficia el path real de publicación actual y es futuro-segura (cualquier runtime que publique por estos helpers la hereda). Fallback: si un publisher futuro NO usara el extractor, no se sanitiza (comportamiento actual), sin romper nada.

**Trabajo del operador: ninguno.**

---

### F2 — Warnings estructurales en `_epic_grounding_warnings`

**Objetivo (1 frase).** Extender `_epic_grounding_warnings` para detectar defectos ESTRUCTURALES deterministas (RF no consecutivos/duplicados, headings vacíos, bloques RF sin contenido) como warnings no bloqueantes.

**Valor.** El Observatorio (Plan 44) muestra defectos concretos de calidad sin UI nueva y sin bloquear publicación.

**Archivos exactos:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/api/tickets.py` — extender la función existente en la línea 5461 (NO crear otra; agregar la lógica estructural detrás de la flag).

**Diff ilustrativo:**
```python
def _epic_grounding_warnings(html):
    warnings = []
    if not html:
        return ["epic_grounding_low: la épica no cita módulos/procesos fuente ni marca supuestos"]
    # --- comportamiento existente (Plan 42 F2) ---
    if not re.search(r"m[oó]dulo|\[SUPUESTO|proceso", html, re.IGNORECASE):
        warnings.append("epic_grounding_low: la épica no cita módulos/procesos fuente ni marca supuestos")
    # --- Plan 50 F2: warnings estructurales (gate suave) ---
    if _epic_structure_warnings_enabled():   # STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED (default True)
        warnings.extend(_structural_epic_warnings(html))
    return warnings
```
Helper puro nuevo:
```python
def _structural_epic_warnings(html: str) -> list[str]:
    """Plan 50 F2 — Warnings estructurales deterministas. Pura; nunca lanza."""
    out = []
    nums = [int(n) for n in re.findall(r"<h2[^>]*>\s*RF-(\d+)", html, re.IGNORECASE)]
    # (a) duplicados de número RF
    dups = sorted({n for n in nums if nums.count(n) > 1})
    if dups:
        out.append(f"epic_structure: números RF duplicados: {dups}")
    # (b) no consecutivos (huecos en la secuencia 1..max)
    if nums:
        expected = set(range(1, max(nums) + 1))
        missing = sorted(expected - set(nums))
        if missing:
            out.append(f"epic_structure: secuencia RF no consecutiva, faltan: {missing}")
    # (c) headings vacíos: <h1></h1> / <h2>   </h2>
    if re.search(r"<h[12][^>]*>\s*</h[12]>", html, re.IGNORECASE):
        out.append("epic_structure: hay headings vacíos")
    # (d) bloque RF sin contenido: un <h2>RF-N</h2> seguido inmediatamente de otro heading o EOF
    #     (sin párrafo/lista entre medio)
    if re.search(r"<h2[^>]*>\s*RF-\d+[^<]*</h2>\s*(?=<h[12]|$)", html, re.IGNORECASE):
        out.append("epic_structure: hay bloques RF sin contenido")
    return out
```
Casos borde: HTML sin RF → solo (c). Lista vacía si todo está bien.

**Sellado y visualización (reuso, sin cambios de UI):** `_epic_grounding_warnings(clean_html)` se evalúa en `autopublish_epic_from_run` (tickets.py:5742-5743) y vuelve en `_AutopublishResult.grounding_warnings`; el runner lo sella en `metadata["grounding_warnings"]` en `claude_code_cli_runner.py:1221` (verificado — el v1 decía "~1216", impreciso). El `GroundingObservatoryCard` (Plan 44) ya lee esa key. **No se agrega UI.**

**Alcance del canal (C5):** estos warnings viajan por el path autopublish (que sella metadata y alimenta el Observatorio). El endpoint HTTP síncrono `create_epic_from_brief` (tickets.py:5960) NO sella metadata de run, por lo que ahí no se muestran warnings — fuera de scope (documentado, no es regresión).

**Tests (PRIMERO):**
- Archivo NUEVO: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_epic_structure_warnings.py`.
- Casos:
  1. HTML con `RF-1` y `RF-3` (falta `RF-2`) → warning "no consecutiva, faltan: [2]".
  2. Dos `RF-2` (números duplicados) → warning "duplicados: [2]".
  3. `<h2></h2>` → warning "headings vacíos".
  4. `<h2>RF-1</h2><h2>RF-2</h2>...` con RF-1 sin cuerpo → warning "bloques RF sin contenido".
  5. Épica bien formada (RF-1, RF-2, RF-3 consecutivos con cuerpo) → lista vacía de warnings estructurales.
  6. Flag OFF → `_structural_epic_warnings` no se invoca (warnings estructurales ausentes; el warning de grounding histórico se mantiene).
- Comando:
  ```
  & "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_epic_structure_warnings.py" -q
  ```

**Criterio de aceptación (binario).** El comando pasa con los 6 casos verdes.

**Flag que lo protege.** `STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED` (default `true`). Con `false`, `_epic_grounding_warnings` se comporta como en Plan 42 (verificable con test que mockea la flag).

**Impacto por runtime + fallback (C1).** `_epic_grounding_warnings` se llama en `autopublish_epic_from_run` (5743), invocado solo por el runner Claude CLI (1163). Fallback: si `_grounding_enabled` (STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED) está OFF, no se generan warnings (comportamiento actual).

**Trabajo del operador: ninguno.**

---

### F3 — `_catalog_grounding_warnings` (linter de procesos contra el catálogo)

**Objetivo (1 frase).** Agregar una función pura que detecta nombres de proceso citados en el HTML que NO existen en el `process_catalog` real del proyecto y emite un warning best-effort no bloqueante.

**Valor.** Señala posibles alucinaciones de procesos sin bloquear ni auto-corregir, reusando el mismo catálogo que ya se inyecta al agente.

**Archivos exactos:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/api/tickets.py` — función pura nueva + cableado dentro del flujo de warnings (junto a F2).
- Fuente de verdad: `services.client_profile.load_client_profile(project_name)` (client_profile.py:266) → `client_profile.get("process_catalog")` (items `{name, purpose, kind}`). Es el **mismo dato** que `services/context_enrichment.py:build_process_dictionary_block` (603, recibe `client_profile` completo) inyecta al agente. F3 lee el catálogo crudo vía `load_client_profile`, NO vía `build_process_dictionary_block` (esa es para inyección, no fuente).

**Firma exacta:**
```python
def _catalog_grounding_warnings(html: str, process_catalog: list) -> list[str]:
    """Plan 50 F3 — Warning si el HTML cita procesos que NO están en el catálogo real.

    Best-effort: si process_catalog es None/vacío -> [] (no opina sin fuente de verdad).
    Matching NORMALIZADO (lower + trim + colapso de espacios). NUNCA bloquea ni corrige.
    Pura; nunca lanza.

    Limitación honesta: solo compara NOMBRES del catálogo, NO IDs de ADO (eso requeriría
    BD/ADO y rompería el determinismo). Documentado a propósito.
    """
```
Pseudocódigo:
```python
def _catalog_grounding_warnings(html, process_catalog):
    if not html or not process_catalog:
        return []
    def norm(s): return re.sub(r"\s+", " ", str(s)).strip().lower()
    catalog_names = {norm(item.get("name")) for item in process_catalog if item.get("name")}
    if not catalog_names:
        return []
    # Extraer candidatos: token tras "proceso "/"módulo " que PAREZCA un identificador
    # de proceso real (C4 — evitar falsos positivos con prosa común como "proceso de carga").
    # Heurística conservadora: el candidato debe parecer un identificador técnico, no una
    # palabra de prosa española. Criterio: tiene una MAYÚSCULA interna (CamelCase) o un
    # dígito o un separador (_ . / -). Palabras de prosa minúsculas ("carga", "de") NO
    # califican y se ignoran (no generan warning espurio).
    def _looks_like_proc_id(tok: str) -> bool:
        return bool(re.search(r"[A-Z].*[A-Z]|[0-9]|[_./-]", tok)) or (tok[:1].isupper() and any(c.isupper() for c in tok[1:]))
    raw_cited = re.findall(r"(?:proceso|m[oó]dulo)\s+([A-Za-z][A-Za-z0-9_./-]{2,})", html, re.IGNORECASE)
    cited = {c for c in raw_cited if _looks_like_proc_id(c)}
    unknown = sorted({c for c in cited if norm(c) not in catalog_names})
    if unknown:
        return [f"catalog_grounding: procesos citados no presentes en el catálogo: {unknown}"]
    return []
```
Limitación honesta (C4): el matching compara solo NOMBRES normalizados; el catálogo puede estar desincronizado entre N:\ (fuente) y C:\ (deploy). Por eso el warning es **best-effort, no bloqueante, default OFF** hasta que el catálogo del proyecto esté curado. Nunca corrige.

**Cableado:** dentro del mismo bloque de warnings (call site 5743), detrás de la flag y resolviendo el catálogo best-effort:
```python
if _catalog_grounding_warnings_enabled():   # STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED (default False)
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project_name)   # `project_name` ES parámetro de autopublish_epic_from_run (tickets.py:5668), verificado
        catalog = (profile or {}).get("process_catalog") or []
    except Exception:
        catalog = []
    warnings.extend(_catalog_grounding_warnings(clean_html, catalog))
```
Best-effort estricto: cualquier fallo de carga → `catalog = []` → la función devuelve `[]` (no opina). Nunca lanza, nunca bloquea.

**Tests (PRIMERO):**
- Archivo NUEVO: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_catalog_grounding_warnings.py`.
- Casos (la función PURA, sin tocar BD — se le pasa el catálogo como argumento):
  1. Catálogo `[{"name":"Mul2Bane"},{"name":"IncHost"}]`, HTML cita "proceso Mul2Bane" → `[]`.
  2. Mismo catálogo, HTML cita "proceso ProcesoFantasma" → warning con `["ProcesoFantasma"]`.
  3. Matching normalizado: catálogo `"Mul2Bane"`, HTML cita "proceso  mul2bane " → `[]` (case/espacios).
  4. `process_catalog` vacío/`None` → `[]` (best-effort, no opina).
  5. HTML sin citas de proceso → `[]`.
  6. Prosa común (C4): HTML cita "el proceso de carga batch" con catálogo `[{"name":"Mul2Bane"}]` → `[]` (ni "de" ni "carga" parecen identificador técnico → `_looks_like_proc_id` los descarta). Valida cero warning espurio por prosa.
  7. Identificador real ausente: catálogo `[{"name":"Mul2Bane"}]`, HTML cita "proceso RSActBD" → warning `["RSActBD"]` (CamelCase/dígitos → sí califica, y no está en catálogo).
- Comando:
  ```
  & "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_catalog_grounding_warnings.py" -q
  ```

**Criterio de aceptación (binario).** El comando pasa con los 7 casos verdes. La función NO toca BD ni red (test no mockea nada externo; el catálogo se pasa por argumento).

**Flag que lo protege.** `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` (default `false`, env-only). Justificación del OFF: evita falsos positivos hasta que el catálogo del proyecto esté curado y por el desync N:\ vs C:\. Nunca bloquea aunque esté ON.

**Impacto por runtime + fallback (C1).** Corre en `autopublish_epic_from_run` (runner Claude CLI, 1163). Fallback: catálogo ausente/ilegible → `[]` (sin opinión), sin error.

**Trabajo del operador: ninguno.**

---

### F4 — Cableado de `validate_pending_task_file` al reporte del run (CONDICIONAL — verificar primero)

**Objetivo (1 frase).** Exponer las `ArtifactValidation.warnings` ya tipadas de `validate_pending_task_file` como warnings visibles del run, SOLO si aún no fluyen a la UI; cero lógica nueva, solo cableado.

**Valor.** El operador ve advertencias de artefacto (JSON inválido, schema incompleto, epic_id no-entero, mismatch ordinal vs directorio, epic_id inexistente en BD) sin que se agregue ningún paso.

**Paso 0 OBLIGATORIO (verificar antes de tocar nada):**
- Función existente: `validate_pending_task_file(path, *, check_db=True) -> ArtifactValidation` en `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/artifact_validator.py:136`; el resultado tiene `.warnings: list[str]` (línea 85) y `.to_dict()` con key `"warnings"` (línea 93).
- Buscar dónde se invoca y si su `.warnings`/`.to_dict()` ya llega a la respuesta de algún endpoint de run o a `metadata`:
  ```
  grep -rn "validate_pending_task_file\|ArtifactValidation\|validate_artifact" "...\backend\api" "...\backend\services"
  ```
- **Si YA fluye a la UI** (p. ej. `api/agents.py:validate_artifact_route` ya devuelve `.warnings` y el frontend lo muestra): **NO hacer F4**. Documentar en el PR "F4 omitida: ya cableado en `<archivo:línea>`" y cerrar la fase como no-op. Esto es un criterio de aceptación válido.
- **Si NO fluye al reporte del run** (validación corre pero `.warnings` se descarta): cablearlo al mismo canal `metadata["grounding_warnings"]` o a un `metadata["artifact_warnings"]` adyacente que el `GroundingObservatory` ya pueda leer.

**Archivos exactos (solo si NO está cableado):**
- El call site donde se valida el pending-task durante el run (resolver con el grep del Paso 0; candidato: `backend/api/tickets.py` cerca de `_normalize_pending_task_parent` 4630, o el output_watcher). Agregar: tras validar, `metadata.setdefault("artifact_warnings", []).extend(result.warnings)`.

**Tests (PRIMERO, solo si se implementa):**
- Archivo NUEVO: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_artifact_warnings_wiring.py`.
- Caso: dado un `ArtifactValidation` con `warnings=["x"]`, el cableado deja `metadata["artifact_warnings"] == ["x"]`. (Mock del validador; testear SOLO el cableado, no la validación que ya tiene sus tests.)
- Comando:
  ```
  & "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_artifact_warnings_wiring.py" -q
  ```

**Criterio de aceptación (binario).** O bien (a) el grep del Paso 0 demuestra que ya está cableado y la fase se cierra como no-op documentado; o bien (b) el test de cableado pasa verde.

**Flag que lo protege.** Reusa el canal de warnings existente; no requiere flag propia (es solo propagación de un resultado ya tipado y no bloqueante). Si se prefiere protección, reusar `STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED` (NO crear una cuarta flag).

**Impacto por runtime + fallback.** El pending-task es común al flujo de tasks de los 3 runtimes. Fallback: si la validación no corre en algún runtime, `artifact_warnings` queda vacío (sin error).

**Trabajo del operador: ninguno.**

---

### F5 — Verificación de paridad y no-regresión (cierre)

**Objetivo (1 frase).** Confirmar que las mejoras corren en el seam compartido (paridad de 3 runtimes) y que no hay regresión de publicación.

**Valor.** Cierra el DoD con evidencia binaria.

**Acciones:**
1. Confirmar por grep (C1) que `autopublish_epic_from_run` tiene UN solo llamante de producción: `grep -rn "autopublish_epic_from_run" backend/services backend/api` debe mostrar el call site `claude_code_cli_runner.py:1163` (runner Claude CLI) + definición en tickets.py + tests. Documentar en el PR: "la mejora corre en el path de publicación real (Claude CLI business); Codex/Copilot no autopublican épicas; paridad por punto de inserción único en `_extract_epic_html`, futuro-segura". NO afirmar cobertura efectiva de 3 runtimes.
2. Test de no-regresión: con `STACKY_EPIC_SANITIZE_ENABLED=false`, `_extract_epic_html(x)` == salida histórica (passthrough).
3. Correr los 4 archivos de test de F0-F3 (y F4 si aplica) y confirmar verde.

**Archivos exactos:** los tests de F1/F2/F3 ya cubren esto; agregar a `test_epic_sanitize.py` el caso de passthrough con flag OFF.

**Comando (corre los archivos uno por uno):**
```
& "...\backend\.venv\Scripts\python.exe" -m pytest "...\backend\tests\test_epic_sanitize.py" "...\backend\tests\test_epic_structure_warnings.py" "...\backend\tests\test_catalog_grounding_warnings.py" "...\backend\tests\test_harness_flags.py" -q
```
(Si correr varios archivos juntos dispara el pin roto de pywin32, correrlos de a uno.)

**Criterio de aceptación (binario).** Todos los archivos de test verdes; el test de passthrough con flag OFF confirma cero regresión.

**Flag que lo protege.** N/A (fase de verificación).

**Impacto por runtime + fallback.** Es la fase que CERTIFICA la paridad.

**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Sanitizador agresivo borra HTML legítimo** (p. ej. elimina un RF con cuerpo distinto creyéndolo duplicado, o destruye `<code>` con backticks). | **Golden-set obligatorio (F1)** con casos de RF mismo-número-cuerpo-distinto y backticks dentro de tags; dedup solo de bloques **byte-idénticos**; paso (2) solo borra líneas que son *solo* backticks. Guard `_looks_like_epic` posterior atrapa cualquier ruptura → `needs_review`, nunca publica basura. |
| R2 | **Falsos positivos del catalog linter** (proceso legítimo no listado dispara warning). | El warning es **suave, nunca bloquea ni corrige**; flag `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` default **OFF** hasta catálogo curado; matching normalizado reduce ruido. Limitación documentada (solo nombres, no IDs ADO). |
| R3 | **Asimetría silenciosa entre publishers** si el saneamiento NO queda en el helper único. | F1 inyecta el saneamiento **dentro de `_extract_epic_html`** (helper único por el que pasa todo HTML de épica), no en el autopublish de un runtime. F5 verifica por grep que `autopublish_epic_from_run` tiene un solo llamante (Claude CLI) y documenta que la paridad es por punto de inserción único, no efectiva en 3 runtimes hoy (C1). |
| R4 | **Renumeración RF cambiaría semántica.** | RESUELTO por diseño (C3): el sanitizador NO renumera. La no-consecutividad se reporta como warning estructural en F2 (no destructivo). Renumeración movida a Fuera de scope. |
| R5 | **`load_client_profile` introduce I/O en el camino caliente** (F3). | Solo se invoca si la flag ON; envuelto en `try/except` → `[]`; la función pura recibe el catálogo ya cargado y no hace I/O. Default OFF evita el costo por defecto. |
| R6 | **Pin pywin32 roto rompe la suite al correr varios archivos juntos.** | Correr tests **por archivo** con el python del .venv (convención del repo). F5 documenta el fallback de correr de a uno. |
| R7 | **Idempotencia rota** (segundo pase cambia el output). | Test de idempotencia que itera TODO el golden-set en F1 (criterio binario). |

---

## 6. Fuera de scope (RECHAZADO con razón — decisiones del debate)

- **Auto-reparación ampliada de `pending-task.json` infiriendo el `epic_id` desde el ordinal.** RECHAZADO: reintroduce el trap "stale consumed pending-task" (escribir en el work item equivocado). La reparación SEGURA ya existe: `_normalize_pending_task_parent` (tickets.py:4630) repara `epic_id` SOLO con id autoritativo resuelto por el output_watcher (BD/ejecución) y es idempotente si ya hay `consumed_at` (:4663). **NO ampliar.**
- **Renumeración automática de RF (C3).** RECHAZADO: renumerar RF cambia semántica (rompe referencias cruzadas tipo "según RF-3") y no es decidible de forma pura sin falsos positivos. La no-consecutividad SOLO se reporta como warning estructural (F2), nunca se corrige.
- **Auto-reescribir la épica con un LLM o sugerir correcciones al operador.** RECHAZADO: no determinístico y/o no invisible (agrega un paso humano). Este plan solo normaliza forma y emite warnings pasivos.
- **Replay/captura de CLIs.** RECHAZADO (ya descartado en Plan 49). No se graban ni reproducen sesiones de runtime.
- **Bloquear publicación por warnings de grounding/estructura/catálogo.** RECHAZADO: rompería human-in-the-loop y agregaría fricción. Gate suave siempre; el único gate duro es el `_looks_like_epic` preexistente.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **Punto de inserción único:** `_extract_epic_html` (tickets.py:5406), helper por el que pasa todo HTML de épica que se publica (call sites por-operación 5623/5695/5852/5925). NO es un "seam de 3 runtimes": hoy solo el runtime Claude CLI autopublica (C1). Paridad futuro-segura, no efectiva en 3 runtimes hoy.
- **Función pura:** sin efectos secundarios, sin I/O, mismo input → mismo output, nunca lanza.
- **Gate suave:** mecanismo que solo agrega warnings, nunca bloquea ni corrige.
- **Gate duro preexistente:** `_looks_like_epic` (tickets.py:5439) — única barrera que evita publicar no-épicas; corre DESPUÉS del saneamiento.
- **RF-N:** bloque de requerimiento funcional `<h2>RF-N ...</h2>` dentro de la épica.
- **process_catalog:** lista `[{name, purpose, kind}]` en `client_profile`, fuente de verdad de procesos del proyecto; mismo dato que `build_process_dictionary_block` inyecta al agente.
- **Observatorio:** `GroundingObservatoryCard` (Plan 44), que ya muestra `metadata["grounding_warnings"]` — canal de visualización reusado, cero UI nueva.

### Orden de implementación (numerado, por dependencia)
1. **F0** — registrar las 3 flags + `.env.example` + tests de flags.
2. **F1** — `_sanitize_epic_html` + helper `_dedup_identical_rf_blocks` (clave explícita, SIN renumeración) + golden-set test (idempotencia incluida) + cableado en `_extract_epic_html` + telemetría `epic_sanitize_changed` en `epic_summary` [ADICIÓN ARQUITECTO].
3. **F2** — `_structural_epic_warnings` + extensión de `_epic_grounding_warnings` + tests.
4. **F3** — `_catalog_grounding_warnings` + cableado best-effort + tests.
5. **F4** — Paso 0 de verificación; cablear `validate_pending_task_file.warnings` SOLO si no fluye ya; test de cableado.
6. **F5** — verificación de paridad y no-regresión (passthrough con flag OFF + correr todos los tests).

### Definition of Done (global, binario)
- [ ] Las 3 flags registradas con tipo `bool` y defaults: SANITIZE=True, STRUCTURE_WARNINGS=True, CATALOG_WARNINGS=False; documentadas en `.env.example`.
- [ ] `_sanitize_epic_html` implementada, pura, idempotente sobre todo el golden-set, cableada en `_extract_epic_html`.
- [ ] Caso Pacífico del golden-set pasa `_looks_like_epic == True` tras sanitizar.
- [ ] `test_epic_sanitize.py` verde (incluye idempotencia y passthrough con flag OFF).
- [ ] `_epic_grounding_warnings` extendida con warnings estructurales tras flag; `test_epic_structure_warnings.py` verde.
- [ ] `_catalog_grounding_warnings` implementada pura (sin I/O), cableada best-effort tras flag OFF; `test_catalog_grounding_warnings.py` verde.
- [ ] F4: o demostrado por grep que ya está cableado (no-op documentado), o `test_artifact_warnings_wiring.py` verde.
- [ ] F5: test de paridad/passthrough verde; sin regresión en `needs_review` respecto del baseline.
- [ ] Ningún paso/checkbox/config/input nuevo para el operador (revisión manual del frontend: cero cambios de UI obligatorios; el Observatorio existente muestra los nuevos warnings).
- [ ] Verificado por grep que `autopublish_epic_from_run` tiene un solo llamante de producción (Claude CLI, 1163); documentado que la paridad es por punto de inserción único, NO cobertura efectiva de 3 runtimes (C1).
- [ ] `_sanitize_epic_html` NO renumera RF (C3); secuencia RF-1/RF-3 sale sin cambiar la numeración.
- [ ] `_catalog_grounding_warnings` no emite warning por prosa común ("proceso de carga"), sí por identificador real ausente (C4).
- [ ] [ADICIÓN ARQUITECTO] `epic_sanitize_changed` sellado dentro de `epic_summary` (sin nueva UI ni nueva key de metadata).

**Trabajo del operador en todo el plan: ninguno.**
