# Dossier UAT — ADO-0: [INC] Etiqueta de contacto ausente en grilla y notas de gestiones

> **Run ID**: `511ea76c-e442-40a6-8218-8a85fd71a2c1`  
> **Fecha**: 2026-07-25T23:44:45Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 2 escenarios UAT para '[INC] Etiqueta de contacto ausente en grilla y notas de gestiones'. Resultado: BLOCKED. Escenarios con problemas: P05. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P05` | Cuando BGCODMEDIO o HBGCODMEDIO es NULL, la etiqueta muestra "—" o cadena vacía sin errores ni excepciones. | ⚠️ BLOCKED | 0 ms |

| `P06` | El fix no altera las reglas de acceso existentes; ningún rol que no vea ya el contacto puede verlo tras el cambio. | ✅ PASS | 0 ms |


---


## Fallas detectadas


### ❌ P05 — P05

**Mensaje**: evaluator_inconclusive






---






---

## Evidencia por escenario


### P05 — Cuando BGCODMEDIO o HBGCODMEDIO es NULL, la etiqueta muestra "—" o cadena vacía sin errores ni excepciones.

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:









---


### P06 — El fix no altera las reglas de acceso existentes; ningún rol que no vea ya el contacto puede verlo tras el cambio.

**Estado**: ✅ PASS


**Artefactos**:









---



## Recomendaciones para el QA humano



- [P05] Revisar manualmente — status: blocked



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `511ea76c-e442-40a6-8218-8a85fd71a2c1`_