# Corpus GitLab CI — procedencia declarada (Plan 249 F0)

Verificado el 2026-07-26: **no existe corpus GitLab real** en este repositorio ni fuera de él
(`find . -iname "*gitlab-ci*"` fuera de `node_modules` devuelve cero resultados). En vez de
inventar uno y llamarlo "real", el corpus de este plan tiene **tres niveles** y cada archivo
declara a cuál pertenece.

## nivel A — derivado (regenerable por comando)

`derived/*.gitlab-ci.yml` — uno por cada golden ADO de `tests/fixtures/cicd_nl/golden/`.

- **Receta:** `to_gitlab_yaml(parse_ado_yaml(<golden ADO>))`.
- **Generador:** `backend/scripts/regen_gitlab_derived_corpus.py`.
- **Guardia de deriva:** regenerar y comparar **byte a byte**. Es más fuerte que vendorizar,
  porque no depende de ninguna ruta externa a esta máquina (a diferencia del corpus ADO, cuya
  guardia compara contra `N:\GIT\RS\RSPACIFICO\pipelines`).
- **Qué representa:** exactamente lo que Stacky emite hoy para GitLab. No representa "un pipeline
  GitLab típico"; representa **la salida propia**, que es justo lo que las reglas `GL*` tienen que
  poder juzgar.

## nivel B — repros por regla (sintéticos, declarados como tales)

Viven en el código, no en disco: `GL_REPROS` y `GL_CONTRA_REPROS` en
`backend/tests/test_plan249_reglas_gitlab.py`.

- **Qué son:** el YAML mínimo que dispara cada `GL000..GL011`, y su gemelo mínimamente distinto
  que **no** debe dispararla.
- **Guardia:** `test_repro_de_cada_regla_dispara_su_regla` y
  `test_todo_contra_repro_NO_dispara_su_regla`. Una regla sin `repro` o sin `contra_repro` rompe
  el test: la completitud es **por construcción**, no por disciplina.

## nivel C — real (AUSENTE, y se declara)

`real/` **no existe**, a propósito.

**no existe corpus GitLab real** al que Stacky tenga acceso hoy. El espejo mira una carpeta
vacía y **calla**: silencio antes que un golden inventado (misma doctrina que
`services/cicd_corpus_mirror.py`). Cuando el operador aporte un `.gitlab-ci.yml` de un proyecto
suyo, va acá con su propia guardia de procedencia.
