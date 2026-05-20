# 12 — Stacky Agent Lab + Evaluation Harness

> Estado: Propuesta ejecutable  
> Fecha: 2026-05-20  
> Objetivo: convertir la mejora de agentes, prompts, runtimes y contextos en un proceso medible, repetible, reversible y promocionable.

---

## 1. Resumen ejecutivo

Stacky Agents ya tiene una base fuerte: ejecuciones auditadas, contract validator, confidence scoring, PII masking, egress policies, output cache, routing de modelos, webhooks, logs, manifest watcher, PM evals y comparador de agentes.

La oportunidad exponencial no es agregar mas botones. Es crear un **Agent Lab**: un laboratorio interno que permita probar variantes de agentes y runtimes contra tickets historicos, comparar resultados contra una baseline y promover solo lo que mejora con evidencia.

La pregunta que responde Agent Lab:

> "Este cambio de prompt, runtime, contexto o modelo mejora Stacky o solo parece mejor?"

La respuesta debe salir de un harness:
- fixture reproducible
- corrida aislada
- output capturado
- judges deterministas y/o IA bajo contrato
- score comparativo
- reporte de regresiones
- decision de promocion

---

## 2. Problema actual

Hoy Stacky acumula ejecuciones reales, pero todavia falta una capa formal para experimentar.

### 2.1 Sintomas

- Cambiar un `.agent.md` no tiene un benchmark automatico antes de usarlo en tickets reales.
- El selector de runtime existe en frontend, pero `agent_runner.py` todavia cae a fallback para `codex_cli` y `claude_code_cli` en el path `/api/agents/run`.
- Las metricas existen, pero estan orientadas a observabilidad operativa, no a promocion de cambios.
- PM Intelligence ya tiene evals, pero ese patron no esta generalizado a todos los agentes.
- Los fixtures de QA UAT son ricos, pero estan separados del ciclo normal de agentes.
- No hay un concepto de "baseline version" por agente.
- No hay comparacion automatica de outputs: estructura, calidad, costo, latencia, cambios semanticos y regresiones.

### 2.2 Riesgo si no se corrige

Sin Agent Lab, Stacky puede crecer en cantidad de features pero volverse dificil de gobernar. Cada mejora de agente queda basada en intuicion, demos puntuales o resultados aislados. Eso escala mal cuando hay muchos agentes, proyectos, clientes y runtimes.

---

## 3. Vision

Agent Lab debe ser el lugar donde Stacky aprende sin arriesgar produccion.

### 3.1 Principios

1. **Reproducibilidad antes que opinion.** Cada resultado debe poder repetirse con el mismo fixture.
2. **Contratos antes que texto libre.** Un output que no respeta estructura no puede promocionarse.
3. **Comparacion contra baseline.** El candidato no se evalua en abstracto; compite contra la version actual.
4. **Human-in-the-loop.** El harness recomienda promocionar, pero el operador aprueba.
5. **Sin efectos externos por defecto.** Nada en Agent Lab publica en ADO, cambia estados ni escribe fuera del sandbox.
6. **Cost awareness.** Una mejora que cuesta 5x debe justificarlo con calidad medible.
7. **Runtimes intercambiables.** El mismo fixture debe poder correrse con mock, GitHub Copilot, Codex CLI o futuros adapters.
8. **Evals acumulativos.** Cada bug real descubierto se convierte en fixture permanente.

---

## 4. Objetivos y no objetivos

### 4.1 Objetivos

- Crear un harness para correr agentes contra fixtures historicos.
- Comparar variantes de prompt, modelo, runtime y contexto.
- Generar reportes de calidad, costo, latencia y regresion.
- Definir promotion gates por agente.
- Exponer resultados via CLI y endpoints internos.
- Integrar el patron de evals PM existente como referencia.
- Permitir shadow/canary de agentes en tickets reales sin publicar.
- Alimentar el Agent Memory Graph con resultados aprobados y fallidos.

### 4.2 No objetivos en v1

- No entrenar modelos.
- No publicar automaticamente a ADO.
- No reemplazar el flujo humano del Workbench.
- No crear un DAG visual complejo.
- No hacer multi-tenant completo.
- No resolver todos los runtimes en el primer PR.

---

## 5. Arquitectura propuesta

```
backend/services/agent_lab/
  __init__.py
  contracts.py
  fixtures.py
  runner.py
  runtime_adapters.py
  judges.py
  diffing.py
  reports.py
  promotion_gate.py
  registry.py
  replay.py

backend/evals/agents/
  technical/
    fixtures/
      ticket_120_grid_empty.json
      ticket_119_pass.json
    baselines/
      technical.default.v1.json
    suites/
      smoke.json
      regression.json
  developer/
  qa/

backend/api/agent_lab.py

frontend/src/pages/AgentLabPage.tsx
frontend/src/components/AgentLab*
```

### 5.1 Componentes

| Componente | Responsabilidad |
|---|---|
| `fixtures.py` | Cargar, validar y normalizar fixtures. |
| `runtime_adapters.py` | Abstraer mock, legacy runner, Codex CLI, future Claude Code CLI. |
| `runner.py` | Orquestar una corrida de eval, persistir resultado y logs. |
| `judges.py` | Evaluar output con reglas deterministas y jueces IA bajo contrato. |
| `diffing.py` | Comparar output candidato vs baseline. |
| `reports.py` | Generar JSON/Markdown/HTML de resultados. |
| `promotion_gate.py` | Determinar si una variante puede ser promovida. |
| `registry.py` | Registrar versiones de agentes, prompts, suites y baselines. |
| `replay.py` | Reconstruir una ejecucion historica como fixture. |

---

## 6. Modelo conceptual

### 6.1 Fixture

Un fixture es un ticket congelado con contexto, expectativas y criterios de evaluacion.

Debe contener:
- identidad del caso
- agente objetivo
- ticket sintetico o historico anonimizado
- context blocks
- restricciones de egress
- output esperado parcial
- reglas de evaluacion
- tags de riesgo

### 6.2 Suite

Una suite es un conjunto de fixtures con un proposito.

Ejemplos:
- `smoke`: 5 fixtures rapidos para validar que el agente no esta roto.
- `regression`: bugs historicos que nunca deben volver.
- `release`: suite obligatoria antes de promocionar.
- `cost`: fixtures grandes para medir tokens/costo.
- `adversarial`: prompt injection, contexto contradictorio, datos incompletos.
- `domain`: casos fuertes por modulo del negocio.

### 6.3 Candidate

Un candidate es lo que se quiere evaluar.

Puede ser:
- version nueva de un `.agent.md`
- override de system prompt
- runtime distinto
- modelo distinto
- estrategia de contexto distinta
- chain/pack nuevo
- judge nuevo

### 6.4 Baseline

La baseline es la version aprobada actual. Cada candidato compite contra ella.

La baseline debe guardar:
- agente
- filename o version
- prompt sha256
- runtime
- modelo
- fecha de promocion
- metricas de promocion
- suite usada

---

## 7. Contrato de fixture

```json
{
  "schema_version": "agent_lab_fixture.v1",
  "fixture_id": "technical_ticket_120_grid_empty",
  "title": "Technical analiza grilla vacia sin proponer fix inventado",
  "agent_type": "technical",
  "project": "RSPACIFICO",
  "tags": ["regression", "technical", "grid", "data"],
  "source": {
    "kind": "historical_execution",
    "ticket_id": 120,
    "execution_id": 431,
    "anonymized": true
  },
  "ticket": {
    "ado_id": 120,
    "work_item_type": "Task",
    "ado_state": "Active",
    "priority": 2,
    "title": "Validar comportamiento de grilla vacia",
    "description": "Texto anonimizado del ticket..."
  },
  "context_blocks": [
    {
      "kind": "text",
      "id": "ticket-description",
      "title": "Descripcion ADO",
      "content": "..."
    }
  ],
  "run_options": {
    "model_override": null,
    "runtime": "mock",
    "use_few_shot": true,
    "use_anti_patterns": true,
    "fingerprint_complexity": "M"
  },
  "expectations": {
    "must_include": [
      "BLOQUEANTE",
      "evidencia",
      "datos"
    ],
    "must_not_include": [
      "implementar directamente",
      "asumo que"
    ],
    "required_sections": [
      "alcance",
      "plan tecnico",
      "pruebas"
    ],
    "min_contract_score": 85,
    "min_confidence": 70,
    "max_cost_usd": 0.25,
    "max_latency_ms": 90000
  },
  "judges": [
    {
      "type": "contract",
      "weight": 0.30
    },
    {
      "type": "deterministic_regex",
      "weight": 0.20
    },
    {
      "type": "llm_rubric",
      "weight": 0.30,
      "rubric_id": "technical_completeness_v1"
    },
    {
      "type": "cost_latency",
      "weight": 0.20
    }
  ]
}
```

### 7.1 Reglas de fixture

- `fixture_id` debe ser estable.
- Todo fixture historico debe estar anonimizado si contiene datos sensibles.
- `context_blocks` debe ser suficiente para reproducir la corrida.
- `expectations` debe evitar pedir output exacto completo; preferir criterios parciales.
- Los judges IA solo se habilitan si su propia suite de evals pasa.
- Los fixtures nunca deben requerir ADO real para correr.

---

## 8. Resultado de corrida

```json
{
  "schema_version": "agent_lab_result.v1",
  "run_id": "lab-20260520-001",
  "fixture_id": "technical_ticket_120_grid_empty",
  "agent_type": "technical",
  "candidate": {
    "kind": "prompt_variant",
    "name": "technical.v3",
    "prompt_sha256": "abc123",
    "runtime": "codex_cli",
    "model": "gpt-5.4"
  },
  "baseline": {
    "name": "technical.v2",
    "prompt_sha256": "def456"
  },
  "status": "passed",
  "scores": {
    "overall": 88.4,
    "contract": 92,
    "confidence": 81,
    "rubric": 86,
    "cost": 95,
    "latency": 73
  },
  "metrics": {
    "duration_ms": 42300,
    "tokens_in": 8200,
    "tokens_out": 1900,
    "cost_usd": 0.18,
    "output_chars": 9400
  },
  "failures": [],
  "warnings": [
    {
      "code": "LOW_SAMPLE_DOMAIN",
      "message": "Solo 2 fixtures del dominio grid en esta suite"
    }
  ],
  "artifacts": {
    "output_path": "backend/data/agent_lab/runs/lab-20260520-001/output.md",
    "report_path": "backend/data/agent_lab/runs/lab-20260520-001/report.json"
  }
}
```

---

## 9. Runtime adapters

Agent Lab necesita una interfaz comun para ejecutar variantes.

### 9.1 Interfaz

```python
class RuntimeAdapter(Protocol):
    name: str

    def run(
        self,
        *,
        agent_type: str,
        system_prompt: str,
        context_blocks: list[dict],
        options: dict,
        run_dir: Path,
    ) -> "RuntimeResult":
        ...
```

### 9.2 RuntimeResult

```python
@dataclass
class RuntimeResult:
    status: str
    output: str
    output_format: str
    metadata: dict
    logs: list[dict]
    duration_ms: int
    usage: dict
    error_message: str | None = None
```

### 9.3 Adapters iniciales

| Adapter | Uso | Riesgo |
|---|---|---|
| `MockRuntimeAdapter` | Tests rapidos y CI sin red. | Bajo |
| `LegacyAgentRunnerAdapter` | Reusa agentes internos actuales. | Medio |
| `CodexCliRuntimeAdapter` | Ejecuta agentes via Codex CLI. | Medio |
| `ShadowRuntimeAdapter` | Compara sin mutar DB/ADO. | Bajo |
| `ClaudeCodeRuntimeAdapter` | Futuro. | Alto hasta implementarse |

### 9.4 Primer fix asociado

El frontend ya permite elegir `codex_cli`, pero `/api/agents/run` todavia no despacha realmente a `services.codex_cli_runner.start_codex_cli_run`.

Accion propuesta:
- Si runtime es `github_copilot`, mantener path actual.
- Si runtime es `codex_cli`, resolver `vscode_agent_filename` y llamar `codex_cli_runner.start_codex_cli_run`.
- Si runtime es `claude_code_cli`, devolver `501 not_implemented` o esconder la opcion hasta que exista adapter.

Esto evita una UX engañosa y prepara Agent Lab.

---

## 10. Judges

Los judges convierten un output en señales medibles.

### 10.1 Deterministic judges

Son obligatorios y corren siempre.

| Judge | Que valida |
|---|---|
| ContractJudge | Usa `contract_validator.validate(agent_type, output)`. |
| ConfidenceJudge | Usa `services.confidence.score(output)`. |
| RegexJudge | `must_include`, `must_not_include`, secciones requeridas. |
| CitationJudge | Referencias a archivos, ADO IDs, tablas o lineas. |
| SQLSafetyJudge | Si hay SQL, debe ser read-only cuando aplique. |
| PiiLeakJudge | Verifica que no haya PII sin mascara en output/logs. |
| EgressJudge | Verifica clases de datos permitidas por modelo/runtime. |
| CostLatencyJudge | Compara tokens, costo y duracion contra limites. |

### 10.2 LLM judges

Se usan para evaluar calidad semantica, pero nunca solos.

Reglas:
- El judge IA debe devolver JSON estricto.
- Debe tener fixtures propios.
- Debe estar en `advisory_only` al inicio.
- Si falla el parseo JSON, el judge falla cerrado.
- No puede inventar evidencia: debe citar fragmentos del output evaluado.

Contrato:

```json
{
  "rubric_id": "technical_completeness_v1",
  "score": 0.86,
  "passed": true,
  "findings": [
    {
      "severity": "minor",
      "category": "missing_evidence",
      "message": "La seccion de BD menciona una tabla pero no muestra query de validacion.",
      "evidence": "Tablas afectadas: T_COBROS"
    }
  ],
  "confidence": 0.78
}
```

### 10.3 Rubricas por agente

#### Technical

- Identifica alcance con archivos/clases/metodos.
- Distingue evidencia de inferencia.
- No propone implementar si faltan datos criticos.
- Incluye plan de pruebas tecnico.
- Incluye riesgos de regresion.
- Respeta formato de 5 secciones.

#### Developer

- Implementa solo el alcance solicitado.
- Reporta archivos tocados.
- Incluye comandos/tests ejecutados.
- No inventa resultados de tests.
- No toca credenciales ni archivos fuera de scope.
- Si no pudo implementar, lo declara como bloqueo.

#### QA

- Veredicto claro PASS/FAIL/BLOCKED.
- Evidencia por escenario.
- No marca PASS si faltan datos.
- Distingue bug de ambiente vs bug funcional.
- Incluye riesgos residuales.

#### Functional

- Extrae RFs.
- Detecta gaps.
- Cita documentacion funcional.
- Genera criterios de aceptacion.
- Evita transformar incertidumbre en requerimiento falso.

---

## 11. Diffing

Agent Lab debe comparar candidato vs baseline.

### 11.1 Tipos de diff

| Tipo | Descripcion |
|---|---|
| Structural diff | Secciones presentes, orden, tablas, contratos. |
| Semantic diff | Cambios de conclusion o recomendacion. |
| Risk diff | Nuevos riesgos o riesgos omitidos. |
| Evidence diff | Citas agregadas/quitadas. |
| Cost diff | Tokens, costo y latencia. |
| Safety diff | Nuevas PII, egress warnings o forbidden claims. |

### 11.2 Resultado esperado

```json
{
  "candidate_vs_baseline": {
    "quality_delta": 6.2,
    "cost_delta_pct": -18.4,
    "latency_delta_pct": 12.1,
    "regressions": [
      {
        "fixture_id": "qa_ticket_116_env_fail",
        "severity": "major",
        "message": "El candidato cambio BLOCKED por FAIL sin evidencia adicional."
      }
    ],
    "improvements": [
      {
        "fixture_id": "technical_ticket_120_grid_empty",
        "message": "El candidato declara bloqueo por datos insuficientes, la baseline asumia fix."
      }
    ]
  }
}
```

---

## 12. Promotion gates

Un candidato solo puede promocionarse si pasa gates.

### 12.1 Gate default

- 100% fixtures smoke pasan.
- >= 95% fixtures regression pasan.
- Ningun failure P0/P1.
- Contract score promedio >= 85.
- Confidence promedio >= 70.
- Costo promedio no sube mas de 20% salvo override.
- Latencia p95 no sube mas de 30% salvo override.
- PII/Egress: 0 fallas.
- LLM judge parse success >= 98%.
- Reporte aprobado por operador.

### 12.2 Gate por tipo de cambio

| Cambio | Gate extra |
|---|---|
| Prompt de Developer | Debe pasar fixtures de safety y scope. |
| Prompt de QA | Debe pasar fixtures con PASS/FAIL/BLOCKED balanceados. |
| Runtime nuevo | Debe pasar cancel/resume/heartbeat/manifest tests. |
| Modelo nuevo | Debe pasar egress, cost y deterministic contract. |
| Context strategy | Debe mostrar mejora de calidad o baja de costo. |

### 12.3 Promotion record

```json
{
  "promotion_id": "prom-20260520-technical-v3",
  "agent_type": "technical",
  "candidate": "technical.v3",
  "baseline_replaced": "technical.v2",
  "approved_by": "juanluca.santoliquido@ubimia.com",
  "approved_at": "2026-05-20T15:40:00Z",
  "suite": "release",
  "summary": {
    "fixtures_total": 42,
    "passed": 41,
    "failed": 1,
    "waived": 1,
    "quality_delta": 5.8,
    "cost_delta_pct": -12.0
  },
  "waivers": [
    {
      "fixture_id": "legacy_ticket_old_format",
      "reason": "Formato historico no aplica a tickets nuevos",
      "approved_by": "lead"
    }
  ]
}
```

---

## 13. Persistencia

### 13.1 Archivos primero

Para v1, evitar migraciones grandes. Persistir resultados en disco:

```
backend/data/agent_lab/
  runs/
    lab-20260520-001/
      fixture.json
      output.md
      logs.jsonl
      report.json
      diff.json
  baselines/
    technical.default.json
  promotions/
    prom-20260520-technical-v3.json
```

### 13.2 Tablas opcionales v2

Cuando el volumen crezca:

- `agent_lab_runs`
- `agent_lab_results`
- `agent_lab_promotions`
- `agent_prompt_versions`
- `agent_lab_waivers`

---

## 14. CLI

### 14.1 Comandos v1

```powershell
cd "N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky Agents\backend"

python -m services.agent_lab.runner list-suites
python -m services.agent_lab.runner list-fixtures --agent technical
python -m services.agent_lab.runner run --agent technical --suite smoke --runtime mock
python -m services.agent_lab.runner run --agent technical --fixture technical_ticket_120_grid_empty --runtime codex_cli
python -m services.agent_lab.runner compare --agent technical --candidate technical.v3 --baseline technical.v2 --suite regression
python -m services.agent_lab.runner report --run-id lab-20260520-001 --format markdown
python -m services.agent_lab.runner promote --agent technical --candidate technical.v3 --suite release
```

### 14.2 Salida resumida

```text
Agent Lab Run
agent: technical
candidate: technical.v3
suite: regression
runtime: mock

fixtures: 42
passed:   40
failed:   2
overall:  87.1
cost:     -12.4% vs baseline
latency:  +4.0% vs baseline

Gate: BLOCKED
- P1 regression in technical_ticket_120_grid_empty
- P2 missing citation in technical_ticket_087_ridioma
```

---

## 15. Endpoints internos

### 15.1 Listar suites

`GET /api/agent-lab/suites`

```json
{
  "ok": true,
  "suites": [
    {
      "id": "technical.regression",
      "agent_type": "technical",
      "fixture_count": 42
    }
  ]
}
```

### 15.2 Ejecutar suite

`POST /api/agent-lab/runs`

```json
{
  "agent_type": "technical",
  "suite": "regression",
  "candidate": {
    "kind": "prompt_override",
    "name": "technical.v3",
    "system_prompt": "..."
  },
  "runtime": "mock",
  "dry_run": false
}
```

Respuesta:

```json
{
  "ok": true,
  "run_id": "lab-20260520-001",
  "status": "running",
  "stream_url": "/api/agent-lab/runs/lab-20260520-001/stream"
}
```

### 15.3 Obtener resultado

`GET /api/agent-lab/runs/<run_id>`

### 15.4 Comparar

`POST /api/agent-lab/compare`

### 15.5 Promocionar

`POST /api/agent-lab/promotions`

Requiere:
- `approved_by`
- `operator_reason`
- `candidate`
- `suite`
- `report_id`

---

## 16. UI propuesta

Nueva pestaña: **Agent Lab**.

### 16.1 Pantalla principal

Paneles:
- Suites disponibles por agente.
- Ultimas corridas.
- Baseline actual por agente.
- Candidatos pendientes.
- Regresiones abiertas.

### 16.2 Vista de corrida

Columnas:
- izquierda: fixtures y estado
- centro: output candidato
- derecha: judges, diff, baseline, costo

Acciones:
- correr fixture individual
- re-run failed only
- abrir output
- abrir diff
- crear waiver
- promover candidato

### 16.3 Vista de promocion

Debe mostrar:
- que cambia
- baseline reemplazada
- fixtures pasados/fallidos
- costo delta
- latencia delta
- riesgos
- waivers
- boton aprobar promocion

---

## 17. Replay desde ejecuciones reales

Una feature clave: convertir un caso real en fixture.

### 17.1 Flujo

1. Operador abre una `AgentExecution`.
2. Click "Convertir en fixture".
3. Stacky toma:
   - ticket
   - input_context
   - output
   - contract_result
   - confidence
   - metadata
4. Aplica anonimizado.
5. Sugiere expectations iniciales.
6. Operador edita y guarda.

### 17.2 Endpoint

`POST /api/agent-lab/fixtures/from-execution/<execution_id>`

Body:

```json
{
  "fixture_id": "technical_ticket_120_grid_empty",
  "suite": "technical.regression",
  "anonymize": true,
  "operator_reason": "Regresion detectada: no debe asumir datos cuando la grilla esta vacia"
}
```

---

## 18. Agent Lab y Memory Graph

Agent Lab debe producir datos utiles para memoria.

### 18.1 Eventos que alimentan memoria

- fixture creado desde ejecucion aprobada
- fixture creado desde bug real
- candidato falla una regresion
- judge detecta missing evidence
- waiver aprobado
- promocion exitosa

### 18.2 Entidades extraidas

- agente
- tipo de ticket
- modulo funcional
- archivo
- tabla
- RIDIOMA
- estado ADO
- causa de bloqueo
- decision de arquitectura
- patron de fallo

Esto permite construir un grafo:

```
Cobranza -> suele_requerir -> RIDIOMA_SMS
Cobranza -> suele_tocar -> BatchCobranza.cs
QA_FAIL_ENV -> requiere -> datos_de_prueba_validos
Technical_low_confidence -> correlaciona_con -> missing_git_context
```

---

## 19. Integracion con features existentes

### 19.1 Contract Validator

Se reutiliza directamente como judge base.

### 19.2 Confidence

Se reutiliza como señal, no como verdad absoluta.

### 19.3 PM evals

El patron de `services/pm/pm_evals.py` es referencia para:
- fixtures JSON
- gate antes de habilitar IA
- resultados por componente
- advisory mode

### 19.4 Agent comparison

`/api/metrics/agent-comparison` debe complementarse con resultados de Agent Lab:
- metrica real historica
- metrica reproducible de laboratorio

### 19.5 Manifest watcher

Los runtimes de laboratorio deben escribir artifacts de corrida con una estructura similar:
- `output.md`
- `logs.jsonl`
- `report.json`
- `MANIFEST.json`

### 19.6 FlowConfig

Antes de cambiar una regla `estado ADO -> agente`, Agent Lab puede validar que el agente sugerido pasa la suite del estado.

---

## 20. Seguridad

### 20.1 Prohibiciones

En Agent Lab:
- no publicar en ADO
- no cambiar estado ADO
- no escribir en repos productivos fuera de sandbox
- no usar credenciales heredadas por subprocess
- no persistir PII sin mascara

### 20.2 Sandbox

Cada corrida debe tener `run_dir` propio:

```
backend/data/agent_lab/runs/<run_id>/
```

Para runtimes que editan archivos:
- usar workspace temporal o worktree aislado
- capturar diff
- destruir o conservar segun flag

### 20.3 Egress

Antes de llamar a un modelo:
- clasificar datos
- chequear policy
- si bloquea, fixture falla con `EGRESS_BLOCKED`
- si advierte, registrar warning

---

## 21. Roadmap de implementacion

### Fase 0 — Preflight runtime

Duracion: 2-3 dias.

Entregables:
- Corregir `/api/agents/run` para que `codex_cli` use `codex_cli_runner`.
- Deshabilitar o marcar `claude_code_cli` como no implementado en UI/API.
- Tests de runtime selection.

Done:
- Elegir `codex_cli` ya no cae silenciosamente a GitHub Copilot.
- El usuario recibe error claro si un runtime no existe.

### Fase 1 — Agent Lab MVP filesystem

Duracion: 1 semana.

Entregables:
- `backend/services/agent_lab/fixtures.py`
- `runner.py`
- `judges.py` con judges deterministas
- `reports.py`
- 10 fixtures iniciales: 2 por agente principal
- CLI `run` y `report`

Done:
- `python -m services.agent_lab.runner run --agent technical --suite smoke --runtime mock`
- genera `report.json`
- falla cerrado ante contrato roto

### Fase 2 — Baseline compare

Duracion: 1 semana.

Entregables:
- `diffing.py`
- `promotion_gate.py`
- baselines por agente
- comando `compare`
- reporte Markdown

Done:
- compara candidato vs baseline
- muestra regresiones y mejoras
- bloquea promocion si falla gate

### Fase 3 — Replay desde ejecuciones reales

Duracion: 1 semana.

Entregables:
- endpoint `from-execution`
- anonimizado basico
- generador de expectations
- boton UI opcional en historial

Done:
- un bug real se convierte en fixture en menos de 2 minutos

### Fase 4 — UI Agent Lab

Duracion: 1-2 semanas.

Entregables:
- `AgentLabPage`
- listado de suites/runs
- detalle de run
- diff visual
- promocion manual

Done:
- operador puede correr suite smoke desde UI y leer resultado

### Fase 5 — Judges IA bajo contrato

Duracion: 1 semana.

Entregables:
- `LLMRubricJudge`
- fixtures propios para judges
- gate de parseo JSON
- advisory mode

Done:
- judge IA no se habilita si sus evals fallan

### Fase 6 — Promotion workflow

Duracion: 1 semana.

Entregables:
- promotion records
- waivers
- audit trail
- changelog de agentes

Done:
- un prompt candidato puede promocionarse con evidencia y rollback

---

## 22. Primer backlog concreto

### AL-01 — Runtime dispatch real

**Problema:** `agent_runner.py` acepta `codex_cli` pero cae a fallback.

**Implementar:**
- Despachar a `services.codex_cli_runner.start_codex_cli_run`.
- Requerir `vscode_agent_filename` cuando runtime sea `codex_cli`.
- Actualizar `Agents.runWithOptions`.
- UI debe pasar `vsCodeAgent.filename` si existe.
- Si no hay filename, devolver 400 con mensaje claro.

**Harness:**
- Test con monkeypatch de `start_codex_cli_run`.
- Test runtime desconocido.
- Test `claude_code_cli` no implementado.

### AL-02 — Fixture loader

**Implementar:**
- Leer `backend/evals/agents/**/fixtures/*.json`.
- Validar schema minimo.
- Normalizar `run_options`.

**Harness:**
- Fixture valido.
- Fixture sin `agent_type`.
- Fixture con `context_blocks` invalido.

### AL-03 — Deterministic judge pack

**Implementar:**
- ContractJudge
- RegexJudge
- ConfidenceJudge
- CostLatencyJudge
- PiiLeakJudge

**Harness:**
- Output bueno.
- Output sin secciones.
- Output con forbidden phrase.
- Output con PII.

### AL-04 — Mock runtime

**Implementar:**
- Devuelve output desde fixture si existe `mock_output`.
- Permite simular error/timeout.

**Harness:**
- Success.
- Error.
- Timeout.

### AL-05 — Report JSON

**Implementar:**
- Guardar corrida en `backend/data/agent_lab/runs/<run_id>/`.
- `report.json`.
- `output.md`.
- `logs.jsonl`.

**Harness:**
- Verificar archivos.
- Verificar schema de report.

### AL-06 — Compare baseline

**Implementar:**
- Baseline por fixture.
- Delta score.
- Regresiones P0/P1/P2.

**Harness:**
- Candidate mejor.
- Candidate peor.
- Candidate mas caro.

---

## 23. Fixtures iniciales sugeridos

Usar ejecuciones/tickets ya conocidos por el repo:

| Agente | Fixture | Objetivo |
|---|---|---|
| Functional | Epic con RF incompleto | No inventar RF faltante. |
| Functional | Epic con pending-task previo | Reconocer artifact existente. |
| Technical | Ticket 120 grilla vacia | Bloquear por datos insuficientes si aplica. |
| Technical | Ticket con RIDIOMA | Exigir plan tecnico + referencias. |
| Developer | Cambio chico con scope estricto | No tocar archivos fuera del alcance. |
| Developer | Falla de build | Reportar comandos y error sin inventar PASS. |
| QA | Ambiente caido | Verdict BLOCKED, no FAIL funcional. |
| QA | Implementacion correcta | PASS con evidencia. |
| Debug | CI log con error claro | Ubicar causa y reproduccion. |
| Critic | Output incompleto | Encontrar supuestos y edge cases. |

---

## 24. Metricas de exito

### 24.1 Producto

- 80% de cambios de prompt pasan por Agent Lab antes de usarse.
- 100% de bugs graves generan fixture de regresion.
- Tiempo de validar un prompt baja de horas a minutos.
- Menos re-runs por outputs incompletos.

### 24.2 Tecnicas

- Suite smoke corre en < 2 min con mock.
- Suite regression corre en < 20 min con runtime real.
- 0 publicaciones externas desde Agent Lab.
- 0 PII leaks en reports.
- Reporte reproducible por `run_id`.

### 24.3 Calidad

- Approval rate real sube despues de promociones.
- Cost per approved output baja.
- Drift de prompts detectado antes de llegar a produccion.

---

## 25. Riesgos

| Riesgo | Mitigacion |
|---|---|
| Fixtures pobres producen falsa confianza | Convertir bugs reales en fixtures; revisar suite mensualmente. |
| Judges IA hallucinan | JSON estricto, evals propios, deterministic judges obligatorios. |
| Costo alto de suites reales | Mock primero, runtime real solo en release/canary. |
| Runtimes editan archivos reales | Worktree/sandbox por corrida. |
| Promociones apresuradas | Waivers auditados y aprobacion humana. |
| Demasiada UI antes de valor | Empezar por CLI + JSON reports. |

---

## 26. Decision recomendada

Implementar Agent Lab en este orden:

1. Runtime dispatch real para `codex_cli`.
2. Harness MVP con mock runtime.
3. Fixtures iniciales por agente.
4. Compare contra baseline.
5. Replay desde ejecuciones reales.
6. UI y promotion workflow.

Esto transforma Stacky Agents en una plataforma que no solo ejecuta agentes, sino que **los mejora con evidencia**.

El valor exponencial aparece cuando cada bug real, cada output aprobado y cada descarte se convierte en aprendizaje permanente.

