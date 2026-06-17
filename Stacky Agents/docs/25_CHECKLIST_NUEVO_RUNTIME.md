# 25 — Checklist: portar un runtime nuevo al arnés

**Fecha:** 2026-06-11
**Plan origen:** `22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` §V2.1
**Nota de numeración:** el plan 22 lo llamaba "doc 23", pero `23_` y `24_` ya
estaban ocupados al implementarlo; se materializa como doc 25.

El arnés es **plataforma**, no features cableadas a 2 CLIs. Agregar un runtime
(Gemini CLI, proveedor X) = implementar un contrato conocido + **pasar la
Runtime Conformance Suite** (`backend/tests/conformance/test_runtime_conformance.py`).
Terminás cuando esa suite pasa parametrizada con tu runtime.

## Pasos exactos

1. **Capabilities** — Agregá una entrada en `harness/capabilities.py::CAPABILITIES`
   con los 5 flags (`writes_artifacts`, `supports_stdin_feedback`,
   `supports_resume`, `supports_mcp`, `has_stream_telemetry`).

2. **Resume** (si `supports_resume=True`) — Agregá la clave de sesión canónica en
   `harness/resume.py::_SESSION_KEY` y el par de flags en `_RESUME_FLAG`. La
   clave NO se renombra nunca (es contrato de metadata).

3. **Flags + config** — Todo flag nuevo del runtime entra en `config.py` **y** en
   `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR. Default OFF/0.

4. **Runner usando los seams compartidos** — El runner nuevo debe:
   - llamar a `harness.post_run` (finalize) en el path de éxito;
   - persistir telemetría vía `harness.telemetry`;
   - cablear `harness.runaway_guard.RunawayGuard` (turnos siempre; costo si hay
     telemetría);
   - clasificar fallos con `harness.failure.classify` → `metadata["failure_kind"]`
     (V0.4);
   - sellar las claves canónicas de metadata: la session key del paso 2,
     `prompt_sha` (V1.1) y `run_fingerprint` (V2.4);
   - inyectar contexto vía los seams (`context_enrichment`, `stacky_skills`,
     `harness/run_contract`) — NO reimplementar inyección;
   - generar un artefacto reproducible (`write_repro_script` o equivalente) en el
     run_dir;
   - si NO soporta MCP, enrutar sus outputs file-based por
     `services/artifact_intake.validate_and_normalize` (V1.3) antes de encolar a
     `ado_write_outbox`.

5. **Presets** — Sumá los flags del runtime al preset `full` (y a `safe` los que
   sean guardrails) en `services/harness_profiles.py` (V0.1).

6. **Conformance verde** — Agregá el runner a `RUNNER_SOURCES` en la suite y
   corré:
   ```
   python -m pytest tests/conformance/test_runtime_conformance.py -q
   ```
   Verde = el runtime está cableado a todos los seams. La suite falla si falta
   cualquier cableado (hay un "test del test" que lo verifica).

7. **CI** — Sumá los archivos de test del runtime a `HARNESS_TEST_FILES` en
   `scripts/run_harness_tests.sh` (+ `.ps1`). El ratchet solo crece.

## Definición de "terminado"

`run_harness_tests.sh` verde con tu runtime incluido **y** la conformance suite
pasando parametrizada con él. Sin eso, el runtime hereda el path frágil y queda
fuera del contrato del arnés.
