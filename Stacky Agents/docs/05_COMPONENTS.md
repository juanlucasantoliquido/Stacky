# 05 — Catálogo de componentes UI

> Cada componente declara: nombre, props, estados internos, eventos que emite, dependencias.
> Los componentes que viven en `frontend/src/components/` están alineados con este catálogo.

---

## Convenciones

- **Stack:** React 18 + TypeScript + Vite + Zustand (state global liviano) + TanStack Query (server state).
- **Estilos:** CSS modules + tokens en `theme.ts`. No CSS-in-JS pesado para mantener bundle chico.
- **Tests:** Vitest + Testing Library. Cada componente con un test happy path mínimo.
- **Naming:** PascalCase, un componente por archivo. Co-locar `Component.tsx`, `Component.module.css`, `Component.test.tsx`.

---

## Árbol de componentes

```
<App>
└── <Workbench>                       ← page principal
    ├── <TopBar>
    │   ├── <ProjectSelector />
    │   ├── <ThemeToggle />
    │   └── <UserMenu />
    │
    ├── <PackBanner />                ← visible si hay pack en curso
    │
    ├── <LeftColumn>
    │   ├── <TicketSelector />
    │   │   └── <TicketRow />*
    │   ├── <AgentSelector />
    │   │   └── <AgentCard />*
    │   └── <PackList />
    │       └── <PackItem />*
    │
    ├── <CenterColumn>
    │   └── <InputContextEditor>
    │       ├── <ContextBlock />*
    │       │   ├── <AutoBlockContent />
    │       │   ├── <EditableBlockContent />
    │       │   └── <ChoiceBlockContent />
    │       ├── <TokenCounter />
    │       └── <RunButton />
    │
    └── <RightColumn>
        ├── <OutputPanel />
        │   ├── <OutputHeader />
        │   ├── <OutputBody />        ← markdown renderer
        │   └── <OutputActions />
        ├── <LogsPanel />
        │   └── <LogLine />*
        └── <ExecutionHistory />
            └── <ExecutionRow />*
```

---

## Componentes raíz

### `<Workbench>`
Page principal — layout 3 columnas + topbar.

**Props:** ninguna (lee del store).
**Estado:** ninguno propio.
**Dependencias:** `useWorkbenchStore`, `useTicketsQuery`.

---

### `<TopBar>`

**Props:** ninguna.
**Subcomponentes:**
- `<ProjectSelector>` — dropdown de proyectos. Default "RSPacifico".
- `<ThemeToggle>` — light/dark.
- `<UserMenu>` — avatar + logout (placeholder).

---

### `<PackBanner>`

Renderiza `null` si no hay pack activo.

**Props:**
```ts
{ pack: PackRunState | null }
```

**Renderiza:** stepper horizontal con los pasos, paso actual destacado, botón Pausar/Reanudar/Abandonar.

**Eventos:**
- `onPause()` → `POST /api/packs/:id/pause`
- `onResume()` → `POST /api/packs/:id/resume`
- `onAbandon()` → confirmación + `DELETE /api/packs/:id`

---

## Columna izquierda

### `<TicketSelector>`

**Props:** ninguna (lee de `useTicketsQuery`).
**Estado interno:** `searchTerm: string`.
**Renderiza:** input de búsqueda + grupos de `<TicketRow>` (En curso / Sin ejecuciones / Completados).

**Eventos:**
- `onSelect(ticketId)` → `workbenchStore.setActiveTicket(ticketId)`.

**Auto-refresh:** TanStack Query con `refetchInterval: 60_000`.

---

### `<TicketRow>`

**Props:**
```ts
{
  ticket: Ticket;
  active: boolean;
  onSelect: (id: number) => void;
}
```

**Visual:** ID + título corto (max 60 chars con ellipsis) + badge de estado ADO + texto muted con "última exec hace Xmin".

---

### `<AgentSelector>`

**Props:** ninguna.
**Renderiza:** lista de `<AgentCard>` para los 5 agentes.

**Datos:** estáticos por ahora (definidos en `frontend/src/agents.ts`). En futuro: `GET /api/agents`.

---

### `<AgentCard>`

**Props:**
```ts
{
  agent: AgentDefinition;     // { type, name, icon, description, inputs, outputs }
  selected: boolean;
  disabled?: boolean;          // true si falta seleccionar ticket
  onSelect: (type: AgentType) => void;
}
```

**Visual:** card compacta con ícono, nombre, descripción 1 línea, "in:" "out:" en muted.
**Estados:** default | hover | selected | disabled.
**Tooltip on hover:** preview corto del system prompt (3 líneas).

---

### `<PackList>`

**Props:** ninguna.
**Datos:** `GET /api/packs`.
**Renderiza:** lista de `<PackItem>`.

---

### `<PackItem>`

**Props:**
```ts
{
  pack: PackDefinition;
  onLaunch: (packId: string) => void;
}
```

**Click:** abre modal `<PackLauncherModal>`.

---

### `<PackLauncherModal>`

**Props:**
```ts
{
  pack: PackDefinition;
  open: boolean;
  onClose: () => void;
  onStart: (config: PackStartConfig) => void;
}
```

**Renderiza:** descripción del pack, lista de pasos, checkboxes de opciones, botones Cancel/Iniciar.

---

## Columna central

### `<InputContextEditor>`

El componente más importante de la app. Es un **editor estructurado**, no un textarea libre.

**Props:** ninguna (lee de `useWorkbenchStore`).

**Estado interno:**
```ts
{
  blocks: ContextBlock[];     // bloques actualmente visibles
  collapsedBlocks: Set<string>;
}
```

**Comportamiento:**
- Cuando cambia `activeTicket` o `activeAgent`, llama a `useAutoFillBlocks(ticket, agent)` que devuelve los bloques sugeridos.
- Cada bloque puede ser `auto`, `editable` o `choice`.
- El usuario puede agregar bloques manuales con un botón `[+ agregar bloque]`.
- El botón Run lee el estado de bloques, los serializa a un payload, llama a la API.

**Eventos:**
- `onRun()` → `POST /api/agents/run`.

---

### `<ContextBlock>`

**Props:**
```ts
{
  block: ContextBlock;        // { id, kind, title, content, source }
  collapsed: boolean;
  onToggleCollapse: () => void;
  onRemove?: () => void;
  onChange?: (content: string) => void;
}
```

**Renderiza header (título + iconos collapse/×) + body según `kind`:**
- `auto`: `<AutoBlockContent>` (read-only con badge `[auto]`)
- `editable`: `<EditableBlockContent>` (textarea autoresize)
- `choice`: `<ChoiceBlockContent>` (lista de checkboxes)

---

### `<AutoBlockContent>`
Render markdown con clase `prose-sm`. Muestra metadata del origen ("desde exec #20").

### `<EditableBlockContent>`
`<textarea>` con autoresize. Placeholder con instrucciones contextual ("ej: notas adicionales, restricciones, deadlines").

### `<ChoiceBlockContent>`
Lista de items con checkbox. Cada item con label y, opcionalmente, preview expandible.

---

### `<TokenCounter>`

**Props:**
```ts
{ current: number; max: number; }
```

**Visual:** "8.4k / 200k" con barra horizontal pequeña debajo. Color por threshold:
- < 60% → text-muted
- 60–85% → warn
- > 85% → danger

**Cálculo:** estimación cliente vía `gpt-tokenizer` o fallback (chars / 4).

---

### `<RunButton>`

**Props:**
```ts
{
  state: 'idle' | 'running' | 'cancelling';
  disabled?: boolean;
  onClick: () => void;
  onCancel?: () => void;
}
```

**Visual states:**
- `idle` enabled: pill grande primario "▶ RUN AGENT".
- `idle` disabled: greyed con tooltip explicando por qué (faltó algo).
- `running`: "Running ▮▮" con spinner pequeño + botón × para cancelar.
- `cancelling`: "Cancelling..." disabled.

**Atajo de teclado:** `Cmd/Ctrl + Enter` desde el editor.

---

## Columna derecha

### `<OutputPanel>`

**Props:**
```ts
{
  execution: AgentExecution | null;     // null = empty state
  loading: boolean;
  comparingWith?: AgentExecution;        // si hay diff activo
}
```

**Renderiza:**
- Si `null`: empty state con "Press Run".
- Si `loading`: skeleton con shimmer.
- Si execution presente sin comparingWith: `<OutputHeader>` + `<OutputBody>` + `<OutputActions>`.
- Si comparingWith: `<DiffView>` lado a lado.

---

### `<OutputHeader>`

**Props:**
```ts
{ execution: AgentExecution }
```

**Visual:** "OUTPUT — exec #N — Agent — date — duration — status icon".

---

### `<OutputBody>`

**Props:**
```ts
{ output: string; format: 'markdown' | 'json' | 'plain' }
```

**Renderer:** `react-markdown` con `remark-gfm` + `rehype-highlight` (Prism).

---

### `<OutputActions>`

**Props:**
```ts
{
  execution: AgentExecution;
  onApprove: () => void;
  onEditAndRerun: () => void;
  onSendToAdo: () => void;
  onDiscard: () => void;
  onCopy: () => void;
  onDownload: () => void;
  onDiffWith?: (otherExecId: number) => void;
}
```

**Layout:** botones primarios (Approve, Edit&Re-run, Send to ADO, Discard) en una fila + secundarios (Copy, Download, Diff) en una segunda fila como icon buttons con tooltip.

---

### `<DiffView>`

**Props:**
```ts
{ left: AgentExecution; right: AgentExecution }
```

**Renderer:** `react-diff-viewer-continued` con tema custom alineado a la paleta.

---

### `<LogsPanel>`

**Props:**
```ts
{
  executionId: number | null;
  live: boolean;     // true mientras la exec está corriendo
}
```

**Estado interno:**
```ts
{
  lines: LogLine[];
  autoScroll: boolean;
  filters: { info, warn, error, debug };
  expanded: Set<groupId>;
}
```

**Comportamiento:**
- Si `live`: abre EventSource a `/api/executions/:id/logs/stream`.
- Si no: `GET /api/executions/:id/logs` una sola vez.
- Auto-scroll mientras el usuario está en el bottom; pausa si scrolleó arriba.
- Filtros toggleables persistidos en `localStorage`.

---

### `<LogLine>`

**Props:**
```ts
{ line: LogLine }
// LogLine = { timestamp, level, message, indent, group?: string }
```

**Visual:** timestamp muted + ícono de nivel + mensaje. Indent visual proporcional al `indent`.

---

### `<ExecutionHistory>`

**Props:**
```ts
{ ticketId: number }
```

**Datos:** `useExecutionsByTicket(ticketId)` (TanStack Query).

**Renderiza:** filtros (all / ok / failed; agente) + lista de `<ExecutionRow>`.

---

### `<ExecutionRow>`

**Props:**
```ts
{
  execution: AgentExecution;
  active: boolean;
  onSelect: () => void;
}
```

**Visual:** `#N agentName — date — status icon`. Active state con borde lateral.

**Click:** carga la exec en el OutputPanel (modo lectura).

---

## Hooks compartidos

### `useWorkbenchStore` (Zustand)

```ts
type WorkbenchState = {
  activeTicketId: number | null;
  activeAgentType: AgentType | null;
  activeExecutionId: number | null;     // qué exec se ve en OutputPanel
  blocks: ContextBlock[];
  packRun: PackRunState | null;
  setActiveTicket: (id: number) => void;
  setActiveAgent: (t: AgentType) => void;
  setActiveExecution: (id: number | null) => void;
  setBlocks: (b: ContextBlock[]) => void;
  // ...
};
```

### `useAgentRun()`

Mutation que dispara `POST /api/agents/run`, conecta al SSE de logs, actualiza el OutputPanel con texto streamed.

### `useTicketsQuery()`
TanStack Query con polling 60s.

### `useExecutionsByTicket(ticketId)`
TanStack Query, invalida automáticamente al completar una nueva exec.

### `useAutoFillBlocks(ticket, agent)`
Lógica que arma los bloques sugeridos según ticket + agente. Cliente puro (no hace fetch — usa lo que ya está en memoria).

---

## Patrones reutilizables

### `<Card>`
Wrapper con padding 16, border, radius 8. Acepta `selected` y `interactive` como props.

### `<Tooltip>`
Wrapper sobre `@radix-ui/react-tooltip`. Tema custom.

### `<Modal>`
Wrapper sobre `@radix-ui/react-dialog`. Soporta `size: sm | md | lg`.

### `<Toast>`
`react-hot-toast` con tema custom. Niveles: success, error, info, warn.

### `<EmptyState>`
Card con ilustración + título + subtítulo + CTA opcional.

### `<Skeleton>`
Block de loading shimmer.

---

## Estados de error compartidos

Componente `<ErrorBoundary>` global captura errores de render. Muestra fallback con botón "Reportar bug".

Para errores de red: TanStack Query muestra toast automático + permite retry.

---

## Telemetría (placeholder)

Cada acción del usuario emite un evento al `analyticsBus`:
- `agent.run.click`
- `agent.run.completed`
- `execution.approved`
- `execution.discarded`
- `pack.started`
- `pack.completed`
- `chain.block.removed`

Por ahora `console.debug`; futuro: backend `/api/telemetry`.
