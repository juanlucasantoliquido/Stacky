/**
 * Plan 171 F5 — Helpers PUROS de telemetría operativa (sin fetch, sin React).
 *
 * Todo número visible pasa por `format.ts`: `Intl` directo rompe el ratchet de
 * formato del repo.
 */
import type { StatusTone } from "../components/ui";
import type { OpsBreach, RunTrace } from "../lib/opsTelemetryTypes";
import {
  formatCostUsd,
  formatDuration,
  formatInt,
  formatTokens,
} from "./format";

/** Mapa severidad → tono del union real de StatusChip ("danger"/"warning"). */
export function severityTone(sev: "warn" | "critical"): StatusTone {
  return sev === "critical" ? "danger" : "warning";
}

export function breachLabel(b: OpsBreach): string {
  const scope =
    b.agent_type || b.runtime ? `${b.agent_type ?? "—"}/${b.runtime ?? "—"}` : "global";
  return `${b.rule_id} · ${scope} · ${b.message}`;
}

/** Normaliza a porcentaje del máximo. Máximo <= 0 (o lista vacía) → todos 0. */
export function barPercents(values: number[]): number[] {
  if (!values.length) return [];
  const max = Math.max(...values);
  if (!(max > 0)) return values.map(() => 0);
  return values.map((v) => Math.round((v * 100) / max));
}

const DASH = "—";

export function traceRows(t: RunTrace): { label: string; value: string }[] {
  const duracion =
    t.duration_seconds == null ? DASH : formatDuration(t.duration_seconds * 1000);
  const costo =
    t.cost?.cost_usd == null
      ? DASH
      : `${formatCostUsd(t.cost.cost_usd)} (${t.cost.cost_kind})`;
  const tokens =
    t.cost?.tokens_in == null && t.cost?.tokens_out == null
      ? DASH
      : `${formatTokens(t.cost?.tokens_in)} / ${formatTokens(t.cost?.tokens_out)}`;

  return [
    { label: "Estado", value: t.status || DASH },
    { label: "Runtime", value: t.runtime || DASH },
    { label: "Modelo", value: t.model ?? "sin dato" },
    { label: "Duración", value: duracion },
    { label: "Costo", value: costo },
    { label: "Tokens (in/out)", value: tokens },
    { label: "Fuente de telemetría", value: t.telemetry_source || DASH },
    { label: "Sesión", value: t.session_id ?? DASH },
    { label: "Turnos", value: t.num_turns == null ? DASH : formatInt(t.num_turns) },
    {
      label: "Incidente",
      value: t.incident?.id ? `${t.incident.id} — ${t.incident.title ?? ""}`.trim() : DASH,
    },
  ];
}
