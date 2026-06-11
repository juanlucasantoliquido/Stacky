---
name: code-review-checklist
description: Checklist de code review para agentes de desarrollo (dev, dev-automation)
agents: [dev, dev-automation, devstack]
projects: []
keywords: [code review, revisión, pr, pull request, checklist, calidad]
---

## Code review checklist — agentes dev

Al revisar o generar código, verificar estos puntos antes de entregar:

### Correctitud
- [ ] La lógica implementa exactamente lo descrito en el ticket (ni más, ni menos)
- [ ] Los casos borde están cubiertos (null, vacío, fuera de rango)
- [ ] No hay hard-codes de valores que deberían ser configurables

### Mantenibilidad
- [ ] Funciones con responsabilidad única (<30 líneas salvo excepciones justificadas)
- [ ] Nombres de variables y funciones auto-descriptivos en español o inglés (no mezclar)
- [ ] Sin código comentado — si está muerto, eliminarlo; si es context, es un comentario real

### Seguridad básica
- [ ] Inputs externos validados antes de usarlos en queries/paths/comandos
- [ ] Secrets nunca hardcodeados ni loggeados

### Tests
- [ ] Al menos un test del happy path
- [ ] Al menos un test del camino de error principal
- [ ] Los tests no mockean más de lo necesario

### Integración Stacky
- [ ] Los archivos de output siguen la convención (comment.html / pending-task.json)
- [ ] JSON de entrega es válido y usa ADO id real, no ordinal
