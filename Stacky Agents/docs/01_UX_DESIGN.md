# 01 — Diseño UX

## Principios visuales

1. **Editor-first** — la pantalla principal NO es un dashboard de monitoreo. Es un editor de contexto + botón Run + panel de output. La metáfora es Postman / Jupyter, no Jenkins.
2. **Tres zonas estables** — izquierda (qué ticket / qué agente), centro (qué le mando), derecha (qué me devuelve + historial). Esa estructura no cambia entre estados.
3. **Density over spacing** — el operador es técnico y va a leer mucho texto. Tipografía mono para outputs, sans para chrome, scrollbars siempre visibles.
4. **Modo oscuro por default**, modo claro disponible. La paleta es plana y de alto contraste — no skeumórfica.
5. **Loaders informativos, no genéricos** — un agente corriendo muestra qué paso está ejecutando ("leyendo docs funcionales", "consultando BD", "redactando análisis"), no un spinner ciego.

---

## Layout maestro (low fidelity, ASCII)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Stacky Agents              ◯ Project: RSPacifico ▼          ⚙  ?  ◐ Theme   👤 │
├──────────────┬────────────────────────────────────────┬──────────────────────────┤
│              │                                         │                          │
│  TICKET      │         INPUT CONTEXT EDITOR            │   OUTPUT                 │
│  ──────      │  ┌────────────────────────────────┐    │   ──────                 │
│ [search...]  │  │ # Ticket ADO-1234              │    │  (vacío hasta Run)       │
│              │  │ # Agente: Technical            │    │                          │
│ ▣ ADO-1234   │  │                                │    │   ┌──────────────────┐  │
│   "RF: nuevo │  │ ## Funcional aprobado ───────  │    │   │ select agent →   │  │
│    flujo..." │  │ {auto-filled de exec #20}      │    │   │ press Run        │  │
│              │  │                                │    │   └──────────────────┘  │
│ □ ADO-1235   │  │ ## Notas adicionales ────────  │    │                          │
│ □ ADO-1236   │  │ <vacío — escribir aquí>        │    │   LOGS                   │
│              │  │                                │    │   ────                   │
│  AGENT       │  │ ## Auto-fill disponible ─────  │    │   (vacío)                │
│  ──────      │  │  ☑ exec #19 (business)         │    │                          │
│ ◉ Business   │  │  ☑ exec #20 (functional)       │    │                          │
│ ◉ Functional │  │  ☐ exec #21 (technical, prev)  │    │   HISTORIAL DEL TICKET   │
│ ◉ Technical  │  │  ☐ archivos del repo: 3 dets   │    │   ──────────────────     │
│ ◉ Developer  │  │                                │    │   #22 technical 16:45 ✓  │
│ ◉ QA         │  │                                │    │   #21 technical 14:30 ✗  │
│              │  │                                │    │   #20 functional 11:15 ✓ │
│  PACKS       │  └────────────────────────────────┘    │   #19 business 11:08 ✓   │
│  ──────      │                                         │   #18 business 11:02 ✗   │
│ ▶ Desarrollo │   tokens: 8.4k / 200k                   │                          │
│ ▶ QA Express │   [ Clear ] [ Save preset ]  [▶ RUN ]  │                          │
│              │                                         │                          │
└──────────────┴────────────────────────────────────────┴──────────────────────────┘
```

Tres columnas con anchos fijos en desktop:
- Izquierda: 260 px (selector de ticket + agente + packs).
- Centro: flex (input editor — la zona donde el humano trabaja).
- Derecha: 420 px (output + logs + historial).

En tablet/mobile se colapsan a stack vertical, pero el target principal es desktop ≥ 1440 px.

---

## Estados de pantalla (high level)

### Estado 1 — Empty (sin ticket seleccionado)
- Centro: hero con copy "Seleccioná un ticket o pegá un ID en la barra superior".
- Derecha: hidden o gris.

### Estado 2 — Ticket seleccionado, sin agente
- Centro: vista resumen del ticket (title, description, ADO state, último exec).
- Derecha: historial completo del ticket.
- Agent selector destacado para invitar al click.

### Estado 3 — Ticket + agente seleccionados (pre-run)
- Centro: editor poblado con auto-fill propuesto (checkboxes editables).
- Derecha: panel output vacío con CTA "Press Run".
- Botón Run habilitado.

### Estado 4 — Running
- Botón Run → "Running" con stop button (cancel).
- Logs panel abierto, streameando en vivo.
- Output panel muestra texto incremental (si el agente devuelve streaming) o spinner con etapa actual.

### Estado 5 — Completed (success)
- Output panel renderizado (markdown, código según tipo).
- Botones de acción: `[ Approve ]` `[ Edit & Re-run ]` `[ Send to ADO ]` `[ Discard ]`.
- Historial agrega la nueva fila al tope.

### Estado 6 — Completed (error)
- Output panel muestra el error en card roja.
- Logs auto-expandidos con la línea del error resaltada.
- Botones: `[ Retry ]` `[ Edit context ]` `[ Reportar bug ]`.

### Estado 7 — Pack en ejecución
- Banner superior: "Pack Desarrollo en progreso — paso 2/4 (Technical)".
- Stepper visual arriba: Functional ✓ → Technical ▶ → Developer ○ → QA ○.
- Editor pre-cargado con el contexto del paso actual; el resto del layout funciona normal.

---

## Wireframes high fidelity por componente

### TicketSelector

```
┌─────────────────────────────────┐
│ TICKETS                         │
├─────────────────────────────────┤
│ 🔍 Buscar ticket…               │
│                                 │
│ ─── En curso ───                │
│ ▣ ADO-1234  • Functional        │
│   RF-008 nuevo flujo de cobros  │
│   última exec hace 18 min       │
│                                 │
│ ─── Sin ejecuciones ───         │
│ □ ADO-1235  • Tech review       │
│   RF-011 reporte mensual        │
│                                 │
│ □ ADO-1236  • To Do             │
│   RF-013 ajuste pantalla agenda │
│                                 │
│ ─── Completados (semana) ───    │
│ ✓ ADO-1230  • Done              │
└─────────────────────────────────┘
```

Comportamiento:
- Click selecciona, doble click abre detalle.
- Ítem activo con borde lateral colorado.
- Filtro implícito: el proyecto activo (top bar).
- Auto-refresh cada 60s (poll a `/api/tickets`).

### AgentSelector

```
┌─────────────────────────────────┐
│ AGENTES                         │
├─────────────────────────────────┤
│ ┌───────────────────────────┐   │
│ │ 🧠 Business                │   │
│ │ Texto libre → Epics        │   │
│ │ in: brief / conv           │   │
│ │ out: HTML estructurado     │   │
│ └───────────────────────────┘   │
│                                 │
│ ┌───────────────────────────┐   │
│ │ 📋 Functional             │   │
│ │ Epic → análisis cobertura │   │
│ │ in: Epic ADO + docs       │   │
│ │ out: análisis + plan      │   │
│ └───────────────────────────┘   │
│                                 │
│ ┌───────────────────────────┐◀──┤  ← seleccionado (highlight)
│ │ 🔧 Technical              │   │
│ │ Funcional → técnico       │   │
│ │ in: Task + funcional      │   │
│ │ out: 5-sec analysis       │   │
│ └───────────────────────────┘   │
│                                 │
│ ┌───────────────────────────┐   │
│ │ 💻 Developer              │   │
│ │ Análisis → código         │   │
│ └───────────────────────────┘   │
│                                 │
│ ┌───────────────────────────┐   │
│ │ ✅ QA                      │   │
│ │ Implementación → veredicto│   │
│ └───────────────────────────┘   │
└─────────────────────────────────┘
```

Cada AgentCard:
- ícono distintivo + nombre + descripción 1 línea
- "in:" "out:" en muted text
- estado seleccionado con borde + fondo sutil + chevron izquierdo
- tooltip al hover muestra el system prompt (preview, no editable acá)

### InputContextEditor

Es la zona crítica. Es un editor textual con secciones colapsables y "smart blocks".

```
┌──────────────────────────────────────────────────────────────────┐
│ INPUT CONTEXT — Technical Agent — ADO-1234                       │
├──────────────────────────────────────────────────────────────────┤
│  ▼ Ticket metadata                                       [auto] │
│    Title: RF-008 nuevo flujo de cobros                          │
│    Type: Task                                                   │
│    State: Tech review                                           │
│    Priority: 2                                                  │
│                                                                  │
│  ▼ Análisis funcional aprobado                          [auto] │
│    [exec #20 — Functional — 2026-04-22 11:15]                  │
│    ┌───────────────────────────────────────────────────┐        │
│    │ # Análisis funcional RF-008                       │        │
│    │ ## Cobertura: GAP MENOR                           │        │
│    │ ...                                                │        │
│    └───────────────────────────────────────────────────┘        │
│                                                                  │
│  ▼ Documentación técnica selectiva                     [auto] │
│    ☑ trunk/OnLine/Cobranzas/CobranzaController.cs              │
│    ☑ trunk/lib/Pacifico.Common/CobranzaService.cs              │
│    ☐ trunk/Batch/CobranzaBatch/                                │
│    [+ agregar archivo manual]                                  │
│                                                                  │
│  ▼ Notas adicionales                                  [editable]│
│    ┌───────────────────────────────────────────────────┐        │
│    │ Tener en cuenta que el cliente pidió que la nueva │        │
│    │ pantalla mantenga compatibilidad con clientes mob │        │
│    │ ya que tienen workflow legacy.                    │        │
│    └───────────────────────────────────────────────────┘        │
│                                                                  │
│  ▶ Auto-fill disponible (3)                          [click]   │
│  ▶ Variables del proyecto                            [auto]    │
│                                                                  │
│  ──────────────────────────────────────────────────────────     │
│  Tokens estimados: 8.4k / 200k    [ Save preset ]  [ Clear ]    │
│                                                                  │
│                                              [ ▶ RUN AGENT ]    │
└──────────────────────────────────────────────────────────────────┘
```

Comportamiento clave:
- Los bloques `[auto]` se rellenan al cambiar de ticket o agente; el humano puede colapsar / quitar / editar.
- Los bloques `[editable]` son texto libre.
- Los bloques `[click]` están colapsados por default y se expanden bajo demanda (no consumen tokens si están cerrados, pero se loguea su disponibilidad).
- Tokens estimados se calculan en cliente (tiktoken-equivalent en JS) en cada cambio.
- El botón Run pulsea suavemente cuando todo está listo y hay contexto cargado.
- Si el contexto excede el límite, el botón se deshabilita y aparece warning con sugerencia ("podés sacar el bloque de docs y dejar sólo los 2 archivos relevantes").

### OutputPanel

```
┌────────────────────────────────────┐
│ OUTPUT — exec #23 — Technical     │
│ 2026-04-23 09:10 ─ 14s ─ ✓        │
├────────────────────────────────────┤
│                                    │
│ # 🔬 ANÁLISIS TÉCNICO — ADO-1234   │
│                                    │
│ ## 1. Traducción funcional → téc.  │
│ Flujo actual: ...                  │
│ Flujo propuesto: ...               │
│                                    │
│ ## 2. Alcance de cambios           │
│ | Archivo | Clase | Método ...     │
│ | ─────── | ───── | ─────────      │
│ | Cobr... | Cobr  | Procesar       │
│                                    │
│ ## 3. Plan de pruebas técnico      │
│ ...                                │
│                                    │
├────────────────────────────────────┤
│ [Approve] [Edit&Re-run] [→ ADO]   │
│ [Copy] [Download .md] [Diff vs#22]│
└────────────────────────────────────┘
```

- Renderiza markdown con syntax highlight para código.
- Header sticky con metadata (id, agente, duración, status).
- Footer con acciones primarias (`Approve`, `Edit & Re-run`, `Send to ADO`) y secundarias (`Copy`, `Download`, `Diff`).
- "Diff vs #22" sólo aparece si hay ejecución previa del mismo agente en el mismo ticket.

### LogsPanel

```
┌────────────────────────────────────┐
│ LOGS — exec #23                   │
├────────────────────────────────────┤
│ 09:10:01  ▶ start                  │
│ 09:10:01    fetched ticket meta    │
│ 09:10:02    found 3 prior execs    │
│ 09:10:02    chained input from #22 │
│ 09:10:03  ▼ explore code           │
│ 09:10:05    sub-agent ONLINE: 4 fs │
│ 09:10:08    sub-agent BATCH: skip  │
│ 09:10:10  ▼ docs lookup            │
│ 09:10:11    INDICE_MAESTRO loaded  │
│ 09:10:12  ▼ db query (SELECT only) │
│ 09:10:13    RIDIOMA: 2 entradas    │
│ 09:10:14  ▶ compose output         │
│ 09:10:15  ✓ done (14s, 1.8k tok)   │
└────────────────────────────────────┘
```

- Auto-scroll, pero pausa si el usuario scrollea hacia arriba.
- Niveles colapsables (▼ / ▶).
- Filtros: `info | warn | error | debug` toggles arriba.
- En modo debug muestra el prompt completo y la respuesta cruda.

### ExecutionHistory

```
┌────────────────────────────────────┐
│ HISTORIAL — ADO-1234              │
├────────────────────────────────────┤
│ ▣ #23 technical    today 09:10 ✓  │
│ □ #22 technical    yest. 16:45 ✗  │
│ □ #21 technical    yest. 14:30 ✗  │
│ □ #20 functional   yest. 11:15 ✓  │
│ □ #19 business     yest. 11:08 ✓  │
│ □ #18 business     yest. 11:02 ✗  │
│                                    │
│ filtros: [all] [✓ ok] [✗ failed]  │
│ agente: [all] [biz][fn][tech]...  │
└────────────────────────────────────┘
```

- Click en una fila carga esa ejecución en el OutputPanel (modo lectura) y permite "Clone & edit".
- Iconos: ✓ aprobada, ✗ fallida o descartada, ⏳ corriendo, ◐ completada sin aprobar.
- Filtros laterales para reducir ruido en tickets con mucho historial.

### PackLauncher

```
┌────────────────────────────────────┐
│ PACK — Desarrollo                 │
├────────────────────────────────────┤
│ Ejecuta los 4 agentes en orden    │
│ pero pidiendo confirmación entre  │
│ pasos.                             │
│                                    │
│ Pasos:                             │
│ 1. Functional                      │
│ 2. Technical                       │
│ 3. Developer                       │
│ 4. QA                              │
│                                    │
│ ☐ Skip si ya hay output aprobado  │
│ ☑ Detener al primer error         │
│                                    │
│ [ Cancel ]      [ Iniciar pack ]  │
└────────────────────────────────────┘
```

Cuando un pack está corriendo, el banner superior reemplaza ese modal por un stepper en la top bar.

---

## Sistema visual

### Colores (tema oscuro default)

| Token | Hex | Uso |
|---|---|---|
| `--bg-base` | `#0E1116` | fondo app |
| `--bg-panel` | `#161A21` | columnas y cards |
| `--bg-elev` | `#1E2330` | hover, modales |
| `--border` | `#2A3142` | separadores |
| `--text-primary` | `#E6E9F0` | texto principal |
| `--text-muted` | `#8B93A7` | metadata, hints |
| `--accent` | `#5B8DEF` | acción primaria, selección |
| `--accent-hot` | `#7AA8FF` | hover de acento |
| `--success` | `#39C28D` | ✓ aprobado |
| `--warn` | `#E5B649` | re-run sugerido |
| `--danger` | `#E5526B` | ✗ error |
| `--mono-bg` | `#0A0D12` | bloques de código |

### Tipografía

- Sans: `Inter, system-ui, -apple-system, sans-serif` — UI chrome y headings.
- Mono: `JetBrains Mono, Consolas, monospace` — outputs, logs, código.
- Escalas: `12 / 13 / 14 / 16 / 18 / 22 / 28`.
- Line-height generoso en outputs (1.6) para lectura larga.

### Spacing

Stack base de 4px. Componentes usan múltiplos: 4, 8, 12, 16, 24, 32. Padding interno de paneles: 16. Gap entre columnas: 1px (border).

### Iconografía

- `lucide-react` (consistente, MIT, ligero).
- Íconos de agentes: emoji-like pero monocromos (no real emoji para evitar problemas de render).
- Estados de ejecución: ✓ ✗ ⏳ ◐ con color semántico.

---

## Microinteracciones

| Interacción | Comportamiento |
|---|---|
| Hover sobre AgentCard | borde acento + leve elevación 2px |
| Click Run | botón se transforma en "Running ▮▮" con barra de progreso indeterminada arriba del editor |
| Llegada de log | el LogsPanel hace scroll suave + flash de la nueva línea |
| Output completado | shimmer breve sobre el OutputPanel + sonido opcional (toggle en settings) |
| Error | shake horizontal del OutputPanel + auto-expand de LogsPanel |
| Auto-fill toggle | el bloque colapsa/expande con animación 200ms ease-out |
| Token counter cerca del límite | el contador cambia de color (verde → amarillo → rojo) progresivamente |

---

## Accesibilidad

- Todo accionable es navegable con teclado. Atajos clave:
  - `g t` → focus TicketSelector
  - `g a` → focus AgentSelector
  - `g e` → focus editor
  - `cmd/ctrl + enter` → Run
  - `esc` → cerrar modal / cancelar run
- Contraste mínimo AA en texto principal.
- Loaders informan via `aria-live="polite"` qué etapa está corriendo.
- Semántica correcta: editor es `textarea` (no `div contenteditable` salvo upgrade futuro).

---

## Estados vacíos y onboarding

Primera vez que un usuario abre la app:

1. Banner superior: "👋 Bienvenido. Stacky Agents es un workbench: vos elegís el agente y vos lo corrés. [Tour guiado] [Skip]".
2. Si acepta el tour: 4 pasos con tooltip secuencial sobre TicketSelector → AgentSelector → Editor → Run.
3. Estado vacío del historial: ilustración minimalista + copy "Tu primera ejecución va a aparecer acá".

---

## Diferenciador UX vs Stacky Pipeline

| Feature | Pipeline | Agents |
|---|---|---|
| Pantalla principal | dashboard de monitoreo | workbench editable |
| Disparo de agente | cambio de estado ADO | click humano |
| Edición de contexto | imposible sin tocar código | UI nativa |
| Comparar 2 ejecuciones | imposible | side-by-side diff |
| Re-correr un agente | hay que revertir estado | "Clone & edit" |
| Onboarding nuevo operador | leer 5 docs internos | tour de 4 pasos en la UI |
