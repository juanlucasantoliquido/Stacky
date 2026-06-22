# sessions/

Una carpeta por sesión: `<timestamp-UTC>__<slug-del-objetivo>/`. Cada sesión es una vuelta
completa del ciclo, aislada y reproducible (ver `docs/03_SESSIONS.md`).

## Contenido típico de una sesión
```
<id>/
├── session.json     # metadatos (contracts/session.input.schema.json)
├── session.md       # bitácora humana
├── proposal.md      # PROPONER
├── evaluation.md    # EVALUAR
├── decision.md      # DECIDIR
└── artifacts/       # (opcional) artefactos locales de la sesión
```

## Índice
`_index.json` es **append-only**: lista `{id, objective, mode, adapter, created_utc, status}`.
Permite auditar y comparar sesiones sin abrir cada carpeta.

> Las carpetas de sesiones reales están gitignored por defecto (datos locales). Se versionan
> este README y `_index.json`. Promové a `artifacts/` / `decisions/` lo que quieras conservar.
