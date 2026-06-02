"""Templates default del client_profile por tracker, embebidos como datos Python.

¿Por qué un módulo `.py` y no solo los JSON de `client_profile_defaults/`?
--------------------------------------------------------------------------------
El backend se distribuye **congelado con PyInstaller** (`build_release.ps1`,
`--onedir`). PyInstaller sigue los imports de Python y empaqueta los módulos
`.py`, pero NO empaqueta archivos de datos sueltos (los `*.json` dentro de
`services/client_profile_defaults/`) salvo que se los agregue explícitamente con
`--add-data`. Como no se agregaban, en el deploy congelado
`get_default_client_profile()` no encontraba ningún JSON y devolvía
`{"schema_version": 1}` vacío → el editor mostraba el "template default" vacío,
guardarlo persistía un perfil incompleto, y los proyectos recién creados se
sembraban vacíos (causa raíz de las advertencias "code_layout/language/
tracker_state_machine ausente" y del "client-profile no inyectado").

Embebiendo los templates como dicts en un módulo importado estáticamente desde
`client_profile.py`, PyInstaller los incluye SIEMPRE. Los JSON de
`client_profile_defaults/` se mantienen como mirror legible/editable en dev y
tienen prioridad cuando existen en disco; este módulo es el fallback canónico
cuando no están (deploy congelado). Un test de drift asegura que ambos no
diverjan: `tests/test_client_profile.py::test_embedded_templates_match_json`.
"""

from __future__ import annotations


AZURE_DEVOPS: dict = {
    "schema_version": 1,
    "code_layout": {
        "online_path": "trunk/OnLine",
        "batch_path": "trunk/Batch",
        "db_scripts_path": "trunk/BD/1 - Inicializacion BD",
        "lib_path": "trunk/lib",
        "test_path": "trunk/Tests",
        "file_extensions": {
            "ui": ".aspx",
            "ui_code_behind": ".aspx.cs",
            "code": ".cs",
        },
        "architecture_layers": ["UI", "RSBus (BLL)", "RSDalc (DAL)", "BD"],
    },
    "language": {
        "primary": "csharp",
        "comment_traceability": "// {ticket_token} | {YYYY-MM-DD} | {description}",
        "ticket_token_pattern": "ADO-{id}",
        "languages_in_ridioma": ["ESP", "ENG", "POR"],
    },
    "database": {
        "type": "sqlserver",
        "server": "",
        "readonly_auth_ref": "auth/db_readonly.json",
        "readonly_user_hint": "",
        "connection_kind": "windows_sqlcmd",
        "dml_policy": "prohibited_runtime_must_emit_sql",
        "catalog_master_files": {},
        "naming_conventions": {
            "table_prefix": "R",
            "column_prefix_len": 2,
        },
    },
    "build": {
        "tool": "msbuild",
        "msbuild_path": "C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe",
        "configuration": "Release",
        "online_solutions": [],
        "batch_proj_glob": "Batch/*/*.csproj",
    },
    "conventions": {
        "ridioma_helper": "RSFac.Idioma",
        "ridioma_message_const": "coMens.m{id}",
        "string_sanitizer": "cFormat.StToBD()",
        "error_helpers": ["Error.Agregar", "msgd.Show"],
    },
    "docs_indexes": {
        "technical_master": "trunk/docs/agentic_manual/tecnica/00_INDICE_MAESTRO.md",
        "functional_online": "trunk/docs/agentic_manual/funcional/ONLINE/INDEX.md",
        "functional_batch": "trunk/docs/agentic_manual/funcional/BATCH/00_INDICE_FUNCIONAL_BATCH.md",
    },
    "tracker_state_machine": {
        "functional": {
            "input_states": ["To Do", "New", "Active"],
            "blocked_state": "Blocked",
            "next_state_ok": "Technical review",
        },
        "technical": {
            "input_states": ["Technical review"],
            "blocked_state": "Blocked",
            "next_state_ok": "To Do",
        },
        "developer": {
            "input_states": ["To Do"],
            "in_progress": "Doing",
            "blocked_state": "Blocked",
            "next_state_ok": "Reviewed by Dev",
        },
    },
    "terminology": {
        "product_name": "",
        "client_label": "",
        "domain_glossary_ref": "",
    },
    "extensions": {},
}


JIRA: dict = {
    "schema_version": 1,
    "code_layout": {
        "online_path": "src/web",
        "batch_path": "src/batch",
        "db_scripts_path": "db/migrations",
        "lib_path": "src/lib",
        "test_path": "src/test",
        "file_extensions": {
            "ui": "",
            "ui_code_behind": "",
            "code": "",
        },
        "architecture_layers": ["UI", "Service", "Repository", "DB"],
    },
    "language": {
        "primary": "",
        "comment_traceability": "// {ticket_token} | {YYYY-MM-DD} | {description}",
        "ticket_token_pattern": "{key}-{id}",
        "languages_in_ridioma": ["ESP"],
    },
    "database": {
        "type": "postgres",
        "server": "",
        "readonly_auth_ref": "auth/db_readonly.json",
        "readonly_user_hint": "",
        "connection_kind": "psql",
        "dml_policy": "prohibited_runtime_must_emit_sql",
        "catalog_master_files": {},
        "naming_conventions": {
            "table_prefix": "",
            "column_prefix_len": 0,
        },
    },
    "build": {
        "tool": "maven",
        "command": "mvn -DskipTests=false clean verify",
        "configuration": "Release",
        "online_solutions": [],
    },
    "conventions": {
        "ridioma_helper": "",
        "ridioma_message_const": "",
        "string_sanitizer": "",
        "error_helpers": [],
    },
    "docs_indexes": {
        "technical_master": "docs/tech/INDEX.md",
        "functional_online": "docs/functional/INDEX.md",
        "functional_batch": "",
    },
    "tracker_state_machine": {
        "functional": {
            "input_states": ["To Do"],
            "blocked_state": "Blocked",
            "next_state_ok": "In Progress",
        },
        "technical": {
            "input_states": ["In Progress"],
            "blocked_state": "Blocked",
            "next_state_ok": "Ready for Dev",
        },
        "developer": {
            "input_states": ["Ready for Dev"],
            "in_progress": "Doing",
            "blocked_state": "Blocked",
            "next_state_ok": "Code Review",
        },
    },
    "terminology": {
        "product_name": "",
        "client_label": "",
        "domain_glossary_ref": "",
    },
    "extensions": {},
}


MANTIS: dict = {
    "schema_version": 1,
    "code_layout": {
        "online_path": "src",
        "batch_path": "scripts",
        "db_scripts_path": "db",
        "lib_path": "lib",
        "test_path": "tests",
        "file_extensions": {
            "ui": "",
            "ui_code_behind": "",
            "code": "",
        },
        "architecture_layers": ["UI", "Service", "DB"],
    },
    "language": {
        "primary": "",
        "comment_traceability": "// {ticket_token} | {YYYY-MM-DD} | {description}",
        "ticket_token_pattern": "MANTIS-{id}",
        "languages_in_ridioma": ["ESP"],
    },
    "database": {
        "type": "mysql",
        "server": "",
        "readonly_auth_ref": "auth/db_readonly.json",
        "readonly_user_hint": "",
        "connection_kind": "mysql_cli",
        "dml_policy": "prohibited_runtime_must_emit_sql",
        "catalog_master_files": {},
        "naming_conventions": {
            "table_prefix": "",
            "column_prefix_len": 0,
        },
    },
    "build": {
        "tool": "",
        "command": "",
        "configuration": "Release",
        "online_solutions": [],
    },
    "conventions": {
        "ridioma_helper": "",
        "ridioma_message_const": "",
        "string_sanitizer": "",
        "error_helpers": [],
    },
    "docs_indexes": {
        "technical_master": "docs/tech/INDEX.md",
        "functional_online": "docs/functional/INDEX.md",
        "functional_batch": "",
    },
    "tracker_state_machine": {
        "functional": {
            "input_states": ["new", "acknowledged"],
            "blocked_state": "feedback",
            "next_state_ok": "confirmed",
        },
        "technical": {
            "input_states": ["confirmed"],
            "blocked_state": "feedback",
            "next_state_ok": "assigned",
        },
        "developer": {
            "input_states": ["assigned"],
            "in_progress": "assigned",
            "blocked_state": "feedback",
            "next_state_ok": "resolved",
        },
    },
    "terminology": {
        "product_name": "",
        "client_label": "",
        "domain_glossary_ref": "",
    },
    "extensions": {},
}


# Mapa tracker → template. La clave debe coincidir con el nombre del JSON
# (`{tracker}.json`) para que el test de drift los compare 1:1.
DEFAULT_TEMPLATES: dict[str, dict] = {
    "azure_devops": AZURE_DEVOPS,
    "jira": JIRA,
    "mantis": MANTIS,
}
