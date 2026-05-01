# Stacky Agents — Frontend

React 18 + Vite + TypeScript + Zustand + TanStack Query.

## Quickstart

```bash
cd "Tools/Stacky Agents/frontend"
npm install
npm run dev          # http://localhost:5173
```

Asume backend en `http://localhost:5050`. Para apuntar a otro:

```bash
VITE_API_BASE=http://localhost:6000 npm run dev
```

## Build

```bash
npm run build        # bundle estático en dist/
npm run preview      # sirve dist/ localmente
```

## Estructura

Ver [docs/02_ARCHITECTURE.md](../docs/02_ARCHITECTURE.md#frontend--estructura-de-carpetas)
y [docs/05_COMPONENTS.md](../docs/05_COMPONENTS.md).

## Convenciones

- Un componente por archivo. PascalCase. Co-location de `Component.tsx` + `Component.module.css`.
- Estado servidor → TanStack Query. Estado UI → Zustand.
- Sin CSS-in-JS pesado: CSS Modules + tokens en `theme.ts`.
- Comentarios mínimos: nombres autodescriptivos.
