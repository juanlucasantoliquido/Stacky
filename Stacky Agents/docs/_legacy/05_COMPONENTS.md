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
<App>  (view: "team" | "workbench")
│
├── <TeamScreen>                       ← PANTALLA PRINCIPAL (default)
│   │   Props: onGoToWorkbench()
│   │
│   ├── <EmployeeCard />*              ← una card por agente en el equipo
│   │   └── <PixelAvatar />            ← avatar galería o base64, size lg
│   │   └── <AgentLaunchModal />       ← modal ticket → VS Code Chat
│   │       └── <PixelAvatar />        ← avatar size sm en header del modal
│   │
│   ├── <TeamManageDrawer />           ← drawer lateral: agregar agentes
│   │   ├── <PixelAvatar />*           ← preview avatar de cada agente
│   │   └── <AvatarPicker />           ← inline al seleccionar un agente
│   │
│   └── <EmployeeEditDrawer />         ← drawer lateral: editar empleado
│       ├── <PixelAvatar />            ← preview avatar actual (header)
│       └── <AvatarPicker />           ← selector completo
│
└── <Workbench>                        ← flujo avanzado (accesible desde TeamScreen)
    ├── <TopBar>                        ← botón "← Equipo" cuando onGoToTeam present
    │   ├── <ProjectSelector />
    │   ├── <ThemeToggle />
    │   └── <UserMenu />
    │
    ├── <PackBanner />                 ← visible si hay pack en curso
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
        │   ├── <OutputBody />         ← markdown renderer
        │   └── <OutputActions />
        ├── <LogsPanel />
        │   └── <LogLine />*
        └── <ExecutionHistory />
            └── <ExecutionRow />*
```

---

## Servicios (capa de persistencia)

### `preferences.ts` — `src/services/preferences.ts`

Wrapper de `localStorage` con tipado TypeScript. No depende de React. API pura de funciones.

```ts
// Agentes en el equipo
getPinnedAgents(): string[]           // filenames de agentes activos
addPinnedAgent(filename: string)      // agrega al equipo
removePinnedAgent(filename: string)   // quita del equipo
setPinnedAgents(filenames: string[])  // reemplaza el equipo completo

// Avatares: gallery ID (ej: "dev-1") o base64 data-URI
getAgentAvatar(filename: string): string | null
setAgentAvatar(filename: string, value: string)

// Apodos y roles
getAgentNickname(filename: string): string | null
setAgentNickname(filename: string, nickname: string)
getAgentRole(filename: string): string | null
setAgentRole(filename: string, role: string)

clearAllPreferences()  // reset completo (dev/debug)
```

**Claves localStorage:** `stacky:pinnedAgents`, `stacky:agentAvatars`, `stacky:agentNicknames`, `stacky:agentRoles`.

---

### `avatarGallery.ts` — `src/services/avatarGallery.ts`

Metadata de los 20 avatares pixel art de la galería y resolver de URLs.

```ts
interface GalleryAvatar {
  id: string;        // ej: "dev-1"
  label: string;     // ej: "Dev Hoodie"
  category: "dev" | "analyst" | "qa" | "pm" | "ops" | "design" | "special";
  file: string;      // path bajo /avatars/, ej: "/avatars/dev-1.svg"
}

GALLERY_AVATARS: GalleryAvatar[]  // 20 avatares definidos

/** Devuelve la URL src a partir de gallery ID o base64 data-URI */
resolveAvatarSrc(value: string | null): string | null
```

**Avatares disponibles (20):**
`dev-1` Dev Hoodie · `dev-2` Dev Glasses · `dev-3` Dev Cap · `mobile-1` Mobile Dev · `analyst-1` Analyst Funcional · `analyst-2` Analyst Técnico · `business-1` Business Analyst · `qa-1` QA Engineer · `pm-1` Project Manager · `tl-1` Tech Lead · `scrum-1` Scrum Master · `dba-1` DBA · `devops-1` DevOps · `data-1` Data Engineer · `sec-1` Security Eng · `architect-1` Arquitecto · `ux-1` UX Designer · `robot-1` AI Agent · `ninja-1` Ninja · `wizard-1` Wizard

---

## Componentes raíz

### `<App>`

Router de vistas con estado simple (`view: "team" | "workbench"`). No usa React Router.

**Estado interno:**
```ts
view: "team" | "workbench"  // default: "team"
```

**Lógica:** renderiza `<TeamScreen>` o `<Workbench>` según `view`. Pasa los callbacks de navegación a cada página.

---

### `<TeamScreen>` — `src/pages/TeamScreen.tsx`

Pantalla principal. Grid de empleados-agentes con header de acciones.

**Props:**
```ts
{ onGoToWorkbench: () => void }
```

**Estado interno:**
```ts
allAgents: VsCodeAgent[]      // cargado de GET /api/agents/vscode
pinned: string[]               // filenames — fuente: preferences.ts
manageOpen: boolean            // drawer TeamManageDrawer
editTarget: string | null      // filename abierto en EmployeeEditDrawer
loading: boolean
```

**Comportamiento:**
- Al montar: `GET /api/agents/vscode` para tener los metadatos de todos los agentes.
- `pinned` viene de `getPinnedAgents()` y se refresca via `refresh()` cada vez que un drawer cierra.
- `agentByFilename(filename)` cruza la lista de `allAgents` con el filename del equipo.
- Estado vacío si `pinned.length === 0`: ilustración + CTA "+ Agregar primer agente".

**Grid:** 3 cols ≥1280px · 2 cols 768–1280px · 1 col <768px.

---

### `<EmployeeCard>` — `src/components/EmployeeCard.tsx`

Tarjeta HR-style para un agente del equipo.

**Props:**
```ts
{
  filename: string;
  agent: VsCodeAgent | undefined;  // puede ser undefined si no se cargó aún
  onEdit: (filename: string) => void;
  onRemoved: () => void;
}
```

**Estado interno:** `menuOpen: boolean` · `launchOpen: boolean`

**Lógica de display:**
- `displayName` = `agentNickname ?? agent.name ?? filename sin extensión`
- `displayRole` = `agentRole ?? primera oración de agent.description`
- `type` = inferido del filename (contiene "technical", "dev", "qa", etc.)
- `color` = CSS var de tipo de agente (ej: `var(--agent-technical)`)

**Estructura visual:**
- Badge tipo de agente (top-left, color del tipo)
- Menú kebab ⋮ (top-right): "Editar" | "Quitar del equipo"
- `<PixelAvatar size="lg">` centrado con borde coloreado
- Nombre (fuente pixel art)
- Rol (muted, truncado)
- Botón "Asignar Ticket →" (abre `AgentLaunchModal`)

**CSS Custom Property:** `--agent-color` pasada inline para efecto de borde en hover.

---

### `<AgentLaunchModal>` — `src/components/AgentLaunchModal.tsx`

Modal principal del flujo Team Screen → VS Code Chat.

**Props:**
```ts
{
  agent: VsCodeAgent;
  avatarValue: string | null;    // gallery ID o base64
  onClose: () => void;
}
```

**Estado interno:**
```ts
query: string                  // búsqueda de ticket (debounce 200ms)
tickets: Ticket[]              // todos los tickets (cargado al montar)
filtered: Ticket[]             // tickets filtrados por query
selected: Ticket | null
message: string                // mensaje opcional
loading: boolean               // fetch al bridge
bridgeError: boolean           // true si POST /open-chat falla
success: boolean               // true 1.2s antes de cerrar
```

**Flujo:**
1. Monta → `GET /api/tickets` (una vez).
2. Query change → debounce 200ms → filtra por `ado_id`, `title`, `project`.
3. Click "OK" → `POST http://localhost:5052/open-chat` con `{ agent_name, message: "#ADO-{id} {título}\n{mensajeOpcional}" }`.
4. Éxito → `success=true` → `setTimeout(onClose, 1200)`.
5. Error → `bridgeError=true` → muestra banner rojo.

**Bridge error copy:** *"La extensión VS Code no está activa. Abrí VS Code con la extensión Stacky para continuar."*

---

### `<TeamManageDrawer>` — `src/components/TeamManageDrawer.tsx`

Drawer lateral derecho para agregar/quitar agentes del equipo.

**Props:**
```ts
{
  allAgents: VsCodeAgent[];   // todos los agentes de VS Code
  onClose: () => void;
}
```

**Estado interno:** `inlineEdit: InlineEdit | null`

```ts
interface InlineEdit {
  filename: string;
  avatar: string | null;
  nickname: string;
  role: string;
}
```

**Comportamiento:**
- `isInTeam(filename)` → consulta `getPinnedAgents()`.
- Click **"+ Agregar"**: abre inline editor con `AvatarPicker` + campos nombre/rol.
- Click **"Quitar"**: `removePinnedAgent()` inmediato.
- Click **"✓ Agregar al equipo"**: persiste avatar/nickname/role + `addPinnedAgent()` + cierra inline.
- Muestra badge "En equipo" en agentes ya agregados.

---

### `<EmployeeEditDrawer>` — `src/components/EmployeeEditDrawer.tsx`

Drawer lateral derecho para editar un agente del equipo.

**Props:**
```ts
{
  filename: string;
  agent: VsCodeAgent | undefined;
  onClose: () => void;
  onRemoved: () => void;
}
```

**Estado interno:** `nickname`, `role`, `avatar`, `confirmRemove: boolean`

**Comportamiento:**
- Pre-carga valores desde `preferences.ts`.
- "Guardar" → persiste los tres campos y llama `onClose()`.
- "Quitar del equipo" → doble confirmación en-fila (no modal) → `removePinnedAgent()` → `onRemoved()`.

---

### `<PixelAvatar>` — `src/components/PixelAvatar.tsx`

Componente de display de avatar único.

**Props:**
```ts
{
  value: string | null;    // gallery ID o base64 data-URI
  size?: "sm" | "md" | "lg";  // 32 / 64 / 96 px (default: "md")
  name?: string;           // para alt text y placeholder de iniciales
  className?: string;
}
```

**Comportamiento:**
- Llama a `resolveAvatarSrc(value)` para obtener el `src`.
- Si `src` es `null` → renderiza placeholder cuadrado con las primeras 2 iniciales del nombre (fuente pixel art).
- Si `src` presente → `<img>` con `image-rendering: pixelated`.

---

### `<AvatarPicker>` — `src/components/AvatarPicker.tsx`

Selector de avatar con galería + upload custom.

**Props:**
```ts
{
  value: string | null;                       // gallery ID o base64
  onChange: (avatarIdOrBase64: string) => void;
}
```

**Estado interno:** `filter: string` · `preview: string | null` · `uploading: boolean`

**Secciones:**
1. **Tabs de categoría:** Todos · Dev · Analista · QA · PM/TL · Ops/BD · Diseño · Especial.
2. **Grid de galería:** avatares filtrados. Click → `onChange(id)`.
3. **Slot "Custom"** (dashed border): click → `<input type="file">` oculto.
   - FileReader → `Image` → `canvas 64×64` con `imageSmoothingEnabled = false` → `canvas.toDataURL("image/png")` → `onChange(base64)`.
4. **Hint** de selección activa.

**Pixelado:** `imageSmoothingEnabled = false` en el canvas → efecto nearest-neighbor independiente del tamaño original.

---

### `<Workbench>` — `src/pages/Workbench.tsx`
Flujo avanzado — layout 3 columnas + topbar. Accesible desde el botón "Ir al Workbench" en TeamScreen.

**Props:**
```ts
{ onGoToTeam?: () => void }
```
**Estado:** ninguno propio.
**Dependencias:** `useWorkbenchStore`, `useTicketsQuery`.

---

### `<TopBar>`

**Props:**
```ts
{ onGoToTeam?: () => void }  // si presente → muestra botón "← Equipo"
```
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
