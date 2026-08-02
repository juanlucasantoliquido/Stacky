"""Plan 287 F1.5 — formas REALES de fetch_item_updates, copiadas de los tests que
los propios adaptadores ya tienen. Sirven de contrato: si un adaptador cambia su
forma, este archivo tiene que cambiar en el mismo commit y el cambio se ve en el diff.

Verificado abriendo los adaptadores el 2026-08-02:
  · ADO   — services/ado_provider.py:137 devuelve tal cual el `data["value"]` de
            /_apis/wit/workitems/<id>/updates (services/ado_client.py:957-972).
            Claves: id, rev, revisedBy{displayName}, revisedDate, fields{...}.
  · GitLab— services/gitlab_provider.py:606-666 arma el dict el mismo adaptador.
            Claves: kind, created_at, user (YA es el username, string, :622),
            label{name}, action, state, body, raw.

La interseccion de claves entre los dos es VACIA. Por eso el normalizador de F1
recibe el tracker y no una forma sola.
"""

UPDATES_ADO = [
    {"rev": 2, "revisedDate": "2026-06-01T10:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"},
     "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}}},
    {"rev": 3, "revisedDate": "2026-06-02T11:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"},
     "fields": {"Microsoft.VSTS.Common.Priority": {"oldValue": 3, "newValue": 1}}},
    {"rev": 4, "revisedDate": "2026-06-03T12:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"}, "fields": {}},   # revision sin campos visibles
]

UPDATES_GITLAB = [
    {"kind": "state_event", "created_at": "2026-06-14T09:00:00",
     "state": "closed", "user": "dev", "raw": {}},
    {"kind": "label_event", "created_at": "2026-06-15T10:00:00",
     "action": "add", "label": {"name": "bug"}, "user": "dev", "raw": {}},
    {"kind": "system_note", "created_at": "2026-06-16T08:00:00",
     "body": "changed the description", "user": "dev", "raw": {}},
]

UPDATES_POR_TRACKER = {
    "azure_devops": UPDATES_ADO,
    "gitlab": UPDATES_GITLAB,
}
