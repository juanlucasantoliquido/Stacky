"""
project_documenter.py — Genera el prompt para el agente documentador de Copilot.

El agente documentador recorre el workspace del proyecto y produce PROJECT_DOCS.md,
un documento de referencia que todos los demás agentes (PM, Dev, QA) pueden leer
en lugar de explorar el codebase desde cero en cada ticket.

El archivo se guarda en:
    Tools/Stacky/projects/{PROJECT}/PROJECT_DOCS.md

Uso:
    from project_documenter import build_doc_prompt, get_project_docs_path
    prompt = build_doc_prompt(project_name, workspace_root, docs_path)
"""

import os
from pathlib import Path


def get_project_docs_path(project_name: str, base_dir: str) -> str:
    """Retorna la ruta absoluta de PROJECT_DOCS.md para el proyecto activo."""
    return os.path.join(base_dir, "projects", project_name, "PROJECT_DOCS.md")


def build_doc_prompt(project_name: str, workspace_root: str, docs_output_path: str) -> str:
    """
    Construye el prompt para el agente documentador.

    El agente debe explorar el workspace y escribir PROJECT_DOCS.md,
    que sirve como contexto compartido y permanente para todos los agentes del pipeline.

    Args:
        project_name:     Nombre del proyecto (ej. "RSMOBILENET")
        workspace_root:   Raíz del workspace a documentar (ej. "N:/GIT/RS/RSPacifico")
        docs_output_path: Ruta absoluta donde guardar PROJECT_DOCS.md
    """
    # Ruta relativa para mostrar en el prompt
    try:
        docs_rel = os.path.relpath(docs_output_path, workspace_root).replace("\\", "/")
    except ValueError:
        docs_rel = docs_output_path.replace("\\", "/")

    already_exists = os.path.exists(docs_output_path)
    update_note = ""
    if already_exists:
        import time
        mtime = os.path.getmtime(docs_output_path)
        age_days = (time.time() - mtime) / 86400
        update_note = f"\n> ⚠️ Ya existe una versión de PROJECT_DOCS.md (hace {age_days:.0f} días). Actualizá las secciones que hayan cambiado, mantené las que siguen vigentes.\n"

    return f"""Generá la documentación técnica completa del proyecto **{project_name}**.

Workspace: `{workspace_root}`
Archivo de salida: `{docs_output_path}`
{update_note}
## Objetivo

Crear (o actualizar) `PROJECT_DOCS.md` — un documento de referencia técnica que van a usar
los agentes PM, Dev y QA del pipeline de tickets para entender el proyecto sin tener que
explorarlo de cero cada vez. Debe ser exhaustivo pero navegable.

## Estructura requerida de PROJECT_DOCS.md

### 1. Visión general del proyecto
- Propósito del sistema y dominio de negocio
- Stack tecnológico (lenguajes, frameworks, BD, runtime)
- Repositorio y estructura de carpetas de primer nivel

### 2. Arquitectura de la solución
- Capas principales (presentación, negocio, datos) y sus responsabilidades
- Proyectos / assemblies principales y sus dependencias
- Patrones de diseño predominantes (DAL, Repository, Service, etc.)

### 3. Módulos y subsistemas clave
Para cada módulo relevante:
- Nombre y propósito
- Archivos / clases principales
- Tablas Oracle que gestiona
- Dependencias entre módulos

### 4. Convenciones del proyecto
- Nomenclatura de clases, métodos, variables
- Cómo se usa RIDIOMA (mensajes al usuario)
- Patrón DAL Oracle: cómo se arman queries, stored procedures, transacciones
- Manejo de errores y logging estándar
- Estructura de un formulario típico (Frm*)

### 5. Base de datos Oracle
- Esquemas principales y tablas más importantes
- Convenciones de nombres de tablas y columnas
- Cómo conecta la app a Oracle (connection string, pool, etc.)
- Stored procedures más usados

### 6. Puntos de entrada y flujos típicos
- Cómo arranca la aplicación
- Flujo típico de un proceso de negocio end-to-end
- Batch jobs / procesos schedulados si los hay

### 7. Guía para resolver tickets
- Checklist que debe seguir el agente PM al analizar un bug
- Checklist que debe seguir el agente Dev al implementar
- Checklist que debe seguir el agente QA al testear
- Dónde buscar primero según el tipo de problema (UI, BD, proceso batch, etc.)

### 8. Archivos de referencia críticos
Lista de los archivos más importantes con una línea de descripción cada uno.
(máx 40 archivos, priorizá los que se tocan en la mayoría de los tickets)

---

## Instrucciones de trabajo

1. Explorá la estructura de carpetas de `{workspace_root}` para entender la organización
2. Leé los archivos de configuración (*.config, appsettings.*, *.csproj) para entender el stack
3. Examiná las clases base y los helpers más referenciados en el código
4. Revisá las tablas Oracle que aparecen con más frecuencia en las queries
5. Identificá los patrones repetidos para documentar las convenciones reales (no supuestas)
6. Escribí PROJECT_DOCS.md en `{docs_output_path}` con la estructura indicada arriba
7. El documento debe tener entre 500 y 1500 líneas — suficiente detalle para ser útil,
   suficientemente conciso para que un agente lo lea completo sin saturarse

**Al terminar:** confirmá con el mensaje "PROJECT_DOCS.md generado correctamente en {docs_output_path}"
"""
