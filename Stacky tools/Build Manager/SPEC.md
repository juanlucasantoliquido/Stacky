---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-04
---

# SPEC — Build Manager (`build.py`)

## 1. Propósito

CLI Python para compilar soluciones RS Pacífico con MSBuild desde agentes o terminal. Es la **única interfaz autorizada** del ecosistema Stacky para compilar código y actúa como **gate bloqueante** antes de cualquier commit, push o PR.

**Regla de negocio:** Si `build_success` es `false` (exit code 1), el agente NO puede crear commit, push ni PR. Debe corregir los errores y volver a llamar la tool hasta obtener `build_success: true`.

## 2. Alcance

**Hace:**
- Listar soluciones disponibles por sistema (OnLine / Batch)
- Compilar cualquier solución con MSBuild en modo Release o Debug
- Parsear errores y warnings de MSBuild y devolverlos como JSON estructurado
- Retornar exit code 0 = build ok, exit code 1 = build fallido o error de tool

**NO hace:**
- Ejecutar tests (ni unitarios ni funcionales)
- Hacer deploy ni copiar binarios
- Gestionar dependencias NuGet (las restaura MSBuild automáticamente si están configuradas)
- Modificar código fuente

## 3. Inputs

### Forma de invocación

```bash
python build.py <accion> [argumentos]
```

### Acciones y sus argumentos

| Acción | Args obligatorios | Args opcionales |
|---|---|---|
| `list` | — | `--system online\|batch` |
| `compile` | `--solution <nombre o ruta>` | `--system online\|batch`, `--config Release\|Debug`, `--msbuild <ruta>` |

### Configuración (en orden de prioridad)

1. Args CLI: `--msbuild`
2. `build-config.json` en la carpeta del script

### Resolución de solución (`--solution`)

- Si es ruta absoluta o relativa existente → se usa directamente
- Si es nombre sin extensión → se busca `<nombre>.sln` en la carpeta del sistema indicado
- Si `--system` no fue especificado → se busca en `OnLine/Soluciones/` y `Batch/Soluciones/`

## 4. Outputs

### `list` — Éxito

```json
{
  "ok": true,
  "action": "list",
  "total": 2,
  "solutions": {
    "online": [
      { "name": "AgendaWeb", "file": "AgendaWeb.sln", "path": "N:\\...\\AgendaWeb.sln", "system": "online" },
      { "name": "AutoGestion", "file": "AutoGestion.sln", "path": "N:\\...\\AutoGestion.sln", "system": "online" }
    ],
    "batch": []
  }
}
```

### `compile` — Build exitoso (exit code 0)

```json
{
  "ok": true,
  "action": "compile",
  "build_success": true,
  "system": "online",
  "solution": "AgendaWeb.sln",
  "solution_path": "N:\\GIT\\RS\\RSPacifico\\trunk\\OnLine\\Soluciones\\AgendaWeb.sln",
  "config": "Release",
  "msbuild": "C:\\...\\MSBuild.exe",
  "exit_code": 0,
  "error_count": 0,
  "warning_count": 3,
  "errors": [],
  "warnings": [
    { "file": "FrmAgenda.aspx.cs", "line": 42, "col": 8, "code": "CS0618", "message": "..." }
  ],
  "summary": "Build succeeded.\n   0 Error(s)\n   3 Warning(s)"
}
```

### `compile` — Build fallido (exit code 1)

```json
{
  "ok": false,
  "action": "compile",
  "build_success": false,
  "system": "online",
  "solution": "AgendaWeb.sln",
  "solution_path": "N:\\...",
  "config": "Release",
  "exit_code": 1,
  "error_count": 2,
  "warning_count": 0,
  "errors": [
    { "file": "FrmAgenda.aspx.cs", "line": 87, "col": 5, "code": "CS0103", "message": "The name 'ddlDebitoAuto' does not exist in the current context" }
  ],
  "warnings": [],
  "summary": "Build FAILED.\n   2 Error(s)\n   0 Warning(s)",
  "recommendation": "Corregí todos los errores listados en 'errors' y volvé a compilar. NO crees commit, push ni PR hasta obtener build_success: true."
}
```

### Error de tool (exit code 1)

```json
{ "ok": false, "error": "MSBuild.exe no encontrado. Verificá que Visual Studio esté instalado..." }
```

## 5. Contrato con los agentes

### Para el agente DevPacifico (y cualquier agente que modifique código)

**ANTES de hacer commit/push/PR, el flujo obligatorio es:**

```
1. python build.py compile --system <online|batch> --solution <nombre>
2. Si build_success == false:
   a. Leer campo "errors" del JSON
   b. Corregir cada error en el código
   c. Volver al paso 1
3. Si build_success == true → proceder con commit/push/PR
```

**El agente NUNCA puede ignorar un exit code 1 o un `build_success: false`.**

### Ejemplo de invocación por agente

```powershell
# OnLine
python "N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\Build Manager\build.py" compile --system online --solution AgendaWeb

# Batch
python "N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\Build Manager\build.py" compile --system batch --solution Motor
```

## 6. Soluciones disponibles

### OnLine (`trunk/OnLine/Soluciones/`)

| Nombre | Descripción |
|---|---|
| `AgendaWeb` | Aplicación web principal (agenda, gestión de créditos) |
| `AutoGestion` | Portal de autogestión de clientes |

### Batch (`trunk/Batch/Soluciones/`)

| Nombre | Descripción |
|---|---|
| `Motor` | Motor principal de procesamiento batch |
| `MotorJ` | Motor J (procesamiento judicial) |
| `RSProcIN` | Proceso de entrada |
| `RSProcOUT` | Proceso de salida |
| `RSNovMasivas` | Novedades masivas |
| `RSSimulacion` | Simulación de cuentas |
| `RSPropuesta` | Propuestas |
| `RSHistoSIC` | Histórico SIC |
| `RsExtrae` | Extracción de datos |
| `RSConverterWF` | Converter WF |
| `RSComi` | Comisiones |
| `RSAgExtOUT` | Agencia externa OUT |
| `RSAgExtIN` | Agencia externa IN |
| `RSAES256` | Criptografía AES256 |
| `Mul2Bane` | Multicanal Bane |
| `IncJudi` | Incidencias judiciales |
| `Inchost` | Incidencias host |
| `IncDemaJudi` | Demandas judiciales |

## 7. Seguridad

- El script no recibe ni transmite credenciales
- Solo ejecuta MSBuild con rutas locales del repo
- No ejecuta comandos arbitrarios — solo el ejecutable de MSBuild con args controlados
- El output de MSBuild es capturado y no ejecutado como código

## 8. Mantenimiento

- Si cambia la ruta de MSBuild → actualizar `build-config.json`
- Si se agrega una nueva solución al repo → aparece automáticamente en `list`
- Si se mueve la carpeta de soluciones → actualizar `_ONLINE_SLN_DIR` / `_BATCH_SLN_DIR` en `build.py`
