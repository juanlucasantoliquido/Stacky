# SDD — Mejoras QA UAT Agent: Experto Agenda Web + Anotaciones Visuales

**Versión**: 1.0  
**Fecha**: 2026-05-04  
**Autor**: StackyToolArchitect  
**Estado**: APROBADO — listo para implementación  
**Branches**:  
- Fase 1: `feature/stacky-qa-uat-agenda-expert`  
- Fase 2: `feature/stacky-qa-uat-screenshot-annotations`

---

## 1. CONTEXTO Y OBJETIVO

### Situación actual
El QA UAT Agent opera con conocimiento limitado de la Agenda Web:
- Solo reconoce **4 pantallas** (`FrmAgenda`, `FrmDetalleLote`, `FrmGestion`, `Login`) de un total de **~90 pantallas** disponibles.
- Las acciones Playwright soportadas son solo 6 (`navigate`, `click`, `fill`, `select`, `wait_networkidle`, `wait_visible`), insuficientes para simular a un QA experto.
- El system prompt del LLM tiene las pantallas hardcodeadas como lista fija en lugar de leerlas del catálogo.
- Sin anotaciones visuales en screenshots: el dossier no señala qué elemento estaba siendo manipulado o verificado.

### Objetivo
**Fase 1**: Convertir el agente en un QA experto en Agenda Web, con cobertura total de pantallas, acciones ricas, y zero duplicación de catálogos.  
**Fase 2**: Agregar anotaciones visuales (box rojo) en screenshots de evidencia sin impacto en la operatoria actual.

---

## 2. ALCANCE

### Fase 1 — feature/stacky-qa-uat-agenda-expert

| Componente | Tipo | Descripción |
|---|---|---|
| `agenda_screens.py` | **MODIFICAR** | Expandir `SUPPORTED_SCREENS` de 4 a ~90 pantallas reales de la Agenda Web |
| `data/agenda_glossary.json` | **MODIFICAR** | Agregar entradas para las pantallas nuevas más relevantes |
| `uat_scenario_compiler.py` | **MODIFICAR** | Ampliar `_SUPPORTED_ACTIONS` + hacer el system prompt dinámico (leer pantallas de `agenda_screens`) |
| `templates/playwright_test.spec.ts.j2` | **MODIFICAR** | Soporte de nuevas acciones en el template |

### Fase 2 — feature/stacky-qa-uat-screenshot-annotations

| Componente | Tipo | Descripción |
|---|---|---|
| `screenshot_annotator.py` | **NUEVO** | CLI + módulo: agrega box rojo sobre elemento en screenshot usando Pillow |
| `qa_uat_pipeline.py` | **MODIFICAR** | Agregar stage `annotator` (no-fatal) post-runner |
| `requirements.txt` | **MODIFICAR** | Agregar `Pillow>=10.0.0` |
| `templates/playwright_test.spec.ts.j2` | **MODIFICAR** | Capturar `boundingBox()` post-step y emitir `step_bboxes.json` |

---

## 3. DISEÑO DETALLADO

### 3.1 Fase 1 — Pantallas completas

#### 3.1.1 `agenda_screens.py` — Expansión del catálogo

**Estado previo**: 4 pantallas hardcodeadas  
**Estado objetivo**: 90 pantallas extraídas de `branches/NetCore/OnLine/AgendaWeb/` (fuente de verdad) + popups de `branches/Materialize/OnLine/AgendaWeb/`

**Categorías** (se mantienen en el frozenset, no como subclases — KISS):

| Categoría | Ejemplos |
|---|---|
| Pantallas principales | `FrmAgenda.aspx`, `FrmDetalleLote.aspx`, `FrmGestion.aspx`, `Login.aspx` (las 4 existentes) |
| Admin/Config | `FrmAdministrador.aspx`, `FrmParametros.aspx`, `FrmFeriados.aspx`, ... |
| Judicial | `FrmAgendaJudicial.aspx`, `FrmJDemanda.aspx`, `FrmJEmbargo.aspx`, ... |
| Reportes | `FrmReportes.aspx`, `FrmReporteOperativo.aspx`, `FrmInformes.aspx` |
| PopUps | `PopUpAgendar.aspx`, `PopUpNota.aspx`, `PopUpContactos.aspx`, ... |
| Otros | `WorkflowFrame.aspx`, `Errors.aspx`, `FrmBusqueda.aspx`, ... |

**API sin cambios** — `is_supported()`, `extract_from_text()`, `normalize()` siguen igual. Solo crece el frozenset.

**Impacto en `ui_map_builder.py`**: ya usa `is_supported()` → cualquier pantalla nueva pasará la validación automáticamente. Sin cambios.

**Impacto en `uat_scenario_compiler.py`**: el guard `if spec["pantalla"] not in _SUPPORTED_SCREENS` ya usa `_SUPPORTED_SCREENS` importado de `agenda_screens` → resuelve automáticamente.

#### 3.1.2 System prompt dinámico en `uat_scenario_compiler.py`

**Problema actual**: el system prompt tiene las pantallas hardcodeadas:
```python
"pantalla": one of ["FrmAgenda.aspx","FrmDetalleLote.aspx","FrmGestion.aspx","Login.aspx"]
```

**Solución**: reemplazar con lista dinámica generada desde `agenda_screens.SUPPORTED_SCREENS`:
```python
screens_hint = ", ".join(f'"{s}"' for s in sorted(agenda_screens.SUPPORTED_SCREENS))
system_prompt = f"""...
- "pantalla": one of [{screens_hint}]
..."""
```

**Consideración de tokens**: con ~90 pantallas × ~20 chars = ~1800 chars adicionales. El model gpt-4o-mini soporta 128k tokens. Impacto: insignificante.

#### 3.1.3 Nuevas acciones en `uat_scenario_compiler.py`

**Estado actual**:
```python
_SUPPORTED_ACTIONS = frozenset({
    "navigate", "click", "fill", "select", "wait_networkidle", "wait_visible"
})
```

**Estado objetivo** (añadir 8 acciones):
```python
_SUPPORTED_ACTIONS = frozenset({
    # existentes
    "navigate", "click", "fill", "select", "wait_networkidle", "wait_visible",
    # nuevas
    "press_key",       # teclado: Enter, Tab, Escape, F5, etc.
    "hover",           # hover sobre elemento (reveal tooltips/menus)
    "double_click",    # doble click (edit-in-place, expandir nodo)
    "check_checkbox",  # marcar checkbox (valor: "true"|"false")
    "select_radio",    # elegir radio button (valor: opción a seleccionar)
    "clear",           # limpiar campo sin fill (útil para dates/combos)
    "wait_for_text",   # esperar que texto aparezca en elemento
    "scroll_into_view", # hacer scroll hasta elemento antes de interactuar
})
```

**System prompt** — agregar al listado de pasos permitidos:
```
{"accion": "<navigate|click|fill|select|wait_networkidle|wait_visible|press_key|hover|double_click|check_checkbox|select_radio|clear|wait_for_text|scroll_into_view>", ...}
```

**Definiciones para el LLM** (bloque en system prompt):
```
Action semantics:
- press_key: valor = key name (e.g. "Enter", "Tab", "Escape", "F5")
- hover: valor = null (just hover to reveal tooltip/menu)
- double_click: valor = null
- check_checkbox: valor = "true" or "false"  
- select_radio: valor = option label or value to select
- clear: valor = null (clears the field)
- wait_for_text: valor = text to wait for in the element
- scroll_into_view: valor = null (scroll element into viewport)
```

#### 3.1.4 Template Playwright — nuevas acciones

El template `playwright_test.spec.ts.j2` genera el bloque de steps con `{% for paso in pasos %}`. Actualmente solo mapea `click`, `fill`, `select`, `navigate`, `wait_networkidle`, `wait_visible`.

**Agregar ramas para nuevas acciones**:
```typescript
{% elif paso.accion == 'press_key' %}
    await page.keyboard.press({{ paso.valor | tojson }});
{% elif paso.accion == 'hover' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).hover();
{% elif paso.accion == 'double_click' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).dblclick();
{% elif paso.accion == 'check_checkbox' %}
    {% if paso.valor == 'true' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).check();
    {% else %}
    await page.locator({{ ui_map[paso.target] | tojson }}).uncheck();
    {% endif %}
{% elif paso.accion == 'select_radio' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).check();
{% elif paso.accion == 'clear' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).clear();
{% elif paso.accion == 'wait_for_text' %}
    await expect(page.locator({{ ui_map[paso.target] | tojson }})).toContainText({{ paso.valor | tojson }}, { timeout: 10000 });
{% elif paso.accion == 'scroll_into_view' %}
    await page.locator({{ ui_map[paso.target] | tojson }}).scrollIntoViewIfNeeded();
```

---

### 3.2 Fase 2 — Anotaciones visuales en screenshots

#### 3.2.1 `screenshot_annotator.py` — Módulo nuevo

**Responsabilidades**:
1. Leer `step_bboxes.json` de un directorio de evidencia de un escenario
2. Para cada step con bbox registrado, abrir el screenshot correspondiente y dibujar un box rojo con `Pillow`
3. Guardar imagen anotada como `step_NN_after_annotated.png` (NO sobrescribir el original)
4. Retornar JSON `{ok, annotated: N, skipped: N, errors: [...]}`

**Contrato de entrada** (`step_bboxes.json`):
```json
[
  {
    "step_index": 1,
    "screenshot_path": "evidence/65/P01/step_01_after.png",
    "target": "select_empresa",
    "bbox": {"x": 120, "y": 80, "width": 200, "height": 30}
  }
]
```

**Contrato de salida**:
```json
{
  "ok": true,
  "annotated": 3,
  "skipped": 0,
  "errors": [],
  "annotated_paths": ["evidence/65/P01/step_01_after_annotated.png", ...]
}
```

**Estilo box**: rojo (`#FF0000`), borde 3px, sin relleno (transparente). No se dibuja texto sobre la imagen.

**Fallback**: si Pillow no está instalado → log warning + retorna `{ok: true, annotated: 0, skipped: N, errors: ["pillow_not_installed"]}`. El pipeline continúa sin anotaciones.

#### 3.2.2 `playwright_test.spec.ts.j2` — Captura de bbox

Agregar un bloque `afterStep` (en `test.afterEach` o inline) que capture `boundingBox()` del selector activo y lo appendee a `step_bboxes.json`:

```typescript
// Capture bbox after each interaction
const bboxEntry = {
  step_index: {{ loop.index }},
  screenshot_path: 'evidence/{{ ticket_id }}/{{ scenario_id }}/step_{{ "%02d"|format(loop.index) }}_after.png',
  target: {{ paso.target | tojson }},
  bbox: await page.locator(stepSelector).boundingBox().catch(() => null)
};
```

**Acumulador al final del test** (en `afterEach`):
```typescript
const bboxPath = 'evidence/{{ ticket_id }}/{{ scenario_id }}/step_bboxes.json';
fs.writeFileSync(bboxPath, JSON.stringify(stepBboxes, null, 2));
```

**Condición**: solo para acciones interactivas (`click`, `fill`, `select`, `double_click`, `check_checkbox`, `select_radio`, `hover`). Para `navigate`, `press_key`, `wait_*` no aplica.

#### 3.2.3 Pipeline — stage `annotator` (no-fatal)

Se agrega después del stage `runner` (index 6) en `qa_uat_pipeline.py`:

```
reader → ui_map → compiler → preconditions → generator → runner → annotator → evaluator → failure_analyzer → dossier → publisher
```

**Comportamiento**:
- Si Pillow no está disponible → `stages["annotator"] = {"ok": True, "skipped": True, "reason": "pillow_not_available"}`. Pipeline continúa.
- Si `step_bboxes.json` no existe para un escenario → ese escenario se salta silenciosamente.
- Si falla para un escenario específico → log warning, ese escenario queda sin anotar, los demás se procesan.
- **NUNCA** retorna fatal. El dossier funciona igual con o sin imágenes anotadas.

**Prioridad de imagen en dossier**: si existe `step_NN_after_annotated.png` → usar esa en el dossier. Sino, usar `step_NN_after.png`.

#### 3.2.4 `requirements.txt` — Agregar Pillow

```
Pillow>=10.0.0
```

---

## 4. IMPACTOS Y RIESGOS

### 4.1 Impacto en pipeline existente

| Cambio | Riesgo | Mitigación |
|---|---|---|
| 90 pantallas en `SUPPORTED_SCREENS` | System prompt más largo (~1800 chars) | < 0.1% del budget de tokens gpt-4o-mini. Insignificante. |
| Nuevas acciones en compiler | LLM puede generar acciones no existentes antes | El guard `_SUPPORTED_ACTIONS` ya filtra; ahora simplemente no descarta acciones válidas |
| Stage annotator no-fatal | Pillow falla → stage se omite | Implementado como try/except + skip explícito |
| `step_bboxes.json` no existente | Tests existentes (sin bbox) no se anotan | Anotador solo procesa si el JSON existe. Sin cambios para tests actuales |

### 4.2 Compatibilidad hacia atrás

- Tests existentes (tickets 57, 65, 70) **no cambian** de comportamiento.
- El pipeline sin `--no-annotate-screenshots` intenta anotar. Sin Pillow → silenciosamente omite.
- `agenda_screens.SUPPORTED_SCREENS` ahora es más grande pero la API es la misma.

### 4.3 Rendimiento Fase 2

- `Pillow.Image.open()` + `ImageDraw.rectangle()` + `save()` ≈ 30-80ms por imagen.
- Con 6 steps × 1 screenshot = 6 imágenes × 80ms = **480ms adicionales máximo** sobre un pipeline de ~120s.
- **Impacto total estimado: < 0.4%**. Aceptable.

---

## 5. CRITERIOS DE ACEPTACIÓN

### Fase 1
- [ ] `agenda_screens.SUPPORTED_SCREENS` contiene todas las pantallas de `branches/NetCore/OnLine/AgendaWeb/` y los PopUps de `branches/Materialize/`
- [ ] `python uat_scenario_compiler.py --ticket 70` produce mismo verdict que antes del cambio
- [ ] El system prompt del compiler no tiene pantallas hardcodeadas
- [ ] Acciones `press_key`, `hover`, `double_click`, `check_checkbox`, `select_radio`, `clear`, `wait_for_text`, `scroll_into_view` son reconocidas por el compiler y generan código Playwright válido
- [ ] `python qa_uat_pipeline.py --ticket 65 ... --mode dry-run` termina exit 0

### Fase 2
- [ ] `pip install Pillow` no rompe nada si Pillow ya está instalado
- [ ] Sin Pillow: pipeline termina exit 0, `stages.annotator.skipped = true`
- [ ] Con Pillow: screenshots anotados generados junto a los originales
- [ ] Original `step_NN_after.png` nunca se sobrescribe
- [ ] El dossier referencia la imagen anotada cuando existe

---

## 6. PLAN DE ROLLBACK

### Fase 1
- Revertir `agenda_screens.py` al estado anterior (4 pantallas) → sin impacto en runtime porque la lógica es idéntica.
- Revertir `uat_scenario_compiler.py` → reemplazar el bloque de acciones nuevas por el frozenset original.

### Fase 2
- Remover el stage `annotator` de `qa_uat_pipeline.py` (3 líneas).
- Remover `screenshot_annotator.py`.
- Remover `Pillow` de `requirements.txt`.
- Revertir el bloque bbox del template `.j2`.

---

## 7. ORDEN DE IMPLEMENTACIÓN

```
[Fase 1]
1. agenda_screens.py        ← ampliar frozenset (sin dependencias)
2. data/agenda_glossary.json ← agregar entradas pantallas nuevas relevantes
3. uat_scenario_compiler.py  ← acciones nuevas + prompt dinámico (depende de 1)
4. playwright_test.spec.ts.j2 ← template nuevas acciones (depende de 3)

[Fase 2]
5. requirements.txt          ← agregar Pillow
6. screenshot_annotator.py   ← módulo nuevo (sin dependencias externas excepto Pillow)
7. playwright_test.spec.ts.j2 ← bloque bbox capture (depende de 6)
8. qa_uat_pipeline.py        ← stage annotator (depende de 6)
```

**PR Fase 1**: `feature/stacky-qa-uat-agenda-expert`  
**PR Fase 2**: `feature/stacky-qa-uat-screenshot-annotations` (depende de Fase 1 mergeada)
