# ASSUMPTIONS — Supuestos, Límites y No-Objetivos

> Lo que este sistema asume, lo que deliberadamente NO hace, y dónde están sus bordes.

## Supuestos

- **S1.** Existe Python 3.8+ disponible para los scripts de soporte (solo stdlib).
- **S2.** El operador trabaja en sesiones discretas; cada sesión tiene un objetivo acotado.
- **S3.** En el modo inicial (HITL) hay un humano que aprueba o rechaza cada propuesta.
- **S4.** El acoplamiento a un proyecto real se hace por **un** adapter a la vez, seleccionado
  por configuración. Sin adapter, el sistema corre en modo genérico (sin tocar ningún proyecto).
- **S5.** Los artefactos y decisiones se guardan como archivos de texto/JSON versionables.

## Límites conocidos

- **L1.** El núcleo **no ejecuta** cambios sobre ningún proyecto: solo produce propuestas,
  evaluaciones y decisiones. La aplicación de un cambio es responsabilidad de un adapter
  y siempre detrás de aprobación (HITL) o gate explícito (AOTL).
- **L2.** No hay orquestador de LLM incluido: `agents/` y `prompts/` definen roles y contratos,
  pero el "motor" que los ejecuta se conecta por adapter. Esto mantiene el núcleo portable.
- **L3.** El índice de sesiones (`sessions/_index.json`) es append-only y de baja concurrencia;
  no está pensado para escritura concurrente multi-proceso.
- **L4.** La validación de contratos se hace contra JSON Schema; el sistema no impone un
  validador específico (cualquiera compatible con draft 2020-12 sirve).

## No-objetivos (explícito)

- **N1.** No reemplaza al humano. En HITL el humano cierra el ciclo; en AOTL supervisa por excepción.
- **N2.** No es un framework de agentes propietario: es una base de **contratos + artefactos**.
- **N3.** No gestiona credenciales ni secretos. Si un adapter los necesita, los maneja el adapter,
  fuera de control de versiones.
- **N4.** No realiza acciones destructivas ni irreversibles por su cuenta.

## Dependencias del proyecto padre (declaradas y aisladas)

> Por defecto: **NINGUNA.** El núcleo genérico no toca el repositorio padre.
>
> Si en el futuro se acopla a un proyecto, **toda** dependencia debe declararse acá y vivir en
> `adapters/<proyecto>/`. Formato de la declaración:

| ID | Adapter | Depende de | Naturaleza | Cómo se aísla |
|----|---------|------------|-----------|----------------|
| —  | (ninguna por defecto) | — | — | — |

## Riesgos de acoplamiento a vigilar

- Que un adapter "filtre" detalles del proyecto al núcleo genérico (revisar en cada PR).
- Que aparezcan rutas absolutas o nombres del repo padre fuera de `adapters/`.
- Que los contratos cambien sin bump de versión (rompe consumidores). Ver `contracts/README.md`.
