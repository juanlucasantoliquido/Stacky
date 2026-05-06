# Batch Test Generator

Herramienta CLI para generar, escanear y mantener tests unitarios NUnit para los procesos Batch de RS Pacifico. Forma parte del ecosistema **Stacky Tools**.

---

## Arquitectura

```mermaid
flowchart TD
    subgraph INPUT["INPUT"]
        BATCH_CODE["trunk/Batch/\ncodigo fuente C# de procesos batch"]
        CFG["config.json\nruta al workspace, configuracion de salida"]
        COPILOT["VS Code + Stacky Extension\npara enriquecimiento via Copilot"]
    end

    subgraph BTG["BATCH TEST GENERATOR - batch_test_gen.py"]
        direction TB
        LIST_CMD["list\nListar todos los procesos batch detectados"]
        SCAN_CMD["scan\nAnalizar un proceso batch en detalle"]
        GEN_CMD["generate\nGenerar archivos .cs de tests NUnit"]
        DIFF_CMD["diff\nMostrar cambios en trunk/Batch desde ultimo scan"]
        WATCH_CMD["watch\nMonitorear trunk/Batch y regenerar ante cambios"]
        ENRICH_CMD["enrich\nEnriquecer assertions via Copilot"]
        STATE["btg-state.json\nEstado persistente del ultimo scan"]
    end

    subgraph CORE["CORE - core/"]
        PARSER["Parser de codigo C#\ndetecta clases, metodos, parametros"]
        TEMPLATE["Generador de templates NUnit"]
        WATCHER["File watcher\nmonitoreo de cambios"]
    end

    subgraph OUTPUT["OUTPUT - siempre JSON"]
        TEST_CS["Archivos .cs de tests NUnit\npor proceso batch"]
        SCAN_JSON["Reporte de scan\nprocesos, sub-procesos, metodos detectados"]
        OK["ok: true + datos"]
        ERR["ok: false + error + exit code 1"]
    end

    subgraph SINERGIAS["SINERGIAS"]
        DEV_AG["Agente Desarrollador\nusa tests generados para validar implementacion"]
        BUILD["Build Manager\ncompila los tests generados"]
        COPILOT_SVC["GitHub Copilot\nenriquece assertions semanticamente"]
    end

    CFG --> LIST_CMD & SCAN_CMD & GEN_CMD & DIFF_CMD & WATCH_CMD & ENRICH_CMD
    BATCH_CODE --> SCAN_CMD & DIFF_CMD & WATCH_CMD
    SCAN_CMD --> CORE --> STATE
    GEN_CMD --> TEMPLATE --> TEST_CS
    DIFF_CMD --> STATE
    ENRICH_CMD --> COPILOT
    COPILOT --> COPILOT_SVC
    LIST_CMD & SCAN_CMD & GEN_CMD & DIFF_CMD --> OK & ERR
    TEST_CS --> DEV_AG
    TEST_CS --> BUILD
```

---

## Uso rapido

```bash
# Listar procesos batch detectados
python batch_test_gen.py list --pretty

# Analizar un proceso especifico
python batch_test_gen.py scan RSProcIN --pretty

# Generar tests NUnit para todos los procesos
python batch_test_gen.py generate --all

# Ver cambios en trunk/Batch desde el ultimo scan
python batch_test_gen.py diff

# Monitorear cambios y regenerar automaticamente
python batch_test_gen.py watch
```

---

## Input / Output

| Accion | Input | Output clave |
|---|---|---|
| `list` | — | Array de procesos batch con sub-procesos detectados |
| `scan` | nombre del proceso | Analisis detallado: clases, metodos, dependencias |
| `generate` | proceso o `--all` | Archivos `.cs` con tests NUnit por proceso |
| `diff` | — | Lista de archivos cambiados vs ultimo scan guardado |
| `watch` | — | Modo continuo: regenera tests ante cualquier cambio |
| `enrich` | — | Tests enriquecidos con assertions semanticas via Copilot |

---

## Configuracion

Editar `config.json`:

```json
{
    "workspace_root": "N:/GIT/RS/RSPacifico/trunk",
    "batch_path": "Batch",
    "output_path": "tests/batch_generated",
    "test_project": "RSPacifico.Tests"
}
```
