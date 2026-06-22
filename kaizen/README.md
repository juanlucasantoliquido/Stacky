# Kaizen — Laboratorio de Automejora por Sesiones

> Base de trabajo **aislada y portable** para desarrollar una herramienta de automejora
> que opera en **sesiones separadas**, primero **Human-in-the-Loop (HITL)** y más adelante
> **Agent-on-the-Loop (AOTL)**.

Esta carpeta es una **raíz única autocontenida**. No depende del repositorio padre salvo por
los enlaces declarados explícitamente en [`adapters/`](adapters/). Puede copiarse a otro repo o
convertirse en una herramienta independiente moviendo *solo* este directorio.

---

## Qué es esto (en una frase)

Un ciclo repetible y auditable: **observar → proponer una mejora → evaluarla (humano o agente) →
decidir → registrar artefactos y decisión**, donde cada vuelta del ciclo es una **sesión**
aislada y reproducible.

## Qué NO es

- No es parte del runtime del proyecto principal.
- No ejecuta cambios destructivos por sí mismo.
- No asume ninguna tecnología ni proyecto concreto: el acoplamiento a un proyecto vive
  **solo** en un *adapter* (ver [`adapters/`](adapters/)).

---

## Mapa rápido

| Carpeta | Para qué | ¿Genérico o reemplazable? |
|---|---|---|
| [`docs/`](docs/) | Base conceptual, arquitectura, uso, sesiones, evaluación, migración | Genérico |
| [`config/`](config/) | Capa de configuración para adaptar el sistema a cualquier proyecto | Genérico (valores por proyecto) |
| [`contracts/`](contracts/) | Contratos de E/S entre componentes (JSON Schema) | Genérico |
| [`prompts/`](prompts/) | Prompts de sistema y plantillas de prompt | Genérico (afinables) |
| [`agents/`](agents/) | Definición de los roles agénticos (proponedor / evaluador) | Genérico |
| [`skills/`](skills/) | Procedimientos invocables (p.ej. correr una sesión) | Genérico |
| [`templates/`](templates/) | Plantillas de sesión, propuesta, evaluación, decisión | Genérico |
| [`adapters/`](adapters/) | **Único punto de acoplamiento** a un proyecto concreto | **Reemplazable por proyecto** |
| [`sessions/`](sessions/) | Salidas de cada sesión (una carpeta por sesión) | Datos |
| [`artifacts/`](artifacts/) | Artefactos producidos por las sesiones | Datos |
| [`decisions/`](decisions/) | Registro de decisiones (ADR-lite) | Datos |
| [`scripts/`](scripts/) | Utilidades portables (stdlib pura) | Genérico |

> El **manifiesto completo** de qué hace cada archivo está en [`MANIFEST.md`](MANIFEST.md).

---

## Quickstart (un solo punto de entrada, sin dependencias externas)

```sh
python kaizen.py help                       # lista todos los subcomandos
python kaizen.py new "mi objetivo acotado"  # crea una sesión
python kaizen.py run  <session_id>          # gate determinista + traza forense
python kaizen.py metrics                    # reporte forense de eficiencia
```

> **¿Sos un agente y querés ejecutar una sesión completa de punta a punta?**
> Seguí el instructivo paso a paso: [`docs/06_RUNBOOK_AGENTE.md`](docs/06_RUNBOOK_AGENTE.md).

Todo usa solo la librería estándar de Python 3 (sin red, sin instalar nada del proyecto padre).

---

## Modos del ciclo

- **Human-in-the-Loop (HITL)** — *modo inicial.* El humano propone o aprueba cada paso.
  La máquina nunca cierra el ciclo sola.
- **Agent-on-the-Loop (AOTL)** — *modo futuro.* Un agente propone y evalúa; el humano
  supervisa por excepción. Se activa por configuración (`config/kaizen.config.yaml: mode`),
  reusando los **mismos contratos**. Ver [`docs/03_SESSIONS.md`](docs/03_SESSIONS.md).

---

## Principios (prioridad máxima)

1. **Aislamiento** — nada acá importa del padre salvo vía adapter declarado.
2. **Portabilidad** — rutas relativas, stdlib, formatos abiertos (Markdown + JSON/YAML).
3. **Claridad** — todo archivo tiene un propósito declarado en el manifiesto.
4. **Facilidad de traslado** — mover esta carpeta = mover la herramienta. Ver
   [`PORTABILITY.md`](PORTABILITY.md) y [`docs/05_MIGRATION.md`](docs/05_MIGRATION.md).

Supuestos y límites: [`ASSUMPTIONS.md`](ASSUMPTIONS.md).
