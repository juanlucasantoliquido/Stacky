# decisions/

Registro acumulado de decisiones que sientan precedente (ADR-lite). Una decisión de sesión vive
en la sesión (`decision.md`); acá se promueven solo las que el sistema debe **recordar** entre
sesiones.

## Formato sugerido (ADR-lite)
```
NNNN-titulo-corto.md
---
- Fecha (UTC):
- Sesión origen:
- Contexto:
- Decisión:
- Consecuencias / rollback:
```

Es **append-only**: las decisiones no se editan; se superan con una nueva que referencia a la
anterior. El contenido está gitignored por defecto salvo este README; versioná lo que deba perdurar.
