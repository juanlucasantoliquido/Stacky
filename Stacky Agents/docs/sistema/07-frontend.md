# 07 — Frontend

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [02-arquitectura](02-arquitectura.md)

## Stack (`frontend/package.json`) [V: package.json:1-31]
- React 18.3 + ReactDOM, TypeScript 5.6, Vite 5.4 (`@vitejs/plugin-react`).
- Estado: `zustand` 5; data fetching: `@tanstack/react-query` 5.59.
- UI/markdown: `lucide-react`, `react-markdown` + `remark-gfm` + `rehype-highlight` + `highlight.js`, `mermaid` 11.
- Scripts: `dev`=vite, `build`=`tsc --noEmit && vite build`, `preview`, `lint` (eslint). [V: package.json:5-11]

## Entrada y ruteo (`frontend/src/App.tsx`)
- Tabs (estado local, no react-router): `team | tickets | review | unblocker | pm | logs | settings | docs | memory | diagnostics | history | migrador | devops | dbcompare`. [V: App.tsx:33]
- Mapa `TAB_PATHS` a rutas (`/`, `/tickets`, `/review`, `/unblocker`, `/pm`, `/logs`, `/settings`, `/docs`, `/memory`, `/diagnostics`, `/history`, `/migrador`, `/devops`, `/dbcompare`); el ruteo se hace con `history.pushState` + `popstate`, sin librería de routing. [V: App.tsx:35-56]
- Páginas: TeamScreen, TicketBoard, ReviewInboxPage, UnblockerPage, PMCommandCenter, SystemLogsPage, SettingsPage, DocsPage, MemoryPage, DiagnosticsPage, ExecutionHistoryPage, MigratorPage, DevOpsPage, DbComparePage. [V: App.tsx:2-15,205-215]
- Tabs opcionales (`pm`, `logs`, `docs`, `memory`) se muestran según `useUiSectionsStore` (config server-side de secciones UI). Si el tab activo se oculta → fallback a `team`. [V: App.tsx:54,114-119,153-190]
- Tabs gated por flag de backend (health probe en boot): `migrador` (`/api/migrator/health`), `devops` (`/api/devops/health`), `dbcompare` (`/api/db-compare/health`); aparecen solo si `flag_enabled===true`. → ver [12-devops](12-devops.md), [14-db-compare](14-db-compare.md). [V: App.tsx:64-107]
- Atajos de teclado: Ctrl/Cmd+K (command palette), `?` (cheatsheet), Ctrl/Cmd+/ (toggle team/tickets). [V: App.tsx:85-110]

## Componentes globales (siempre montados)
DemoModeBanner, TopBar (incluye versión — Plan 38 A), HealthBanner, CommandPalette, ShortcutsCheatsheet,
DailyStandupModal, OnboardingTour, **CodexConsoleDock** (consola en vivo de runtimes CLI Codex/Claude, permite
responderle al agente), **ActiveRunsPanel** (cancelar runs activos/huérfanos, aparece solo si hay runs). [V: App.tsx:121-237]
`useGlobalExecutionNotifier()` notifica fin de ejecuciones globalmente. [V: App.tsx:25,56]

## Consumo de API
- Capa de cliente: `frontend/src/api/` (`client.ts` con `api`/`apiBase`/`rawPost`/`RawResponse`/`GatewayErrorBody`,
  y `endpoints.ts` con las funciones tipadas). [V: endpoints.ts:1-2]
- Tipos en `frontend/src/types`. Contratos tipados explícitos (ej. `FinishWorkResponse`, `TicketSyncResult`). [V: endpoints.ts:3-60]
- `EpicFromBriefModal.tsx` consume el flujo brief→épica (incluye selector de modelo/effort). [V: gitStatus modified EpicFromBriefModal.tsx; relación con agents.py:564-669]

## Build y servido
- `vite build` genera `frontend/dist`; el deploy limpia `dist` antes de compilar para garantizar rebuild fresco. [V: gitStatus commit 9ec2e83f]
- El backend Flask sirve `dist/index.html` y assets con Content-Type forzado por extensión (ver [02-arquitectura](02-arquitectura.md)). [V: app.py:469-503]

## Notas operativas
- vitest no está instalado en el entorno de dev; el frontend se valida con `tsc`. [INF: MEMORY stacky-backend-dev-test-env]
- `frontend/src/components` tiene ~75 componentes; no se documentan uno a uno. [V: CLAUDE.md]
