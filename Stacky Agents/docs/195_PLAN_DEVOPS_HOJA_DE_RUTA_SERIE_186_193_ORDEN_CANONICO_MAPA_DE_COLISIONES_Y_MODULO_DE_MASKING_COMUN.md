# Plan 195 — DevOps: hoja de ruta de la serie 186-193 — orden canónico, mapa de colisiones y módulo de masking común

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** DevOps — capstone de coordinación (precedente en la casa: plan 184, hoja de ruta DB Compare)

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy existen 6 planes DevOps hermanos CRITICADOS v2 y sin implementar —
**186** (lint de pipelines), **188** (evidencia de fallo → incidencia), **189** (rollback
readiness), **190** (equipaje portable), **191** (bitácora CI), **193** (triage de fallos CI) — que
al implementarse VAN a chocar entre sí: los 6 editan `services/harness_flags.py` en el MISMO punto
(bloque FlagSpec DEVOPS ~:2743 + `_CURATED_DEFAULTS_ON` ~:200-216) y el MISMO registro
(`scripts/run_harness_tests.sh`), 191+193 comparten `api/ci.py` y `TriggerPipelineSection.tsx`,
188+189 comparten `api/devops_deployments.py` y `DeploymentsSection.tsx`, y CUATRO (186/188/190/193)
definen su propia copia de `TOKEN_VALUE_PREFIXES`. Ese patrón es EXACTAMENTE el que dispara el
gotcha documentado del **merge duplicado silencioso** (git 3-way no marca conflicto cuando dos ramas
agregan la misma línea de cierre). Este plan es la hoja de ruta ejecutable que lo previene: **gate 0
de saneo de entorno** (venv ajeno py3.11 + `ratchet_meta` rojo, hallazgos verificados en vivo),
**orden canónico** que agrupa por archivos compartidos, **módulo común `services/secret_masking.py`**
con contenido congelado que el primer plan crea y los demás importan, **mapa de colisiones por
archivo** con regla por celda, y **gates compuestos post-merge**. Cero código de producto acá: el
entregable es la ruta que hace implementable la serie sin pisadas.

**KPI / impacto esperado (binarios, verificables al ejecutar la ruta):**

| KPI | Criterio binario |
|-----|------------------|
| KPI-1 | Gate 0 cumplido ANTES del primer plan: `venv\Scripts\python.exe --version` reporta py3.13 (o el venv se recreó) y el estado de `test_harness_ratchet_meta.py` quedó registrado (verde, o rojo-preexistente con causa anotada) |
| KPI-2 | Al cierre de la serie existe UN SOLO `TOKEN_VALUE_PREFIXES` en `Stacky Agents/backend/services/` (grep = 1 archivo: `secret_masking.py`) |
| KPI-3 | Tras CADA plan mergeado, el gate compuesto pasó: `python -m compileall backend` + `npx tsc --noEmit` + grep de keys FlagSpec duplicadas = 0 |
| KPI-4 | Los 6 planes implementados en el orden canónico (o con desvío ANOTADO en el propio doc de la ruta con su motivo) |
| KPI-5 | Cero regresión del gotcha: grep de líneas duplicadas consecutivas idénticas en `harness_flags.py` y `run_harness_tests.sh` = 0 tras cada merge |

**Ganancia robusta:** la serie completa (6 planes, ~35 archivos de test) se vuelve implementable en
secuencia o en paralelo por worktrees SIN el impuesto de deshacer pisadas — que en la serie 144-149
costó una sesión entera de auditoría.

**Onboarding casi nulo:** es un documento; el implementador (humano o modelo menor vía
`implementar-plan-stacky`) lo sigue paso a paso.

---

## 2. Por qué ahora / gap que cierra

- Los 6 planes nacieron en UN día (2026-07-18, loop de propuestas) compartiendo convenciones — y
  por eso mismo comparten superficies. Evidencia por lectura de los propios planes (secciones
  "Archivos" de cada F0): TODOS editan `harness_flags.py` "al final del bloque DEVOPS ~:2743",
  TODOS agregan a `_CURATED_DEFAULTS_ON`, TODOS registran tests en `run_harness_tests.sh`.
- El gotcha del **merge duplicado silencioso** está documentado en memoria del proyecto y ya
  mordió en la consolidación de 16 ramas (2026-07-16).
- El juez del plan 192 (sesión paralela) verificó EN VIVO: venv del backend en **py3.11 ajeno** y
  `test_harness_ratchet_meta.py` **rojo preexistente**. Implementar los 6 planes sobre ese entorno
  produce falsos rojos en cadena (cada DoD exige el meta-test).
- Precedente de formato: plan **184** (hoja de ruta de integración de la serie DB Compare 178-183)
  — mismo problema, misma solución, otra serie.
- Vecinos que NO se pisan: 184 (DB Compare), 192/194 (UX de la paralela). Esta ruta SOLO ordena la
  serie DevOps 186-193 (los planes 187/192/194 de la paralela no son de esta serie).

---

## 3. Principios y guardarraíles

1. **Esta ruta NO reescribe los 6 planes:** cada plan se implementa según SU doc v2. La ruta solo
   fija orden, entorno, módulo común y verificaciones entre planes. Ante contradicción, manda el
   plan individual y la discrepancia se ANOTA en la sección 8 de este doc.
2. **3 runtimes / cero trabajo del operador / HITL / mono-operador:** heredados de los 6 planes;
   esta ruta no agrega flags nuevas NI pasos del operador (el gate 0 lo ejecuta quien implementa).
3. **Paralelismo permitido SOLO entre grupos disjuntos** (ver §5): dentro de un grupo, secuencial
   estricto.
4. **Tras cada merge, gates compuestos SIEMPRE** (§7) — no negociable, es la mitigación del gotcha.
5. **Releer estado fresco antes de CADA plan:** `git log --oneline -10` + `git status` (la sesión
   paralela sigue activa; sus merges pueden tocar superficies compartidas — p.ej. 194 "copiar como
   servicio central" puede rozar helpers de portapapeles del 189).

---

## 4. Gate 0 — saneo de entorno (ANTES de implementar cualquier plan)

1. `cd "Stacky Agents\backend"` y `venv\Scripts\python.exe --version`.
   - Si NO es py3.13: recrear el venv con el intérprete del repo
     (`py -3.13 -m venv venv` + `venv\Scripts\python.exe -m pip install -r requirements.txt` — si
     `requirements.txt` no existe, instalar los paquetes que importan los tests del primer plan y
     ANOTAR el faltante acá).
2. `venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q` — registrar el
   resultado EN ESTE DOC (sección 8):
   - VERDE → los DoD de la serie usan "sigue verde".
   - ROJO → leer el mensaje, anotar la causa; los DoD de la serie usan el criterio NO-EMPEORAR
     (el fallo no debe mencionar archivos `planNNN` de la serie) — ya codificado en el plan 193 C2.
3. `npx tsc --noEmit` (cwd frontend) — mismo registro (verde / rojo preexistente con causa).

**Criterio binario del gate:** los 3 puntos ejecutados y sus resultados anotados en §8 (KPI-1).

---

## 5. Orden canónico (agrupado por superficies compartidas)

| # | Plan | Por qué en este lugar | Grupo |
|---|------|----------------------|-------|
| 1 | **190** equipaje portable | Independiente de las zonas calientes (toca `config_transfer`); **CREA `services/secret_masking.py`** (§6) que 3 planes posteriores importan | A (config) |
| 2 | **186** lint de pipelines | Toca `api/devops.py` + servicio nuevo propio; consume `secret_masking` para PL012(b) en vez de redefinir | B (devops.py) |
| 3 | **188** evidencia → incidencia | Primero de la pareja `devops_deployments.py` + `DeploymentsSection.tsx`; importa `secret_masking` | C (deployments) |
| 4 | **189** rollback readiness | Segundo de la pareja C — SOBRE el árbol ya mergeado de 188 (misma sección UI, misma API) | C (deployments) |
| 5 | **191** bitácora CI | Primero de la pareja `api/ci.py` + `TriggerPipelineSection.tsx` | D (ci) |
| 6 | **193** triage de fallos CI | Segundo de la pareja D — sus rutas van DESPUÉS de `/runs` de 191 (su propio F0 ya contempla ambos órdenes); importa `secret_masking` | D (ci) |

**Paralelismo permitido:** A→B→(C)→(D) es la secuencia segura simple. Si se implementa en paralelo
por worktrees: A y B pueden convivir; C y D pueden correr en paralelo ENTRE SÍ (archivos disjuntos)
pero cada pareja es secuencial POR DENTRO (188 antes que 189; 191 antes que 193). `harness_flags.py`
y `run_harness_tests.sh` los tocan TODOS → al mergear cada rama, aplicar §7 SIEMPRE.

**Regla de adopción del módulo común:** el plan que se implemente PRIMERO crea `secret_masking.py`
con el contenido de §6 (aunque el orden se altere); los siguientes IMPORTAN y sus tests de masking
apuntan al módulo común. Los docs 186/188/190/193 ya prevén esta sustitución ("si existiera en un
módulo compartido, importarla de ahí").

---

## 6. Módulo común `services/secret_masking.py` (contenido CONGELADO)

CREAR `Stacky Agents/backend/services/secret_masking.py` (lo crea el primer plan implementado):

```python
"""services/secret_masking.py — Plan 195 (serie DevOps 186-193). Masking canónico.

Única fuente de: prefijos de token conocidos, placeholder, sufijos de clave secreta.
Consumidores: 186 (PL012b), 188 (evidencia), 190 (notes export), 193 (logs CI).
PURO: sin red, sin config, sin imports de servicios.
"""
from __future__ import annotations

import re

TOKEN_VALUE_PREFIXES = ("ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "AKIA", "eyJhbGciOi")
MASK_PLACEHOLDER = "<posible-secreto-omitido>"
SECRET_KEY_SUFFIXES = ("_token", "_pat", "_password", "_secret", "_key", "_apikey")

_TOKEN_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in TOKEN_VALUE_PREFIXES) + r")[A-Za-z0-9_./+-]{8,}"
)


def mask_token_values(text: str) -> str:
    """Reemplaza por MASK_PLACEHOLDER toda substring prefijo-de-token + >=8 chars del set."""
    return _TOKEN_RE.sub(MASK_PLACEHOLDER, text or "")


def strip_secret_keys(obj):
    """Copia profunda de dict/list; claves cuyo lower() termina en SECRET_KEY_SUFFIXES o está
    en {"pat","token","password","secret","auth_header","api_key"} → "<omitido>"."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in {"pat", "token", "password", "secret", "auth_header", "api_key"} or \
               kl.endswith(SECRET_KEY_SUFFIXES):
                out[k] = "<omitido>"
            else:
                out[k] = strip_secret_keys(v)
        return out
    if isinstance(obj, list):
        return [strip_secret_keys(x) for x in obj]
    return obj
```

CREAR `Stacky Agents/backend/tests/test_secret_masking.py` (junto con el módulo, mismo commit;
registrarlo en `HARNESS_TEST_FILES`):
- `test_mask_prefijo` — `"ghp_" + "x"*20` (literal PARTIDO — gotcha push-protection) → placeholder.
- `test_mask_corto_no` — prefijo + 3 chars → intacto.
- `test_strip_por_sufijo_y_literal` — `{"deploy_token": "a", "password": "b", "host": "c"}` →
  token y password omitidos, host intacto.
- `test_strip_recursivo` — anidado en list/dict.
- `test_puro` — el SOURCE del módulo no contiene `import requests` ni `from services`.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_secret_masking.py -q`

---

## 7. Gates compuestos (tras CADA plan mergeado — mitigación del gotcha)

Ejecutar los 5, en orden; cualquier fallo se arregla ANTES de arrancar el siguiente plan:

1. `python -m compileall "Stacky Agents/backend" -q` → exit 0.
2. `npx tsc --noEmit` (cwd frontend) → sin errores nuevos vs. lo anotado en Gate 0.
3. Duplicados de flags: `grep -o "STACKY_[A-Z_]*_ENABLED" "Stacky Agents/backend/services/harness_flags.py" | sort | uniq -d`
   → salida VACÍA (una key duplicada = pisada silenciosa).
4. Duplicados de registro: `sort "Stacky Agents/backend/scripts/run_harness_tests.sh" | uniq -d | grep test_plan` → VACÍA.
5. El archivo de tests del plan recién mergeado corre verde POR ARCHIVO (gotcha reload de config).

---

## 8. Registro de ejecución (lo completa quien implementa — vive en este doc)

| Ítem | Resultado | Fecha |
|------|-----------|-------|
| Gate 0.1 — versión de venv | _pendiente_ | |
| Gate 0.2 — ratchet_meta (verde/rojo + causa) | _pendiente_ | |
| Gate 0.3 — tsc baseline | _pendiente_ | |
| Plan 190 + gates §7 | _pendiente_ | |
| Plan 186 + gates §7 | _pendiente_ | |
| Plan 188 + gates §7 | _pendiente_ | |
| Plan 189 + gates §7 | _pendiente_ | |
| Plan 191 + gates §7 | _pendiente_ | |
| Plan 193 + gates §7 | _pendiente_ | |
| KPI-2 — grep TOKEN_VALUE_PREFIXES = solo secret_masking.py | _pendiente_ | |
| Desvíos del orden (si hubo) + motivo | _pendiente_ | |

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Merge duplicado silencioso en archivos compartidos (el gotcha) | §7 gates 3-4 (grep de duplicados) tras CADA merge; agrupación C/D secuencial por dentro |
| La sesión paralela mergea algo que toca las mismas superficies | §3.5: git log/status frescos ANTES de cada plan; si aparece colisión nueva, anotarla en §8 y resolver ANTES de seguir |
| El primer plan implementado no es el 190 (orden alterado) | Regla §5: quien vaya primero CREA `secret_masking.py` igual; el orden es recomendación fuerte, el módulo común es obligación |
| Entorno roto produce falsos rojos en cadena | Gate 0 obligatorio + criterio NO-EMPEORAR (193 C2) heredado por toda la serie |
| Este doc queda desactualizado si un plan se re-critica a v3 | §3.1: manda el plan individual; la discrepancia se anota en §8 |

## 10. Fuera de scope

- Implementar los 6 planes (eso es `implementar-plan-stacky`, plan por plan, siguiendo esta ruta).
- Los planes de la sesión paralela (184/187/192/194 y series DB Compare/RSI) — otras rutas.
- Re-criticar los planes de la serie (ya están en v2).
- Automatizar los gates §7 como script (valioso; que lo proponga un plan futuro si la serie crece).

## 11. Glosario + Orden de implementación + DoD

- **Serie DevOps 186-193:** los 6 planes listados en §1 (187/192 son de la paralela, NO integran
  esta serie pese al rango numérico).
- **Gotcha del merge duplicado silencioso / reload de config / ratchet UI / curated:** ver memoria
  del proyecto y planes 186-193 (§7 los operacionaliza).
- **Orden de implementación:** Gate 0 → 190 → 186 → 188 → 189 → 191 → 193, con §7 tras cada uno.
- **DoD global de la ruta:** los 5 KPIs de §1 en verde y la tabla §8 completa sin `_pendiente_`.
