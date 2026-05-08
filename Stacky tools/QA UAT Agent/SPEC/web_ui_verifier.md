---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `web_ui_verifier.py`

## 1. Propósito

Módulo Python que compila el proyecto OnLine de ASP.NET, lo despliega localmente y verifica assertions básicas sobre el DOM usando Playwright. Es la **infraestructura de deploy + smoke test** sobre la que se construye el pipeline UAT. Actualmente es un *spike* (código de exploración) que el agente QA UAT reutiliza como dependencia para garantizar que la Agenda Web esté compilada y accesible antes de ejecutar los tests.

## 2. Alcance

**Hace:**
- Navegar a una URL del Agenda Web local y verificar que carga sin errores
- Verificar que un campo específico existe en el DOM y es visible
- Verificar que la validación de campo requerido dispara al intentar submit vacío
- Tomar screenshots como evidencia de cada verificación

**NO hace:**
- Compilar o deployar el proyecto (eso ocurre fuera de este módulo, en el pipeline de Stacky)
- Gestionar sesiones de usuario (login) — eso es responsabilidad de `uat_session_manager.py`
- Generar escenarios UAT o evaluar assertions de negocio
- Producir JSON a stdout — es un módulo Python, no un CLI

## 3. Inputs

### Uso como módulo

```python
from web_ui_verifier import WebUIVerifier

verifier = WebUIVerifier(config={
    "web_port": 5000   # puerto donde corre el Agenda Web local
})
result = verifier.verify(
    ticket_folder="projects/70",  # carpeta con el archivo de spec del ticket
    config={
        "url": "/AgendaWeb/FrmAgenda.aspx",
        "new_field_id": "ddlEmpresa",
        "required": False
    }
)
```

### Estructura de `spec` (extraída de `ticket_folder`)

| Campo | Tipo | Descripción |
|---|---|---|
| `url` | `str` | Path relativo de la pantalla a verificar (ej: `/AgendaWeb/FrmAgenda.aspx`) |
| `new_field_id` | `str` (opcional) | ID del campo nuevo a verificar en el DOM |
| `required` | `bool` (opcional) | Si el campo es requerido, verifica que la validación dispare al submit |

### Config de runtime

| Campo | Default | Descripción |
|---|---|---|
| `web_port` | `5000` | Puerto donde corre IIS Express o el servidor local |

## 4. Outputs

### Objeto Python `UITestResult`

```python
@dataclass
class UITestResult:
    cases: list[UITestCase]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)

@dataclass
class UITestCase:
    name: str         # descripción del caso
    passed: bool      # True si el caso pasó
    evidence: bytes | None  # screenshot PNG en bytes, si se tomó
```

### Casos generados automáticamente

| Caso | Condición de PASS |
|---|---|
| `"Page loads without errors"` | No hay elementos `.error-dialog`, `#errorDiv`, `.server-error` en el DOM |
| `"Field '<id>' exists in DOM"` | El selector `#<id>`, `[name='<id>']` o `[id$='<id>']` encuentra ≥ 1 elemento |
| `"Field '<id>' is visible"` | El elemento encontrado es visible (`.is_visible()`) |
| `"Required field validation fires"` | Al hacer click en el botón de submit sin rellenar el campo, aparece un validador `[id$='rfv<id>']` o `.field-validation-error` |

Si `url` no está en la spec → retorna un caso `"No UI URL detected"` con `passed=True` (no hay nada que verificar).

## 5. Contrato de uso

**Precondiciones:**
- Playwright instalado (`pip install playwright` + `playwright install chromium`)
- El Agenda Web compila y está accesible en `http://localhost:<web_port>`
- Si `new_field_id` se especifica, el campo debe existir en la pantalla para que el caso pase

**Postcondiciones:**
- No modifica ningún dato en la aplicación web
- No hace login — accede a la URL directamente; si la pantalla requiere autenticación, la navegación puede fallar silenciosamente (retorna caso `"Page navigation"` con `passed=False`)

**Idempotencia:** sí — múltiples invocaciones producen el mismo resultado si la app no cambió.

## 6. Validaciones internas

- Si Playwright no está instalado → caso `"Playwright available"` con `passed=False`, no lanza excepción
- Si la navegación falla (timeout, conexión rechazada) → caso `"Page navigation"` con `passed=False` y la excepción como `name`
- Timeouts: navigate `15000ms`, `wait_for_load_state` `10000ms`

## 7. Errores esperados

| Situación | Comportamiento |
|---|---|
| Playwright no instalado | Retorna `UITestResult` con un caso `passed=False` y mensaje de instrucción |
| `url` no especificada | Retorna un caso "No UI URL detected" `passed=True` |
| App no accesible (ECONNREFUSED) | `passed=False` en "Page navigation" con el error en el nombre del caso |
| Campo no existe en DOM | `passed=False` en "Field exists in DOM" |

> Esta herramienta **no lanza excepciones al caller**. Todos los errores se capturan y se representan como casos `passed=False`.

## 8. Dependencias

- `playwright` (`pip install playwright`) + `playwright install chromium`
- Python 3.8+ stdlib

## 9. Ejemplos de uso

### Smoke test de FrmAgenda.aspx

```python
from web_ui_verifier import WebUIVerifier

v = WebUIVerifier({"web_port": 80})
result = v.verify(
    ticket_folder="",
    config={
        "url": "/AgendaWeb/FrmAgenda.aspx",
        "new_field_id": "ddlEmpresa"
    }
)
for case in result.cases:
    print(f"{'PASS' if case.passed else 'FAIL'} — {case.name}")

assert result.passed, "La pantalla no pasó el smoke test"
```

### Desde el pipeline UAT

```python
# En uat_precondition_checker.py (Fase 3.B)
from web_ui_verifier import WebUIVerifier

verifier = WebUIVerifier({"web_port": int(os.getenv("AGENDA_WEB_PORT", "80"))})
smoke = verifier.verify("", config={"url": f"/AgendaWeb/{screen}"})
if not smoke.passed:
    return {"ok": False, "scenario": scenario_id, "reason": "DEPLOY_FAILED",
            "detail": [c.name for c in smoke.cases if not c.passed]}
```

## 10. Criterios de aceptación

- [ ] Con Agenda Web corriendo localmente, `verify(config={"url": "/AgendaWeb/FrmAgenda.aspx"})` retorna `result.passed == True`
- [ ] Sin Playwright instalado, retorna `UITestResult` con caso `passed=False` (no lanza excepción)
- [ ] Con `url=""` o sin campo `url`, retorna caso `"No UI URL detected"` con `passed=True`
- [ ] Con app no accesible (puerto incorrecto), retorna caso con `passed=False` describiendo el error
- [ ] Cada caso verificado que pasa incluye `evidence` (bytes del screenshot) no nulo

## 11. Tests requeridos

```
tests/unit/test_web_ui_verifier.py

test_no_url_returns_pass_case
test_playwright_not_installed_returns_fail_without_raising
test_page_load_pass_when_no_error_elements  (mock Playwright)
test_field_exists_pass_when_element_found   (mock Playwright)
test_field_not_found_returns_fail           (mock Playwright)
test_navigation_error_returns_fail          (mock Playwright)
```
