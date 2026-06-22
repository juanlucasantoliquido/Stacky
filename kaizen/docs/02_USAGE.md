# 02 — Uso Mínimo (HITL)

> Cómo correr una sesión de automejora con un humano al mando, sin instalar nada del proyecto padre.

## Requisitos

- Python 3.8+ (solo para `scripts/`, librería estándar; opcional si trabajás 100% a mano).
- Un editor de texto.

## Paso a paso

### 1) (Primera vez) elegí configuración

```sh
cp config/kaizen.config.example.yaml config/kaizen.config.yaml
# Editá: mode: hitl   y   adapter: generic
```

### 2) Creá una sesión

```sh
python scripts/new_session.py "mejorar-mensajes-de-error"
```

Esto crea `sessions/<timestamp>__mejorar-mensajes-de-error/` con:

- `session.md`     — bitácora de la sesión (desde `templates/session.template.md`)
- `proposal.md`    — para completar la propuesta
- `evaluation.md`  — para la evaluación
- `decision.md`    — para la decisión
- `session.json`   — metadatos conforme a `contracts/session.input.schema.json`

y agrega una entrada a `sessions/_index.json`.

### 3) Proponé (PROPONER)

Completá `proposal.md`: qué mejora, por qué, alcance, riesgos, cómo se revierte, cómo se mide.
Debe cumplir `contracts/proposal.schema.json`.

### 4) Evaluá como humano (EVALUAR)

Completá `evaluation.md` usando la rúbrica de [`04_HUMAN_REVIEW.md`](04_HUMAN_REVIEW.md):
hallazgos, score por criterio, veredicto preliminar. Cumple `contracts/evaluation.schema.json`.

### 5) Decidí (DECIDIR)

Completá `decision.md`: `accept` / `reject` / `iterate`, con justificación y, si aplica,
próximos pasos. Cumple `contracts/decision.schema.json`.

### 6) Registrá (REGISTRAR)

- Copiá cualquier artefacto producido a `artifacts/` (o dejalo en la carpeta de la sesión).
- Si la decisión sienta precedente, agregá un ADR-lite en `decisions/`.
- Cerrá `session.md` con el resultado.

## Verificación rápida (smoke test)

```sh
python scripts/new_session.py "smoke-test"
# Debe imprimir la ruta de la sesión creada y salir con código 0.
```

## Verificación completa (CI / pre-commit)

```sh
python kaizen.py check
# CHECK: TODO VERDE  [5/5 grupos OK | 120 tests unitarios]
```

Corre en orden: `doctor` (salud estructural) → `selfcheck` (consistencia del índice) →
`validate` (contratos de sesiones cerradas) → `test_core` (76 tests de lógica pura:
slugify, scores, metrics, dashboard, archive, adapters, config, doctor, _console, autoloop.gather_focus)
→ `test_aotl` (44 tests de maquinaria AOTL: guardarraíl, gate, apply/rollback+applied_paths,
spawn_child, forensic, engine.normalize).
Exit 0 solo si todo pasa. Usalo como gate antes de commitear o como CI.

## Pasar a AOTL (más adelante)

Cambiá `mode: aotl` en `config/kaizen.config.yaml` y configurá la política de gates en
`config/profiles/default.yaml`. Los pasos 3–5 los ejecuta un agente; el humano supervisa por
excepción. Mismos archivos, mismos contratos. Ver [`03_SESSIONS.md`](03_SESSIONS.md).
