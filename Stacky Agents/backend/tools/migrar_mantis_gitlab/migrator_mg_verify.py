"""tools/migrar_mantis_gitlab/migrator_mg_verify.py — Plan 217 F7a (§8.2).

`verify_migration` consolida las 5 comprobaciones post-migración del plan
(§8.2.1..§8.2.5) en un único resultado (`MgVerificationResult`) que
`migrator_mg_report.py` (F7b, mismo batch) consume para el reporte final.

Principio rector (§6/§8.2 del plan): esta función **no recalcula** lo que
ya calculó el resto del pipeline (fallbacks de mapeo, usuarios caídos a
`default_fallback`, adjuntos saltados) — eso llega ya resuelto como
parámetros de entrada (`unmapped_events`, `user_fallback_events`,
`attachment_skip_events`) y esta función solo los consolida en el reporte
de verificación. Lo que sí calcula desde cero es: conteo origen vs.
migrado (§8.2.1), markers duplicados (§8.2.2) y el muestreo campo-a-campo
(§8.2.4).

Shapes asumidos (decisión de diseño explícita, documentada porque el plan
no fija un shape exacto para `origin_issues`/`real_items_by_iid` en este
batch):
  - `origin_issues`: `list[dict]` con, como mínimo, `mantis_issue_id`,
    `title`, y los valores YA MAPEADOS que se esperan ver en GitLab:
    `expected_gitlab_state` (el `gitlab_state` que produjo
    `mapping.status_map.map_status`) y `expected_priority_label` (el label
    completo, ej. `"priority::P1-critica"`, que produjo
    `mapping.priority_severity_map.map_priority` — GitLab no tiene un campo
    "priority" propio, se codifica como label, ver
    `services/gitlab_provider.py:69-80` `_normalize_issue`). Aplicar el
    mapeo es responsabilidad de la orquestación (F9, otro batch) — esta
    función NO llama a `status_map`/`priority_severity_map`, solo compara
    lo que ya viene calculado, igual criterio que con los `*_events`.
  - `real_items_by_iid`: `dict[str, dict]` indexado por `iid` (string), con
    el shape real que devuelve `GitLabTrackerProvider._normalize_issue`
    (`title`, `state`, `labels`, ...). En producción se arma UNA vez
    llamando `writer.fetch_open_items()` (`_build_real_items_index`); en
    test se pasa un dict fake directo, sin tocar la red (mandato del
    batch).

NOTA DE IMPRECISIÓN DEL PLAN (documentada, no oculta): el texto del batch
dice "compara ... contra lo que devuelve `writer.effective...`" (oración
incompleta / probable errata — `effective_target()` no devuelve datos de
issues, solo `(base_url, project_path)`, ver `destination_writer.py:116`).
Se interpreta como "contra los datos reales del destino" y se resuelve con
`real_items_by_iid`, tal como el batch pide explícitamente dos líneas más
abajo en su propio texto.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MgVerificationResult:
    total_origin: int = 0
    total_migrated: int = 0
    count_gap: int = 0
    duplicate_markers: list[str] = field(default_factory=list)
    sample_mismatches: list[dict] = field(default_factory=list)
    unmapped_fallbacks_used: list[dict] = field(default_factory=list)
    users_fallback: list[dict] = field(default_factory=list)
    attachments_skipped: list[dict] = field(default_factory=list)
    passed: bool = False


def _build_real_items_index(writer) -> dict[str, dict]:
    """Arma `{iid: item}` con UNA sola llamada a `writer.fetch_open_items()`
    (§8.2.4 del plan: "no hace falta re-consultar por cada muestra")."""
    index: dict[str, dict] = {}
    for item in writer.fetch_open_items():
        iid = str(item.get("iid") or item.get("id") or "")
        if iid:
            index[iid] = item
    return index


def _extract_label_with_prefix(labels: "list[str] | None", prefix: str) -> Optional[str]:
    for label in labels or []:
        if isinstance(label, str) and label.startswith(prefix):
            return label
    return None


def _find_duplicate_markers(mapping_rows: list[dict]) -> list[str]:
    """§8.2.2: agrupa por `gitlab_iid` — si el mismo `gitlab_iid` tiene 2+
    `mantis_issue_id` distintos detrás, es un marker duplicado (bug de
    migración: dos issues Mantis "escribieron" el mismo destino)."""
    by_iid: dict[str, set] = {}
    for row in mapping_rows:
        iid = row.get("gitlab_iid")
        if not iid:
            continue
        by_iid.setdefault(str(iid), set()).add(str(row.get("mantis_issue_id")))

    return [
        f"gitlab_iid={iid} mapeado a mantis_issue_id={sorted(ids)}"
        for iid, ids in sorted(by_iid.items())
        if len(ids) > 1
    ]


def _sample_and_compare(
    mapping_rows: list[dict],
    origin_issues: list[dict],
    real_items_by_iid: dict[str, dict],
    *,
    sample_rate: float,
    sample_min: int,
    total_migrated: int,
    rng_seed: int,
) -> list[dict]:
    """§8.2.4: muestreo determinista (seed fija) de filas `done`, comparación
    campo a campo `title`/`gitlab_state`/`priority` contra los valores
    reales ya indexados."""
    done_rows = [r for r in mapping_rows if r.get("status") == "done" and r.get("gitlab_iid")]
    sample_size = min(max(sample_min, int(total_migrated * sample_rate)), len(done_rows))
    sampled = random.Random(rng_seed).sample(done_rows, sample_size) if sample_size > 0 else []

    origin_by_id = {str(issue.get("mantis_issue_id")): issue for issue in origin_issues}

    mismatches: list[dict] = []
    for row in sampled:
        mantis_id = str(row.get("mantis_issue_id"))
        gitlab_iid = str(row.get("gitlab_iid"))
        origin = origin_by_id.get(mantis_id)
        real = real_items_by_iid.get(gitlab_iid)
        if origin is None or real is None:
            # Sin ambos lados no hay con qué comparar — no se inventa un
            # mismatch fantasma (principio rector §6 del plan).
            continue

        field_diffs: list[dict] = []

        expected_title = origin.get("title")
        actual_title = real.get("title")
        if expected_title != actual_title:
            field_diffs.append({"field": "title", "expected": expected_title, "actual": actual_title})

        expected_state = origin.get("expected_gitlab_state")
        actual_state = real.get("state")
        if expected_state != actual_state:
            field_diffs.append({"field": "gitlab_state", "expected": expected_state, "actual": actual_state})

        expected_priority = origin.get("expected_priority_label")
        actual_priority = _extract_label_with_prefix(real.get("labels"), "priority::")
        if expected_priority != actual_priority:
            field_diffs.append({"field": "priority", "expected": expected_priority, "actual": actual_priority})

        if field_diffs:
            mismatches.append({
                "mantis_issue_id": mantis_id,
                "gitlab_iid": gitlab_iid,
                "mismatches": field_diffs,
            })

    return mismatches


def verify_migration(
    mapping_rows: list[dict],
    origin_issues: list[dict],
    *,
    writer,
    sample_rate: float = 0.1,
    sample_min: int = 20,
    real_items_by_iid: "dict[str, dict] | None" = None,
    unmapped_events: "list[dict] | None" = None,
    user_fallback_events: "list[dict] | None" = None,
    attachment_skip_events: "list[dict] | None" = None,
    rng_seed: int = 42,
) -> MgVerificationResult:
    """Consolida las 5 comprobaciones post-migración (§8.2 del plan).

    `writer` se usa SOLO si `real_items_by_iid` es `None` (producción: se
    llama `writer.fetch_open_items()` una única vez). Los tests pasan
    `real_items_by_iid` directo y `writer` puede quedar en `None` — nunca
    se toca la red en el arnés de tests (mandato del batch).
    """
    total_origin = len(origin_issues)
    total_migrated = len([r for r in mapping_rows if r.get("status") == "done"])
    count_gap = total_origin - total_migrated

    duplicate_markers = _find_duplicate_markers(mapping_rows)

    real_index = real_items_by_iid
    if real_index is None:
        real_index = _build_real_items_index(writer) if writer is not None else {}

    sample_mismatches = _sample_and_compare(
        mapping_rows,
        origin_issues,
        real_index,
        sample_rate=sample_rate,
        sample_min=sample_min,
        total_migrated=total_migrated,
        rng_seed=rng_seed,
    )

    result = MgVerificationResult(
        total_origin=total_origin,
        total_migrated=total_migrated,
        count_gap=count_gap,
        duplicate_markers=duplicate_markers,
        sample_mismatches=sample_mismatches,
        unmapped_fallbacks_used=list(unmapped_events or []),
        users_fallback=list(user_fallback_events or []),
        attachments_skipped=list(attachment_skip_events or []),
    )
    result.passed = count_gap == 0 and not duplicate_markers and not sample_mismatches
    return result


__all__ = ["MgVerificationResult", "verify_migration"]
