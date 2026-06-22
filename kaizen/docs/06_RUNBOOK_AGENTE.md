# 06 — Runbook del Agente: Lanzar una Sesión Completa

> Procedimiento **determinístico y sin ambigüedad** para que CUALQUIER agente (o persona)
> ejecute una sesión de automejora de punta a punta. Seguilo en orden. Todas las rutas son
> relativas a la raíz `kaizen/`. Todos los comandos se corren **parado en `kaizen/`**.

## 0. Prerrequisitos (una sola vez)
- Python 3.8+ disponible (los scripts usan solo la librería estándar).
- Config activa creada:
  ```sh
  cp config/kaizen.config.example.yaml config/kaizen.config.yaml
  ```
- Punto de entrada único: `python kaizen.py help` (lista todos los subcomandos).

## 1. Elegí UN objetivo acotado
Una sola mejora, medible, reversible. Si tenés varias, son varias sesiones.
Ejemplo: `"mejorar los mensajes de error del validador"`.

## 2. Crear la sesión
```sh
python kaizen.py new "tu objetivo acotado"
```
- Imprime la ruta de la sesión, p.ej. `sessions/2026-06-21T1925Z__tu-objetivo-acotado`.
- **Guardá ese `<session_id>`** (la parte después de `sessions/`). Lo vas a usar en cada paso.

## 3. PROPONER — escribí `sessions/<session_id>/proposal.json`
Debe cumplir `contracts/proposal.schema.json`. Plantilla exacta (reemplazá los valores):
```json
{
  "session_id": "<session_id>",
  "title": "Título corto",
  "summary": "Qué cambia, 1-3 frases.",
  "motivation": "Por qué vale la pena (problema real).",
  "scope": { "in": ["qué SÍ incluye"], "out": ["qué deja afuera"] },
  "risks": ["riesgos conocidos"],
  "reversibility": { "reversible": true, "rollback": "Cómo se deshace. OBLIGATORIO." },
  "success_metric": "Cómo se mide OBJETIVAMENTE que mejoró.",
  "author": "agent:improver",
  "artifacts": ["rutas/relativas/que/vas/a/tocar"]
}
```
> Regla dura: `reversibility.rollback` y `success_metric` son **obligatorios**. Sin ellos, el gate
> rechaza o escala.

## 4. APLICAR — implementá la mejora de verdad
Hacé el cambio real (código, doc, lo que sea), dentro del alcance declarado.
**No** ejecutes acciones destructivas. Dejá el rollback posible.

## 5. MEDIR — ejecutá la `success_metric`
Corré el comando/prueba que demuestra que la mejora funciona y **anotá el resultado real**
(salida, exit code). La evaluación del paso 6 debe basarse en esta evidencia, no en suposiciones.

## 6. EVALUAR — escribí `sessions/<session_id>/evaluation.json`
Debe cumplir `contracts/evaluation.schema.json`. Aplicá la rúbrica de `docs/04_HUMAN_REVIEW.md`
(criterios C1..C5, 0-3 cada uno). Plantilla exacta:
```json
{
  "session_id": "<session_id>",
  "findings": ["hallazgo con evidencia de la medición del paso 5"],
  "scores": { "value": 3, "correctness": 3, "scope": 3, "reversibility": 3, "measurability": 3 },
  "total": 15,
  "blocking": [],
  "preliminary_verdict": "accept",
  "confidence": 0.9,
  "evaluator": "agent:evaluator"
}
```
- `total` = suma de los 5 scores (0-15). Si no coincide, el gate lo marca con un WARN.
- `blocking`: lista de `B1`/`B2`/`B3`/`B4` si se dispara algún bloqueante (ver `docs/04`).
- `confidence`: honesto. Si es `< 0.7`, el gate **escala a humano**.

## 7. (Recomendado) Validar antes del gate
```sh
python kaizen.py validate <session_id>
```
Debe decir "Todos los artefactos presentes validan." (exit 0). Si hay errores, corregilos.
> `--strict` exige además decision.json; usalo **después** del gate, no antes.

## 8. DECIDIR — corré el gate determinista
```sh
python kaizen.py run <session_id>
```
Imprime `verdict=... status=... total=... escalated=...` y escribe `decision.json` +
`session.output.json`, actualiza el índice y deja traza forense. Interpretá el veredicto:

| Veredicto | Significa | Qué hacés |
|---|---|---|
| `accept` | score ≥ umbral, sin bloqueantes | Paso 9 (promover) y cerrás. |
| `reject` | score bajo o bloqueante no corregible | Replanteá; abrí una sesión nueva si insistís. |
| `iterate` (+`escalated=False`) | dirección buena, falta pulir | `python kaizen.py spawn-child <session_id>` y trabajás la hija. |
| `iterate` (+`escalated=True`) | confianza baja / irreversible | **Para. Decide un humano.** No auto-continúes. |

## 9. REGISTRAR — promové la decisión (si fue `accept`)
```sh
python kaizen.py promote <session_id>     # crea decisions/NNNN-<slug>.md (ADR-lite)
```

## 10. ANALIZAR — verificá eficiencia y consistencia
```sh
python kaizen.py view <session_id>        # timeline forense de ESTA sesión
python kaizen.py metrics                  # reporte agregado de todas las sesiones
python kaizen.py selfcheck                # guard de consistencia (debe dar 0 fallas)
```

---

## Receta mínima (copia-pega) para una sesión `accept`
```sh
cd kaizen
REL=$(python kaizen.py new "mi objetivo acotado")        # 1. crear
SID=$(basename "$REL")                                   #    capturar id
# 2. escribir sessions/$SID/proposal.json   (paso 3)
# 3. implementar la mejora                  (paso 4)
# 4. medir la success_metric                (paso 5)
# 5. escribir sessions/$SID/evaluation.json (paso 6)
python kaizen.py validate "$SID"                         # 7. validar
python kaizen.py run "$SID"                               # 8. gate
python kaizen.py promote "$SID"                           # 9. promover (si accept)
python kaizen.py view "$SID"                              # 10. auditar
```

## Reglas duras (no negociables)
1. **Sin falsos verdes:** la evaluación se basa en una medición real (paso 5), no en intención.
2. **Reversibilidad obligatoria:** siempre declarás `rollback`.
3. **Una sola mejora por sesión:** acotada; lo demás es otra sesión.
4. **No destructivo:** ninguna acción irreversible sin aprobación humana.
5. **Append-only:** no reescribís sesiones ni decisiones previas; iterás con sesiones hijas.
6. **Si el gate escala (`escalated=True`): se detiene y decide un humano.**

## Si algo falla
- `validate` da errores → tu JSON no cumple el contrato; corregí los campos que lista.
- `run` dice "falta proposal/evaluation" → te faltó escribir ese artefacto (pasos 3/6).
- `metrics`/`view` con datos raros → revisá `sessions/_forensic.jsonl` (log forense crudo).
