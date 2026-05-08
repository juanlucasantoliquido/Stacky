# Build Manager

CLI Python para compilar soluciones RS Pacífico con MSBuild. Forma parte del ecosistema **Stacky Tools**.

## Requisitos

- Python 3.8+
- Visual Studio 2022 (Community, Professional o Enterprise) instalado
- Acceso de lectura/escritura al repositorio local

## Uso

```powershell
# Ver soluciones disponibles
python build.py list
python build.py list --system online
python build.py list --system batch

# Compilar por nombre
python build.py compile --system online --solution AgendaWeb
python build.py compile --system batch  --solution Motor

# Compilar en Debug
python build.py compile --system online --solution AgendaWeb --config Debug

# Compilar por ruta completa
python build.py compile --solution "N:\GIT\RS\RSPacifico\trunk\OnLine\Soluciones\AgendaWeb.sln"
```

## Salida

Siempre JSON a stdout. Exit code `0` = build exitoso, `1` = build fallido o error.

Campo clave: `build_success` (bool) — los agentes deben verificar este campo antes de hacer commit/push/PR.

## Configuración

Editar `build-config.json` si MSBuild no está en la ruta predeterminada:

```json
{
  "msbuild": "C:\\ruta\\a\\MSBuild.exe"
}
```

## Contrato con agentes

Los agentes que modifican código **DEBEN** llamar esta tool y verificar `build_success: true` antes de cualquier commit, push o PR. Si `build_success` es `false`, deben corregir los errores listados en el campo `errors` y volver a compilar.

Ver [SPEC.md](SPEC.md) para el contrato completo y ejemplos de output JSON.


---

## Arquitectura

```mermaid
flowchart TD
    subgraph CALLERS["CONSUMIDORES - Quienes llaman a build.py"]
        DEV_AG["Agente Desarrollador\n(build obligatorio antes de commit/PR)"]
        QA_AG["Agente QA UAT\n(build previo al deploy local)"]
        CLI_USER["Operador via terminal"]
    end

    subgraph BUILD_TOOL["BUILD MANAGER - build.py"]
        direction TB
        CFG["build-config.json\nruta a MSBuild.exe"]
        DETECT["Detectar soluciones\nen trunk/OnLine/ y trunk/Batch/"]
        LIST_CMD["list - Listar soluciones disponibles"]
        COMPILE_CMD["compile - Compilar solucion .sln"]
        MSBUILD["Invocar MSBuild\nVisual Studio 2022"]
    end

    subgraph WORKSPACE["WORKSPACE LOCAL"]
        SRC["trunk/OnLine/ y trunk/Batch/\ncodigo fuente .cs/.aspx"]
        SLN["Soluciones .sln"]
        BIN["Binarios compilados\nbin/ obj/"]
    end

    subgraph OUTPUT["OUTPUT - siempre JSON"]
        OK["build_success: true\n+ warnings (array)"]
        FAIL["build_success: false\n+ errors (array con linea y mensaje)\n+ exit code 1"]
    end

    subgraph CONTRATO["CONTRATO CON AGENTES"]
        RULE["OBLIGATORIO: verificar build_success: true\nantes de cualquier commit, push o PR"]
    end

    DEV_AG & QA_AG & CLI_USER --> CFG
    CFG --> DETECT
    DETECT --> SLN
    SLN --> LIST_CMD & COMPILE_CMD
    COMPILE_CMD --> MSBUILD
    MSBUILD --> SRC
    SRC --> BIN
    MSBUILD --> OK
    MSBUILD -->|"Errores de compilacion"| FAIL
    OK --> RULE
    FAIL --> RULE
```

---

## Flujo de compilacion tipico

```mermaid
sequenceDiagram
    participant DEV as Agente Desarrollador
    participant BM as build.py
    participant MSB as MSBuild.exe
    participant SRC as trunk/OnLine/AgendaWeb/

    DEV->>BM: python build.py compile --system online --solution AgendaWeb
    BM->>BM: Resolver ruta a AgendaWeb.sln
    BM->>MSB: MSBuild AgendaWeb.sln /p:Configuration=Release
    MSB->>SRC: Compilar archivos .cs y .aspx
    SRC-->>MSB: Resultado de compilacion
    MSB-->>BM: Exit code + output
    BM-->>DEV: {"build_success": true, "solution": "AgendaWeb", "warnings": []}
    DEV->>DEV: Verificar build_success: true -> proceder con commit/PR
```

---

## Input / Output

| Accion | Input | Output clave |
|---|---|---|
| `list` | sistema opcional (online/batch) | Array de soluciones disponibles con rutas |
| `compile` | sistema + nombre de solucion | `build_success`, `errors`, `warnings` |

---

## Sinergia con el pipeline de desarrollo

```mermaid
flowchart LR
    IMPL["Implementacion\nde codigo"]
    BUILD["Build Manager\nbuild.py"]
    OK{"build_success?"}
    FIX["Corregir errores"]
    COMMIT["Git commit + push"]
    PR["Git Manager\nCrear PR"]
    IMPL --> BUILD --> OK
    OK -->|"true"| COMMIT --> PR
    OK -->|"false"| FIX --> IMPL
```
