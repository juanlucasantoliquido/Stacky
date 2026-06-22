---
name: run-session
description: Corre una vuelta completa del ciclo Kaizen (observar -> proponer -> evaluar -> decidir -> registrar) para una sesión, en modo HITL o AOTL según config. Procedimiento determinístico sobre los contratos del núcleo.
---

# Skill: run-session

Procedimiento para ejecutar **una** sesión de automejora de principio a fin. Determinístico,
portable, agnóstico de motor. Las rutas son relativas a la raíz `kaizen/`.

## Precondiciones
- Existe `config/kaizen.config.yaml` (si no, copiar desde el `.example`).
- Se conoce `mode` (hitl|aotl) y `adapter`.

## Pasos

### 1. OBSERVAR — crear la sesión
- Correr `python scripts/new_session.py "<objetivo-en-slug>"`.
- Esto instancia plantillas en `sessions/<id>/` y agrega la entrada a `sessions/_index.json`.
- Verificar que `session.json` cumple `contracts/session.input.schema.json`.

### 2. PROPONER
- **HITL:** completar `sessions/<id>/proposal.md`.
- **AOTL:** el motor (adapter) ejecuta `agents/improver` con `prompts/system/improver.system.md`.
- En ambos casos: el resultado debe cumplir `contracts/proposal.schema.json`.

### 3. EVALUAR
- **HITL:** completar `sessions/<id>/evaluation.md` con la rúbrica de `docs/04_HUMAN_REVIEW.md`.
- **AOTL:** el motor ejecuta `agents/evaluator`.
- Resultado: cumple `contracts/evaluation.schema.json` (scores C1..C5, bloqueantes, confianza).

### 4. DECIDIR
- **HITL:** completar `sessions/<id>/decision.md` (`accept`/`reject`/`iterate` + justificación).
- **AOTL:** aplicar el gate de `config/profiles/default.yaml`:
  - cualquier bloqueante ⇒ no auto-accept;
  - propuesta irreversible ⇒ rechazar o escalar;
  - `confidence < min_confidence` ⇒ escalar a humano;
  - si `iterate`, respetar `max_iterations`.
- Resultado: cumple `contracts/decision.schema.json`.

### 5. REGISTRAR
- Promover artefactos a `artifacts/` (con metadatos `contracts/artifact.schema.json`).
- Si la decisión sienta precedente, agregar un ADR-lite en `decisions/`.
- Actualizar `status` de la sesión en `sessions/_index.json` a `closed`.
- (Opcional) Emitir `session.output` conforme a `contracts/session.output.schema.json`.

## Postcondiciones
- La sesión queda `closed` (o engendra una hija si `iterate`).
- Todo producto es validable contra su contrato.
- El registro es append-only (no se reescribió historia).
