# QA UAT Agent — Tools Físicas

> Carpeta de herramientas CLI del agente QA UAT. Cada tool es un script Python autocontenido que corre suelto o como parte del pipeline orquestado por `qa_uat_pipeline.py`.

---

## Estructura de la carpeta

```
QA UAT Agent/
├── README.md                    ← este archivo
├── qa-uat-config.json           ← config de runtime (timeouts, flags Playwright, etc.)
├── qa_uat_pipeline.py           ← orquestador CLI: corre todas las tools en orden
│
├── ── MVP (Fase 3.A) ─────────────────────────────────────────
├── uat_ticket_reader.py         ← Lee ticket ADO y devuelve JSON normalizado
├── uat_scenario_compiler.py     ← Compila plan de pruebas en ScenarioSpecs ejecutables
├── ui_map_builder.py            ← Inspecciona pantalla en vivo y produce UI map con selectores
├── selector_discovery.py        ← Helper interno: elige el selector más robusto por elemento
├── playwright_test_generator.py ← Genera .spec.ts por escenario desde ScenarioSpec + UI map
├── uat_test_runner.py           ← Ejecuta .spec.ts y captura evidencia (trace, video, screenshots)
├── uat_dossier_builder.py       ← Ensambla dossier final: JSON + Markdown + HTML para ADO
├── ado_evidence_publisher.py    ← Publica dossier como comentario único e idempotente en ADO
│
├── ── Fase 3.B ────────────────────────────────────────────────
├── uat_precondition_checker.py  ← Verifica precondiciones (RIDIOMA, Web.config, BD, build)
├── uat_evidence_capturer.py     ← Hooks Playwright: screenshots/DOM por paso
├── uat_assertion_evaluator.py   ← Evalúa assertions (literales + semánticas via LLM)
├── uat_failure_analyzer.py      ← Clasifica FAILs en taxonomía con hipótesis
├── uat_cleanup_tool.py          ← Limpia datos creados por el escenario
├── uat_session_manager.py       ← Gestiona sesión browser (login PABLO, cookies, pool)
│
├── ── Fase 3.C / Post-MVP ─────────────────────────────────────
├── uat_report_summarizer.py
├── uat_flakiness_detector.py
├── uat_golden_path_validator.py
├── uat_test_data_finder.py
├── uat_action_recorder.py
│
├── schemas/                     ← JSON schemas para validación de contratos
│   ├── uat_ticket.schema.json
│   ├── scenario_spec.schema.json
│   ├── ui_map.schema.json
│   ├── runner_output.schema.json
│   └── dossier.schema.json
│
├── templates/                   ← Plantillas Jinja2 para generación de archivos
│   ├── playwright_test.spec.ts.j2
│   ├── dossier.md.j2
│   └── ado_comment.html.j2
│
├── prompt_cards/                ← Documentación de cada uso de LLM
│   ├── ticket_context_classifier.md
│   ├── scenario_compiler.md
│   ├── ui_map_alias_namer.md
│   ├── assertion_semantic_oracle.md
│   ├── failure_explainer.md
│   └── executive_summary.md
│
├── cache/
│   └── ui_maps/                 ← Cache de inspección DOM por hash (borrable sin riesgo)
│
├── evidence/
│   └── <ticket_id>/             ← Screenshots, video, trace, dossier, ado_comment.html
│
├── audit/
│   └── <YYYY-MM-DD>.jsonl       ← Audit log de publicaciones a ADO (append-only)
│
├── tests/unit/                  ← Tests unitarios por tool
│   ├── test_uat_ticket_reader.py
│   ├── test_uat_scenario_compiler.py
│   ├── test_uat_precondition_checker.py
│   ├── test_ui_map_builder.py
│   ├── test_selector_discovery.py
│   ├── test_playwright_test_generator.py
│   ├── test_uat_test_runner.py
│   ├── test_uat_assertion_evaluator.py
│   ├── test_uat_failure_analyzer.py
│   ├── test_uat_cleanup_tool.py
│   ├── test_uat_dossier_builder.py
│   └── test_ado_evidence_publisher.py
│
└── requirements.txt
```

---

## Instalación

```bash
cd "Tools/Stacky/Stacky tools/QA UAT Agent"
pip install -r requirements.txt
playwright install chromium
```

---

## Credenciales

**Nunca en el repo.** Crear localmente:

```
Tools/Stacky/.secrets/qa_db.env
Tools/Stacky/.secrets/agenda_web.env
```

Ver `Tools/Stacky/.secrets/*.env.example` para el formato.

Cargar antes de correr cualquier tool:

```powershell
# PowerShell (Windows)
Get-Content "..\..\..\.secrets\qa_db.env" | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}
Get-Content "..\..\..\.secrets\agenda_web.env" | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}
```

```bash
# bash/zsh (Linux/Mac)
export $(grep -v '^#' ../../.secrets/qa_db.env | xargs)
export $(grep -v '^#' ../../.secrets/agenda_web.env | xargs)
```

---

## Pipeline completo (MVP)

```bash
# 1. Leer ticket
python uat_ticket_reader.py --ticket 70

# 2. Compilar escenarios
python uat_scenario_compiler.py < evidence/70/ticket.json > evidence/70/scenarios.json

# 3. Construir UI map (si no existe o invalidado)
python ui_map_builder.py --screen FrmAgenda.aspx

# 4. Generar tests
python playwright_test_generator.py \
  --scenarios evidence/70/scenarios.json \
  --ui-maps cache/ui_maps/ \
  --out evidence/70/tests/

# 5. Ejecutar
python uat_test_runner.py \
  --tests-dir evidence/70/tests/ \
  --evidence-out evidence/70/

# 6. Ensamblar dossier
python uat_dossier_builder.py --ticket 70 --evidence evidence/70/

# 7a. Preview sin tocar ADO
python ado_evidence_publisher.py --ticket 70 --mode dry-run

# 7b. Publicar cuando el operador confirma
python ado_evidence_publisher.py --ticket 70 --mode publish

# O todo de una vez:
python qa_uat_pipeline.py --ticket 70 --mode dry-run
```

---

## Convenciones de cada tool

- **Salida JSON a stdout.** Errores en formato `{"ok": false, "error": "<code>", "message": "..."}` con exit code 1.
- **Falla rápido** si las env vars requeridas no están seteadas.
- **Sin side effects inesperados**: ninguna tool escribe fuera de `evidence/`, `cache/` o `audit/` salvo `ado_evidence_publisher.py` (que escribe en ADO solo con `--mode publish`).
- **NUNCA se llama `python ado.py state ...`** desde ninguna tool. Hay un test estático (`tests/unit/test_ado_evidence_publisher.py`) que verifica esto en tiempo de CI.

---

## Tests

```bash
# Correr todos los tests unitarios
pytest tests/unit/ -v

# Test estático de seguridad (verifica que ningún módulo invoque `ado.py state`)
pytest tests/unit/test_ado_evidence_publisher.py::test_no_state_subcommand_in_codebase -v
```

---

## Audit log

Cada invocación de `ado_evidence_publisher.py` — incluso `--mode dry-run` y los fallos — escribe una línea en `audit/<YYYY-MM-DD>.jsonl`:

```json
{"ts": "2026-05-02T14:32:00Z", "ticket_id": 70, "run_id": "uuid", "mode": "publish", "action": "created", "user": "juan@empresa.com", "comment_hash": "sha256:...", "ado_response_status": 200}
```

Este log es append-only. No se versiona (gitignored). Retener localmente para auditoría.
