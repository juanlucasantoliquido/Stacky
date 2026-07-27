# Plan 100 — Suite DevOps en un click: activación en lote HITL del paquete de flags + primeros pasos inline

**Estado:** ❌ **OBSOLETO / SUPERADO — NO IMPLEMENTAR**
**Versión:** v2 (v1: 2026-07-06 · veredicto de vigencia: 2026-07-26)
**Veredicto del juez:** **RECHAZADO.** Premisa falsificada + 3 defectos que rompen en la primera corrida.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## VEREDICTO: OBSOLETO. El dolor que este plan ataca ya no existe.

Este documento se conserva como registro. **No debe implementarse.** Nada de su alcance
sobrevive: el problema fue eliminado por una directiva del operador y sus dos features
secundarias ya están construidas por otros planes.

---

## 1. La premisa central es FALSA hoy

El plan v1 se sostiene íntegro sobre una sola afirmación (§GAP, §1, §2, KPI-1):

> *"El operador que quiere el panel DevOps completo hoy pulsa 'Activar ahora' en CADA banner
> (hasta 6 flags devops), navegando sección por sección."*
> *KPI: "Clicks para dejar el panel DevOps completamente operativo: **hasta 6** → 2"*

**Las 7 flags del "paquete" son default ON.** Medido en `backend/config.py` el 2026-07-26:

| Flag del paquete | Default efectivo | Evidencia |
|---|---|---|
| `STACKY_DEVOPS_PANEL_ENABLED` | **`"true"`** | `backend/config.py:1463-1464` |
| `STACKY_DEVOPS_PUBLICATIONS_ENABLED` | **`"true"`** | `backend/config.py:1475-1476` |
| `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` | **`"true"`** | `backend/config.py:1482-1483` |
| `STACKY_DEVOPS_AGENT_ENABLED` | **`"true"`** | `backend/config.py:1518-1519` |
| `STACKY_DEVOPS_SERVERS_ENABLED` | **`"true"`** | `backend/config.py:1526-1527` |
| `STACKY_PIPELINE_GENERATOR_ENABLED` | **`"true"`** | `backend/config.py:1410-1411` |
| `STACKY_PIPELINE_TRIGGER_ENABLED` | **`"true"`** | `backend/config.py:1403-1404` |

En una instalación limpia el panel DevOps arranca **completamente operativo con CERO clicks**.
El "botón que activa el paquete" abriría un modal cuyo propio caso borde —el que el v1 §F2
describe como excepcional— es **el caso normal**: `off.length === 0` ⇒
*"Todas las funciones DevOps ya están activas"* + sin checkbox + sin botón. Es decir: **el
entregable del plan es un botón que, por diseño, no hace nada.**

**Causa raíz de la obsolescencia:** el barrido de flags default ON (directiva del operador —
"flags nuevas OFF→ON salvo las que quemen tokens ociosos o escriban en un sistema real") y el
flip explícito del 2026-07-09 anotado en el propio `config.py` (`:1564`, `:1521-1522`:
*"Default ON (activado 2026-07-09, decisión explícita del operador)"*). El plan 100 fue escrito
tres días antes de esa decisión.

**Precedente de la casa:** es el mismo patrón por el que el **plan 184 fue rechazado por
vigencia** (su premisa —"ordenar la integración de 8 planes pendientes"— era falsa porque 7 de
las 8 capas ya estaban en main).

## 2. Las dos features secundarias YA ESTÁN IMPLEMENTADAS

El v1 §1 agregaba dos "primeros pasos inline". **Ambos existen.**

| "Primer paso" del v1 | Estado | Evidencia |
|---|---|---|
| (a) *"cargar el catálogo de procesos SIN salir de la sección"* | **YA IMPLEMENTADO** | `frontend/src/components/devops/PublicationsSection.tsx:138` (`handleAutoDetect`), llama `GET /api/projects/<p>/process-catalog/autodetect` (`:145`, endpoint real en `backend/api/client_profile.py:392`), botón montado en `:290`. Solo cae al mensaje "Cargá el catálogo en Configuración → Perfil del cliente" cuando la detección **no encuentra nada** — que es el fallback correcto, no una fricción. |
| (b) *"crear el preset `todo-completo` cuando falta"* | **YA IMPLEMENTADO** | `frontend/src/components/devops/EnvironmentsSection.tsx:248` (`handleCreateTodoPreset`), botón en `:532`. Además `applyAutodetectedCatalog` ya devuelve `createdTodoPreset` y lo asegura dentro del propio autodetect (`PublicationsSection.tsx:160-168`). |

Con la premisa muerta y las dos features construidas, **el plan queda sin alcance real**.

## 3. Y además: 3 defectos que lo romperían en la primera corrida

Aunque la premisa siguiera viva, el v1 **no era implementable como está escrito**. Se dejan
documentados porque son la clase de bug que esta casa persigue.

### D1 — BLOQUEANTE — `read_current()` no devuelve lo que el snippet asume ⇒ **500 inmediato**
El v1 §F0 escribe:

```python
    current = read_current()          # el plan lo describe como: dict key -> valor efectivo (bool)
    ...
    "enabled": bool(current.get(key, False)),
```

La firma real es **`def read_current() -> list[dict]:`** (`backend/services/harness_flags.py:5064`
— *"Devuelve spec + valor actual de cada flag del registry"*). Una `list` **no tiene `.get`**
⇒ `AttributeError` ⇒ el endpoint devuelve **500 en su primera invocación**. El test 1 del v1
(`test_bundle_200_always`) fallaría — pero el plan lo declara como criterio verde.

### D2 — BLOQUEANTE — `get_plain_help` **no existe** ⇒ ayuda vacía en silencio, con test cómplice
El v1 §F0 usa `from services.harness_flags_help import get_plain_help` y luego
`getattr(help_obj, "what", "")`. Medido: **`get_plain_help` tiene 0 hits en todo el backend.**
El accessor real es **`plain_help_for(key) -> dict | None`**
(`backend/services/harness_flags_help.py:1687`), y devuelve un **dict**, no un objeto
`PlainHelp`. Por lo tanto `getattr(dict, "what", "")` devuelve **siempre `""`**.

Lo grave no es el error: es que **el test del propio plan lo bendice**. El v1 caso 6
(`test_bundle_has_plain_help_fields`) dice textualmente *"cada item trae las keys `what`,
`on_effect`, `risk` (strings; **pueden ser vacíos** pero existen)"*. Resultado: **la feature
está 100% rota y la suite está 100% verde.** Falso verde perfecto.

El v1 lo intuyó y lo delegó — §F0 trae una *"Nota de investigación para el implementador:
verificar el nombre real del helper... si el accessor no se llama `get_plain_help`, usar el que
exista"*. **Eso no es un plan: es una tarea de investigación abierta**, prohibida para modelos
menores (Haiku/Codex/Copilot tendrían que INFERIR). Mismo defecto en §3.1 del plan 101 y §3.1
del 102 (la coletilla *"resolver por test"*).

### D3 — IMPORTANTE — `ActivateSuiteModal.tsx` nace violando el ratchet de deuda UI
El v1 §F2 crea un `.tsx` **nuevo** con ~15 `style={{` literales y un
`<input type="checkbox" ...>` crudo. La regla de la casa para archivos nuevos es **alcance 0**:
primitivas `Input/Select/Textarea/Checkbox` y **cero `style={{`**
(`frontend/src/__tests__/uiDebtRatchet.test.ts:4` — *"la deuda solo puede BAJAR"*; `:161` fuerza
cero en las carpetas cubiertas). El archivo entraría con deuda de fábrica.

---

## 4. Lo único que sobrevive (y ya tiene dueño)

Nada del v1 justifica un plan. Dos observaciones se reciclan **como notas**, no como alcance:

1. **`FlagGateBanner` sigue vivo y sigue siendo correcto**
   (`frontend/src/components/devops/FlagGateBanner.tsx`). Activar UNA flag con contexto es el
   patrón bueno; el problema nunca fue el banner, fue el default OFF — y ese ya se corrigió en
   la fuente.
2. **La postura del v1 §3.6 sobre `harness_defaults.env` era CORRECTA y sigue vigente**: ese
   archivo es un **snapshot generado** (`deployment/export_harness_defaults.py`), **no se edita
   a mano** y la UI no debe escribirlo en runtime. Esa conclusión ya es doctrina del repo y no
   necesita este plan para sostenerse.

## 5. Qué hacer en lugar de implementarlo

- **Nada.** No hay trabajo residual que rescatar.
- Si en el futuro el operador quiere volver a un panel con flags OFF por default, el problema a
  resolver **no** sería "activar en lote": sería revisar la directiva de defaults. El botón sería
  un parche sobre una decisión, no una mejora.
- El número **100 queda consumido**. No reutilizarlo.

## 6. [ADICIÓN ARQUITECTO] La lección transferible

Los tres planes de esta tanda (100, 101, 102) comparten el mismo defecto de método y vale
dejarlo escrito para los próximos:

> **Un plan que contiene la frase "verificar el nombre real del helper", "usar el que exista" o
> "resolver por test" NO está terminado.** Un anclaje sin verificar es una hipótesis, y una
> hipótesis en un plan es una tarea de investigación que el implementador va a resolver
> improvisando. La regla mínima: **cada símbolo que el plan invoca debe haber sido abierto y su
> firma copiada**, no recordada. Aquí, dos llamadas (`read_current`, `get_plain_help`) habrían
> costado dos greps y se llevaban puesta la fase entera.

Corolario para los tests: **un test que acepta el valor vacío como válido no prueba la feature,
prueba el andamio.** `test_bundle_has_plain_help_fields` habría quedado verde para siempre sobre
una ayuda llana que nunca se mostró.
