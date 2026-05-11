# Dossier UAT — ADO-0: RF-007 - Modificaciones en la Lista de Obligaciones

> **Run ID**: `7b058b9a-169a-4ad2-973c-d68180b42b21`  
> **Fecha**: 2026-05-10T02:09:23Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

El ticket RF-007 permanece bloqueado tras ejecutar 8 escenarios de prueba, todos con incidencias. Los escenarios P02, P05, P06, P07, P08, P10, P11 y P12 presentaron fallos que impiden la validación de las modificaciones en la Lista de Obligaciones. Se requiere revisión y corrección por parte del equipo de desarrollo antes de continuar con la validación UAT.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | La columna "Fecha de ingreso judicial" no es recuperable por configuracion | ⚠️ BLOCKED | 0 ms |

| `P05` | Comportamiento con campos sin valor (nulos) en los 8 nuevos campos | ⚠️ BLOCKED | 0 ms |

| `P06` | Valores "Si"/"No" del campo "Afiliado al Debito Automatico" | ⚠️ BLOCKED | 0 ms |

| `P07` | Los 8 nuevos campos son de solo lectura para todos los perfiles | ⚠️ BLOCKED | 0 ms |

| `P08` | Formato monetario de "Saldo a favor disponible" y "Monto de la Cuota" | ⚠️ BLOCKED | 0 ms |

| `P10` | Actualizacion de datos tras batch nocturno | ⚠️ BLOCKED | 0 ms |

| `P11` | La sub-vista de detalle de cuotas no se ve afectada (regresion) | ⚠️ BLOCKED | 0 ms |

| `P12` | Exportacion incluye nuevos campos y excluye columna eliminada (si aplica) | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR






---


### ❌ P05 — P05

**Mensaje**: RUNTIME_ERROR






---


### ❌ P06 — P06

**Mensaje**: RUNTIME_ERROR






---


### ❌ P07 — P07

**Mensaje**: RUNTIME_ERROR






---


### ❌ P08 — P08

**Mensaje**: RUNTIME_ERROR






---


### ❌ P10 — P10

**Mensaje**: RUNTIME_ERROR






---


### ❌ P11 — P11

**Mensaje**: RUNTIME_ERROR






---


### ❌ P12 — P12

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P02 — La columna "Fecha de ingreso judicial" no es recuperable por configuracion

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P05 — Comportamiento con campos sin valor (nulos) en los 8 nuevos campos

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P06 — Valores "Si"/"No" del campo "Afiliado al Debito Automatico"

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P07 — Los 8 nuevos campos son de solo lectura para todos los perfiles

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P08 — Formato monetario de "Saldo a favor disponible" y "Monto de la Cuota"

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P10 — Actualizacion de datos tras batch nocturno

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P11 — La sub-vista de detalle de cuotas no se ve afectada (regresion)

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P12 — Exportacion incluye nuevos campos y excluye columna eliminada (si aplica)

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa exacta de los errores de ejecución.

- Verifique que todas las dependencias y configuraciones necesarias estén correctamente instaladas y actualizadas.

- Ejecute los casos de prueba individualmente para aislar el problema y facilitar la depuración.

- Consulte la documentación del sistema para asegurarse de que el entorno de ejecución cumple con los requisitos.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `7b058b9a-169a-4ad2-973c-d68180b42b21`_