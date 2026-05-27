# Plan robusto: Exportación/Importación de Configuración + Sincronización ADO por Usuario

**Fecha:** 2026-05-27  
**Proyecto:** Stacky Agents  
**Objetivo:** Evitar reconfiguración tras upgrades/deploys y mejorar foco operativo en la pestaña de tickets ADO.

---

## 1) Contexto y alcance

Este plan cubre dos capacidades clave:

1. **Portabilidad de configuración por proyecto**: exportar/importar la configuración para migraciones entre versiones y nuevos despliegues sin repetir setup manual.
2. **Filtrado de tickets ADO por usuario sincronizado**: conectar el usuario de Stacky con ADO, mostrar por defecto solo tareas asignadas al usuario y habilitar un checkbox (marcado por defecto) para ver todas las tareas.

> Nota funcional requerida por negocio: en la pestaña de tickets ADO debe existir un control visible para “mostrar todas las tareas” y debe iniciar activado.

---

## 2) Principios de diseño

- **Backward compatible**: ninguna migración debe romper configuraciones existentes.
- **Idempotencia**: importar el mismo archivo varias veces no debe duplicar entidades.
- **Trazabilidad**: cada export/import debe dejar auditoría (quién, cuándo, qué versión, resultado).
- **Seguridad por defecto**: secretos fuera de texto plano o con cifrado/mascarado.
- **UX simple**: “Exportar” e “Importar” en flujo guiado, validaciones claras y rollback.
- **Feature flags**: liberar gradualmente para minimizar riesgo en producción.
- **Persistencia local de UX**: todo filtro, checkbox o preferencia de usuario debe guardarse en **localStorage** para evitar reconfiguración repetitiva entre sesiones.

---

## 3) Requerimiento A: Exportar/Importar configuración de proyectos

## 3.1 Alcance funcional

### Exportar
- Exportar configuración de un proyecto a archivo versionado (JSON/YAML firmado).
- Permitir exportación completa y selectiva por módulos (ej. prompts, reglas, mapeos ADO, pipelines).
- Incluir metadatos: versión de schema, versión app, fecha, hash integridad.

### Importar
- Cargar archivo, validar schema y compatibilidad de versión.
- Modo **dry-run**: previsualizar cambios antes de aplicar.
- Modo **merge** o **overwrite** por sección.
- Reporte final de resultado por campo/entidad.

### Post-deploy / cambio de versión
- Flujo asistido “Restaurar desde exportación previa”.
- Sugerencia automática de importación cuando detecte entorno sin configuración.

## 3.2 Diseño técnico propuesto

### Formato de archivo
- `stacky-project-config-v{n}.json`
- Secciones:
  - `meta` (schemaVersion, appVersion, projectId, exportedAt, checksum)
  - `settings`
  - `integrations` (ADO, otros)
  - `workflows`
  - `agentProfiles`
  - `uiPreferences`
  - `secretsRef` (referencias, no secretos en claro)

### Compatibilidad de versiones
- Registro de migradores `schemaVersion -> schemaVersion+1`.
- Validaciones obligatorias antes de persistir.
- Estrategia de fallback: rechazar import incompatible y sugerir acción.

### Persistencia y seguridad
- Secretos fuera del archivo o cifrados con clave de entorno.
- Firma/hash para detectar corrupción o manipulación.
- Auditoría en tabla/log: `config_transfer_events`.

### API/servicios (propuesta)
- `POST /api/projects/{id}/config/export`
- `POST /api/projects/{id}/config/import?mode=dry-run|merge|overwrite`
- `GET /api/projects/{id}/config/import/{jobId}/result`

### UI
- Botón “Exportar configuración”.
- Botón “Importar configuración”.
- Wizard de 3 pasos: subir archivo → validar/preview → confirmar.

## 3.3 Criterios de aceptación (DoD)

- Exporta configuración de proyecto en < 10s para tamaño estándar.
- Importa con `dry-run` y muestra diff legible.
- Importación idempotente comprobada.
- Cambios auditados y consultables.
- Cero regresión en proyectos existentes.

---

## 4) Requerimiento B: Sincronización ADO por usuario + checkbox “mostrar todas”

## 4.1 Comportamiento esperado

En la pestaña **Tickets ADO**:

- Stacky identifica el usuario autenticado y su vínculo con identidad ADO.
- Vista principal filtra tareas asignadas al usuario (modo “Mis tareas”).
- Existe un checkbox **“Mostrar todas las tareas”** y aparece **marcado por defecto**.
- Al desmarcar, se aplicará filtro de “solo asignadas a mí”.
- Estado del checkbox se recuerda por usuario (preferencia UI), configurable si se desea.

> Dado que el negocio pidió checkbox marcado por defecto, se respeta ese default aunque la experiencia “mis tareas primero” se puede habilitar vía configuración global de tenant si fuera necesario.

## 4.2 Diseño técnico propuesto

### Identidad y mapeo usuario
- Guardar `stackyUserId -> adoUserDescriptor/email`.
- Proceso de vinculación inicial:
  1. OAuth/Token ADO válido.
  2. Resolución de identidad ADO.
  3. Persistencia de mapeo con timestamp de verificación.

### Consulta de tickets
- Query base ADO con filtros por proyecto/sprint.
- Filtro opcional `AssignedTo == currentAdoUser` cuando checkbox esté desmarcado.
- Checkbox marcado = sin filtro de asignación (todas).

### UX / estado
- Checkbox visible al nivel de filtros primarios.
- Tooltip con explicación de impacto.
- Persistencia preferencia en `uiPreferences.adoTickets.showAll`.
- Persistir en `localStorage` cualquier filtro/checkbox/preferencia de la vista (incluyendo `showAll`) para restaurar estado automáticamente al volver a la pestaña.

### Rendimiento
- Caché corta (ej. 30-60s) para lista de tickets.
- Debounce en filtros para evitar llamadas excesivas.
- Paginación/virtualización para listas grandes.

### Observabilidad
- Métricas:
  - `% usuarios con vinculación ADO exitosa`
  - `latencia consulta tickets ADO`
  - `uso de checkbox showAll`
- Logs con correlación de usuario/sesión.

## 4.3 Criterios de aceptación (DoD)

- Usuario vinculado ve tickets sin errores de permisos.
- Checkbox “Mostrar todas las tareas” se renderiza marcado por defecto.
- Al desmarcar, solo se muestran tareas asignadas al usuario autenticado.
- Estado se mantiene al refrescar (si persistencia activa).
- Manejo claro de errores de token/expiración.
- Todos los filtros/checkboxes/preferencias de la pestaña se restauran desde `localStorage` sin intervención manual.

---

## 5) Plan de implementación por fases

## Fase 0 — Discovery (1-2 días)
- Levantar modelo actual de configuración y dependencias.
- Identificar qué campos son exportables y cuáles requieren tratamiento especial (secretos).
- Revisar integración actual ADO y forma de identificar usuario.

**Entregable:** documento técnico de gap analysis + riesgos.

## Fase 1 — Backend base export/import (3-5 días)
- Definir schema v1 de exportación.
- Implementar endpoint de export.
- Implementar validación de import + dry-run.
- Implementar auditoría de eventos.

**Entregable:** API funcional con pruebas unitarias.

## Fase 2 — Migraciones/versionado + seguridad (2-4 días)
- Implementar migradores de schema.
- Añadir hash/firma y estrategia de secretos.
- Probar compatibilidad entre versiones recientes.

**Entregable:** import robusto cross-version.

## Fase 3 — UI de export/import (2-4 días)
- Wizard de importación con preview/diff.
- Mensajería de errores y confirmación.
- Telemetría de uso.

**Entregable:** flujo end-to-end usable por usuario no técnico.

## Fase 4 — ADO user sync + filtro tickets (3-5 días)
- Vinculación usuario Stacky ↔ ADO.
- Nuevo filtro asignado a usuario.
- Checkbox “Mostrar todas las tareas” marcado por defecto.
- Persistencia de preferencia.

**Entregable:** pestaña ADO tickets con comportamiento requerido.

## Fase 5 — QA/UAT y rollout (2-3 días)
- Pruebas funcionales, regresión y performance.
- Feature flags por tenant.
- Rollout progresivo + monitoreo.

**Entregable:** salida controlada a producción.

---

## 6) Matriz de riesgos y mitigación

1. **Incompatibilidad de config entre versiones**  
   - Mitigación: schema versionado + migradores + dry-run obligatorio.

2. **Exposición accidental de secretos**  
   - Mitigación: no exportar secretos en claro; usar referencias/cifrado y checklist de seguridad.

3. **Mapeo incorrecto de usuario ADO**  
   - Mitigación: flujo de verificación de identidad + reconexión simple + logs.

4. **Degradación de performance en tickets**  
   - Mitigación: caching, paginación, límites de query, telemetría de latencia.

5. **Confusión de UX por default del checkbox**  
   - Mitigación: tooltip explicativo + preferencia guardada + documentación rápida.

---

## 7) Pruebas recomendadas

### Unitarias
- Serializer/deserializer de config.
- Validador de schema y migradores.
- Lógica de filtros ADO (showAll true/false).

### Integración
- Export → Import dry-run → Import apply.
- Vinculación usuario Stacky/ADO con credenciales válidas e inválidas.
- Consulta tickets con y sin filtro de asignación.
- Persistencia y restauración de filtros/checkboxes/preferencias desde `localStorage`.

### E2E
- Usuario exporta en versión N, importa en N+1 tras deploy.
- En pestaña ADO, checkbox inicia marcado; desmarcar filtra por asignado.
- Usuario aplica varios filtros, sale y vuelve a la app, y los filtros se rehidratan desde `localStorage`.

### Seguridad
- Verificar que archivo exportado no contenga secretos en texto claro.
- Verificar controles de acceso en endpoints de import/export.

---

## 8) KPIs de éxito

- **Tiempo de recuperación post-deploy** de configuración: reducción >70%.
- **Tasa de éxito de importación** >95% en primera ejecución.
- **Reducción de incidencias de setup manual** por release.
- **Precisión de filtrado de tickets asignados** >99%.
- **Latencia p95 de carga de tickets ADO** bajo umbral definido por producto.

---

## 9) Checklist de salida a producción

- [ ] Feature flag habilitable por tenant.
- [ ] Documentación de usuario final (export/import y filtro ADO).
- [ ] Dashboard de métricas y alertas.
- [ ] Runbook de soporte (errores comunes de import/ADO auth).
- [ ] Plan de rollback validado.

---

## 10) Siguiente paso inmediato

1. Aprobar este plan.  
2. Priorizar Fase 1 + Fase 4 en sprint siguiente (valor más alto).  
3. Preparar historias técnicas separadas para backend, frontend, QA y DevOps con criterios DoD ya definidos.
