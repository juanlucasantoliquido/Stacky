"""Plan 123 F1 — motor puro de diff de esquemas (SchemaDiff v1).

Función pura y determinista: sin red, disco ni config. Entra JSON (snapshots v1 del
Plan 122, contrato `Stacky Agents/docs/122_PLAN_*.md` §F3), sale JSON (SchemaDiff v1,
contrato congelado en `Stacky Agents/docs/123_PLAN_*.md` §F1). Toda la lógica es
testeable sin BD (ver tests/test_plan123_dbcompare_diff.py).

Semántica de dirección (congelada para la serie 122-126): el ORIGEN es la referencia
(source of truth); el DESTINO es el ambiente a alinear. `added` = existe en origen y
falta en destino (la paridad lo CREARÁ en destino); `removed` = existe en destino y no
en origen (la paridad lo DROPEARÁ del destino).
"""
from __future__ import annotations

import re

DIFF_VERSION = 1
SEVERITIES = ("info", "warn", "danger")

_SEVERITY_RANK = {"info": 0, "warn": 1, "danger": 2}


class DbCompareDiffError(RuntimeError):
    """El diff no puede calcularse (p.ej. los ambientes tienen motores distintos)."""


# Tabla CERRADA de kinds y severidades (doc 123 §F1). kind desconocido -> "warn".
_KIND_SEVERITY = {
    "table_added": "warn",
    "table_removed": "danger",
    "column_added": "warn",
    "column_removed": "danger",
    "column_type_changed": "danger",
    "column_nullable_relaxed": "warn",
    "column_nullable_tightened": "danger",
    "column_default_changed": "info",
    "column_autoincrement_changed": "warn",
    "pk_changed": "danger",
    "fk_added": "warn",
    "fk_removed": "warn",
    "index_added": "warn",
    "index_removed": "warn",
    "unique_added": "warn",
    "unique_removed": "warn",
    "check_added": "warn",
    "check_removed": "warn",
    "view_added": "warn",
    "view_removed": "warn",
    "view_definition_changed": "warn",
    "sequence_added": "info",
    "sequence_removed": "warn",
}


def classify_severity(kind: str) -> str:
    return _KIND_SEVERITY.get(kind, "warn")


# --------------------------------------------------------------------------
# Normalización (doctrina de campo: Compare-DevTestDatabase.ps1, doc 122 §2-bis)
# --------------------------------------------------------------------------

def _parens_balanced(s: str) -> bool:
    """El '(' en posición 0 cierra exactamente con el ')' en la última posición."""
    if not s or s[0] != "(" or s[-1] != ")":
        return False
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def _normalize_default(s):
    """[FIX C1] bucle explícito: SQL Server envuelve defaults en capas de paréntesis
    (`((0))` vs `(0)`) y una sola pasada no las despoja del todo."""
    if s is None:
        return None
    s = s.strip()
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")" and _parens_balanced(s):
        s = s[1:-1].strip()
    return s


def _normalize_default_v2(s):
    """Plan 179 F1 (v2, fix C2) — normalización ENDURECIDA de defaults para modo v2.
    Reglas EXACTAS, en orden:
      1. None -> None.
      2. Strip de capas de paréntesis externos balanceados (reusa _normalize_default,
         que ya mata `((0))` vs `(0)` — fix C1 del plan 123, intacto).
      3. GUARDIA DE LITERALES (fix C2): si el resultado contiene comilla simple (')
         hay un literal de string y CUALQUIER normalización interna podría cambiar
         su semántica ('a, b' != 'a,b'; 'ABC' != 'Abc'; 'A  B' != 'A B') — se
         retorna el resultado del paso 2 SIN más cambios (conservador total).
         Limitación conocida y aceptada (C10): si el default mezcla función y
         literal (CONVERT(varchar,'x') vs convert(VARCHAR,'x')), el case de la
         parte función tampoco se foldea — falso positivo residual deliberado.
      4. Colapsar todo whitespace a UN espacio + strip.
      5. Eliminar espacios adyacentes a '(' , ')' y ',' — `CONVERT(bit, 0)` == `CONVERT(bit,0)`.
      6. Case-folding: se retorna .upper() (acá ya no hay literales, por el paso 3).
    """
    s = _normalize_default(s)
    if s is None:
        return None
    if "'" in s:
        return s
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*([(),])\s*", r"\1", s)
    return s.upper()


def _normalize_check(s):
    """upper + colapsar espacios múltiples a uno + strip de una capa de paréntesis
    exteriores balanceados."""
    if s is None:
        return ""
    s = s.upper()
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) >= 2 and s[0] == "(" and s[-1] == ")" and _parens_balanced(s):
        s = s[1:-1].strip()
    return s


# --------------------------------------------------------------------------
# Construcción de changes/items
# --------------------------------------------------------------------------

def _change(kind, detail):
    return {"kind": kind, "severity": classify_severity(kind), "detail": detail}


# Plan 179 §4 (fix C3) — clasificación de subcampos de type_detail para el modo v2:
#  ESTRUCTURALES: `null` vs valor SÍ cuenta (una identity/precision que aparece ES drift).
#  SENSIBLES A REFLEXIÓN: comparan SOLO si ambos lados son non-null (asimetría de
#  permisos de catálogo / versión de driver / dialecto NO es drift confiable).
_STRUCTURAL_DETAIL_FIELDS = ("base", "precision", "scale", "length", "identity", "computed")
_REFLECTION_SENSITIVE_FIELDS = ("collation", "timezone")


def _all_optional_null(td: dict) -> bool:
    return all(td.get(k) is None for k in ("precision", "scale", "length", "collation", "timezone", "identity", "computed"))


def _diff_columns(s_cols, t_cols, v2_mode: bool = False):
    changes = []
    s_by_name = {c["name"]: c for c in s_cols}
    t_by_name = {c["name"]: c for c in t_cols}
    for name in sorted(set(s_by_name) | set(t_by_name)):
        sc = s_by_name.get(name)
        tc = t_by_name.get(name)
        if sc is None:
            changes.append(_change("column_added", {"column": name, "source": None, "target": tc}))
            continue
        if tc is None:
            changes.append(_change("column_removed", {"column": name, "source": sc, "target": None}))
            continue
        # Tipo — Plan 179 F3: en modo v2 (ambos snapshots v2) el criterio es ESTRUCTURAL
        # (type_detail), no el render del string. `changed_fields` es una clave ADITIVA
        # del detail: lista ordenada y cerrada de subcampos que difieren; `["type"]` es
        # la red de seguridad para tipos opacos sin atributos en ambos lados.
        s_td, t_td = sc.get("type_detail"), tc.get("type_detail")
        if v2_mode and isinstance(s_td, dict) and isinstance(t_td, dict):
            changed_fields = [k for k in _STRUCTURAL_DETAIL_FIELDS if s_td.get(k) != t_td.get(k)]
            changed_fields += [
                k for k in _REFLECTION_SENSITIVE_FIELDS
                if s_td.get(k) is not None and t_td.get(k) is not None and s_td.get(k) != t_td.get(k)
            ]
            if not changed_fields and _all_optional_null(s_td) and _all_optional_null(t_td) and str(sc.get("type")) != str(tc.get("type")):
                changed_fields = ["type"]
            if changed_fields:
                changes.append(_change("column_type_changed", {
                    "column": name, "source": sc, "target": tc, "changed_fields": changed_fields,
                }))
        elif str(sc.get("type")) != str(tc.get("type")):
            changes.append(_change("column_type_changed", {"column": name, "source": sc, "target": tc}))
        s_null, t_null = bool(sc.get("nullable")), bool(tc.get("nullable"))
        if s_null and not t_null:
            changes.append(_change("column_nullable_relaxed", {"column": name, "source": sc, "target": tc}))
        elif not s_null and t_null:
            changes.append(_change("column_nullable_tightened", {"column": name, "source": sc, "target": tc}))
        norm = _normalize_default_v2 if v2_mode else _normalize_default
        if norm(sc.get("default")) != norm(tc.get("default")):
            changes.append(_change("column_default_changed", {"column": name, "source": sc, "target": tc}))
        if bool(sc.get("autoincrement")) != bool(tc.get("autoincrement")):
            changes.append(_change("column_autoincrement_changed", {"column": name, "source": sc, "target": tc}))
    return changes


def _diff_pk(s_pk, t_pk):
    s_cols = list(s_pk.get("columns") or [])
    t_cols = list(t_pk.get("columns") or [])
    if s_cols != t_cols:
        return [_change("pk_changed", {"source": s_cols, "target": t_cols})]
    return []


def _diff_by_signature(s_items, t_items, sig_fn, added_kind, removed_kind):
    """Matchea por FIRMA ESTRUCTURAL, nunca por nombre (doctrina de campo, doc 122 §2-bis).
    Los nombres de ambos lados quedan en detail (name_source/name_target) solo informativos.
    """
    s_by_sig = {sig_fn(it): it for it in s_items}
    t_by_sig = {sig_fn(it): it for it in t_items}
    changes = []
    for sig in sorted(set(s_by_sig) - set(t_by_sig), key=str):
        it = s_by_sig[sig]
        changes.append(_change(added_kind, {
            "name_source": it.get("name"), "name_target": None,
            "source": it, "target": None,
        }))
    for sig in sorted(set(t_by_sig) - set(s_by_sig), key=str):
        it = t_by_sig[sig]
        changes.append(_change(removed_kind, {
            "name_source": None, "name_target": it.get("name"),
            "source": None, "target": it,
        }))
    return changes


def _fk_signature(fk):
    return (
        tuple(fk.get("columns") or []),
        fk.get("referred_schema"),
        fk.get("referred_table"),
        tuple(fk.get("referred_columns") or []),
    )


def _diff_fks(s_fk, t_fk):
    return _diff_by_signature(s_fk, t_fk, _fk_signature, "fk_added", "fk_removed")


def _diff_indexes(s_idx, t_idx):
    def sig(idx):
        return (bool(idx.get("unique")), tuple(idx.get("columns") or []))
    return _diff_by_signature(s_idx, t_idx, sig, "index_added", "index_removed")


def _diff_uniques(s_uq, t_uq):
    def sig(uq):
        return tuple(uq.get("columns") or [])
    return _diff_by_signature(s_uq, t_uq, sig, "unique_added", "unique_removed")


def _diff_checks(s_ck, t_ck):
    def sig(ck):
        return _normalize_check(ck.get("sqltext"))
    return _diff_by_signature(s_ck, t_ck, sig, "check_added", "check_removed")


def _diff_table(s_table, t_table, v2_mode: bool = False):
    changes = []
    changes += _diff_columns(s_table.get("columns") or [], t_table.get("columns") or [], v2_mode=v2_mode)
    changes += _diff_pk(s_table.get("primary_key") or {}, t_table.get("primary_key") or {})
    changes += _diff_fks(s_table.get("foreign_keys") or [], t_table.get("foreign_keys") or [])
    changes += _diff_indexes(s_table.get("indexes") or [], t_table.get("indexes") or [])
    changes += _diff_uniques(s_table.get("unique_constraints") or [], t_table.get("unique_constraints") or [])
    changes += _diff_checks(s_table.get("check_constraints") or [], t_table.get("check_constraints") or [])
    changes.sort(key=lambda c: c["kind"])
    return changes


def _diff_view(s_view, t_view):
    s_sha = s_view.get("definition_sha256")
    t_sha = t_view.get("definition_sha256")
    if s_sha is None or t_sha is None:
        # No se puede confirmar igualdad si algún lado no pudo leerse (permisos, etc.):
        # nunca asumir "sin cambios" en silencio.
        return [_change("view_definition_changed", {
            "source_sha256": s_sha, "target_sha256": t_sha, "unverifiable": True,
        })]
    if s_sha != t_sha:
        return [_change("view_definition_changed", {
            "source_sha256": s_sha, "target_sha256": t_sha,
        })]
    return []


def _item_severity(changes):
    if not changes:
        return "info"
    return max((c["severity"] for c in changes), key=lambda sev: _SEVERITY_RANK[sev])


def _item(object_type, schema, name, action, changes=None):
    changes = changes or []
    if changes:
        severity = _item_severity(changes)
    else:
        severity = classify_severity(f"{object_type}_{action}")
    return {
        "object_type": object_type,
        "schema": schema,
        "name": name,
        "action": action,
        "severity": severity,
        "changes": changes,
    }


def _walk_object_type(object_type, schema, s_objs, t_objs, items, diff_fn):
    names = sorted(set(s_objs) | set(t_objs))
    unchanged = 0
    for name in names:
        if name not in t_objs:
            items.append(_item(object_type, schema, name, "added"))
        elif name not in s_objs:
            items.append(_item(object_type, schema, name, "removed"))
        else:
            changes = diff_fn(s_objs[name], t_objs[name]) if diff_fn else []
            if changes:
                items.append(_item(object_type, schema, name, "changed", changes))
            else:
                unchanged += 1
    return unchanged


def summarize(items: list, objects_total: int, objects_unchanged: int) -> dict:
    by_severity = {"info": 0, "warn": 0, "danger": 0}
    by_action = {"added": 0, "removed": 0, "changed": 0}
    by_object_type = {"table": 0, "view": 0, "sequence": 0}
    for it in items:
        by_severity[it["severity"]] += 1
        by_action[it["action"]] += 1
        by_object_type[it["object_type"]] += 1
    parity_score = 100.0 if objects_total == 0 else round(100.0 * objects_unchanged / objects_total, 1)
    return {
        "by_severity": by_severity,
        "by_action": by_action,
        "by_object_type": by_object_type,
        "objects_total": objects_total,
        "objects_unchanged": objects_unchanged,
        "parity_score": parity_score,
    }


def diff_snapshots(source: dict, target: dict) -> dict:
    if source.get("engine") != target.get("engine"):
        raise DbCompareDiffError(
            f"Los ambientes tienen motores distintos: {source.get('engine')} vs {target.get('engine')}."
        )

    items: list = []
    objects_unchanged = 0

    # Plan 179 F3 — modo v2 PASIVO por versión: las reglas v2 (type_detail + defaults
    # endurecidos) se activan SOLO cuando AMBOS snapshots son v2. En cualquier otro
    # caso (v1/v1, v1/v2, v2/v1) el diff es byte-idéntico a main. No hay flag propia:
    # la pasividad es por construcción (§3.2 del plan).
    v2_mode = int(source.get("version") or 1) >= 2 and int(target.get("version") or 1) >= 2

    s_schemas = source.get("schemas") or {}
    t_schemas = target.get("schemas") or {}

    for schema in sorted(set(s_schemas) | set(t_schemas)):
        s_schema = s_schemas.get(schema) or {}
        t_schema = t_schemas.get(schema) or {}

        s_tables = s_schema.get("tables") or {}
        t_tables = t_schema.get("tables") or {}
        objects_unchanged += _walk_object_type(
            "table", schema, s_tables, t_tables, items,
            lambda s, t: _diff_table(s, t, v2_mode=v2_mode),
        )

        s_views = s_schema.get("views") or {}
        t_views = t_schema.get("views") or {}
        objects_unchanged += _walk_object_type("view", schema, s_views, t_views, items, _diff_view)

        s_seqs = s_schema.get("sequences") or []
        t_seqs = t_schema.get("sequences") or []
        objects_unchanged += _walk_object_type("sequence", schema, s_seqs, t_seqs, items, None)

    items.sort(key=lambda it: (it["object_type"], it["schema"], it["name"]))
    objects_total = len(items) + objects_unchanged

    summary = summarize(items, objects_total, objects_unchanged)

    return {
        "version": DIFF_VERSION,
        "engine": source.get("engine"),
        "source": {
            "alias": source.get("alias"),
            "snapshot_id": source.get("id"),
            "content_hash": source.get("content_hash"),
        },
        "target": {
            "alias": target.get("alias"),
            "snapshot_id": target.get("id"),
            "content_hash": target.get("content_hash"),
        },
        "items": items,
        "summary": summary,
    }
