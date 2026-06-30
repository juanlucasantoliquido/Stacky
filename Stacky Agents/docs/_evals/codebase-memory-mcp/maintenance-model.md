# F3 — Modelo de mantenimiento del índice (D6)

> Plan 76 — Fase F3. Generado: 2026-06-30.

---

## E6 — ¿Cómo se actualiza el índice?

### Actualización automática (watcher)

`codebase-memory-mcp` incluye un **watcher de filesystem** que:
1. Detecta cambios en archivos del sub-árbol indexado
2. Re-indexa automáticamente los archivos modificados en background
3. No requiere intervención del operador

Según el README: "Background auto-sync keeps it fresh after that" (tras la indexación inicial). "Background watcher detects file changes and re-indexes automatically."

### Actualización manual

```bash
codebase-memory-mcp update
```

Útil cuando el watcher está apagado o para forzar re-indexación completa.

---

## ¿Crece linealmente con el repo?

El knowledge graph es un grafo de símbolos y relaciones. El tamaño esperado es O(n) respecto al número de símbolos del repo:
- Crecimiento lineal con el tamaño del codebase ✓
- Sin explosión combinatoria (las relaciones se expresan como aristas del grafo, no productos cruzados)

**D6 = APROBADO** — watch automático + update manual, crecimiento lineal esperado.

---

## Consideraciones para el operador (Windows)

1. El watcher del filesystem usa las APIs de notificación del SO (Windows: `ReadDirectoryChangesW`).
2. Para repos grandes (>100k archivos), el watcher puede consumir handles de fichero; verificar con el operador si RS/Pacífico tiene ese volumen.
3. El índice se almacena localmente (SQLite/grafo local según el README — sin servidor externo).

---

## Resumen D6

| Aspecto | Estado |
|---------|--------|
| Watch automático | Sí — background watcher |
| Re-index manual | Sí — `codebase-memory-mcp update` |
| Crecimiento | Lineal O(n símbolos) |
| Almacenamiento | Local (sin servidor externo) |
| Windows | Sí (binary nativo) |

**D6 = APROBADO**
