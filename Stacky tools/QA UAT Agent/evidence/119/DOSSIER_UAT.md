# Dossier UAT — ADO-119: ADO-119 RF-006 — Mostrar campos Corredor Principal y Riesgo de Cliente en Datos de Identificacion del Deudor

> **Run ID**: `c0872b92-040f-4fc1-9039-7fa6632c7eb2`  
> **Fecha**: 2026-05-08T04:27:33Z  
> **Agente**: 1.2.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Resumen Ejecutivo UAT:  
El ticket ADO-119 RF-006 se encuentra BLOQUEADO. De los 11 escenarios de prueba ejecutados, ninguno fue aprobado y se identificaron 11 incidencias en los escenarios P01, P02, P03, P04, P05, P06, P07, P08, P10, P11 y P12. Se requiere resolución de los problemas detectados para continuar con la validación y asegurar el cumplimiento de los requisitos solicitados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | Campo Corredor Principal visible con corredor correcto (lote con una obligacion con OGCORREDOR post-batch) | ⚠️ BLOCKED | 0 ms |

| `P02` | Corredor Principal = OGCORREDOR de la obligacion con mayor deuda (multiples obligaciones) | ⚠️ BLOCKED | 0 ms |

| `P03` | Desempate por fecha de inicio de mora mas antigua cuando hay empate de importe | ⚠️ BLOCKED | 0 ms |

| `P04` | Lote con una sola obligacion con OGCORREDOR asignado | ⚠️ BLOCKED | 0 ms |

| `P05` | Lote sin OGCORREDOR asignado: campo Corredor Principal vacio, sin error | ⚠️ BLOCKED | 0 ms |

| `P06` | Campo Riesgo de Cliente visible con clasificacion correcta (atributo de lote) | ⚠️ BLOCKED | 0 ms |

| `P07` | Riesgo de Cliente en cabecera consistente con Vista Obligaciones | ⚠️ BLOCKED | 0 ms |

| `P08` | Lote sin clasificacion de riesgo: campo Riesgo de Cliente vacio, sin error | ⚠️ BLOCKED | 0 ms |

| `P10` | Los campos NO aparecen en instancias distintas de Pacifico (InstanciaPacifico != 1) | ⚠️ BLOCKED | 0 ms |

| `P11` | Los campos se actualizan tras el batch nocturno de posicion | ⚠️ BLOCKED | 0 ms |

| `P12` | Corredor Principal en cabecera consistente con OGCORREDOR de Vista Obligaciones | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: missing_selectors






---


### ❌ P02 — P02

**Mensaje**: missing_selectors






---


### ❌ P03 — P03

**Mensaje**: missing_selectors






---


### ❌ P04 — P04

**Mensaje**: missing_selectors






---


### ❌ P05 — P05

**Mensaje**: missing_selectors






---


### ❌ P06 — P06

**Mensaje**: missing_selectors






---


### ❌ P07 — P07

**Mensaje**: missing_selectors






---


### ❌ P08 — P08

**Mensaje**: missing_selectors






---


### ❌ P10 — P10

**Mensaje**: missing_selectors






---


### ❌ P11 — P11

**Mensaje**: missing_selectors






---


### ❌ P12 — P12

**Mensaje**: missing_selectors






---




---

## Evidencia por escenario


### P01 — Campo Corredor Principal visible con corredor correcto (lote con una obligacion con OGCORREDOR post-batch)

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P02 — Corredor Principal = OGCORREDOR de la obligacion con mayor deuda (multiples obligaciones)

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P03 — Desempate por fecha de inicio de mora mas antigua cuando hay empate de importe

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P04 — Lote con una sola obligacion con OGCORREDOR asignado

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P05 — Lote sin OGCORREDOR asignado: campo Corredor Principal vacio, sin error

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P06 — Campo Riesgo de Cliente visible con clasificacion correcta (atributo de lote)

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P07 — Riesgo de Cliente en cabecera consistente con Vista Obligaciones

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P08 — Lote sin clasificacion de riesgo: campo Riesgo de Cliente vacio, sin error

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P10 — Los campos NO aparecen en instancias distintas de Pacifico (InstanciaPacifico != 1)

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P11 — Los campos se actualizan tras el batch nocturno de posicion

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P12 — Corredor Principal en cabecera consistente con OGCORREDOR de Vista Obligaciones

**Estado**: ⚠️ BLOCKED (missing_selectors)





---



## Recomendaciones para el QA humano



- Revise las dependencias y configuraciones previas necesarias para ejecutar las pruebas.

- Verifique que todos los recursos requeridos (archivos, servicios, bases de datos) estén disponibles y accesibles.

- Consulte los registros de errores o mensajes del sistema para identificar posibles bloqueos o permisos faltantes.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.2.0 — Run `c0872b92-040f-4fc1-9039-7fa6632c7eb2`_