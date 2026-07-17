/**
 * Plan 161 F0 — Módulo canónico ÚNICO de formateo humano del frontend.
 * Funciones PURAS y deterministas (sin React, sin fetch, sin Date.now implícito
 * en firmas testeables, sin APIs de locale del navegador). Este archivo y su
 * test son los ÚNICOS autorizados por formatDebtRatchet a usar métodos
 * nativos de formateo; el resto del código importa de acá.
 * Reglas congeladas en docs/161_PLAN_FORMATO_HUMANO_CONSISTENTE_*.md §4.F0.
 */
import { formatRelativeTime, MESES_ABREV } from "../utils/formatRelativeTime";

export type FormatTz = "local" | "utc";

export { formatRelativeTime }; // 1 (re-export, reglas ya congeladas allá)

const pad2 = (n: number) => String(n).padStart(2, "0");

function dateParts(
  iso: string | null | undefined,
  tz: FormatTz,
): { y: number; mo: number; day: number; h: number; mi: number; s: number } | null {
  if (!iso) return null;
  // C2: date-only ("YYYY-MM-DD") parsea como medianoche UTC en JS; en modo local
  // se normaliza a medianoche LOCAL para que la fecha nunca retroceda un día
  // en zonas negativas (AR = UTC-3). En modo utc se deja tal cual (ya es UTC).
  const s = tz === "local" && /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return null;
  return tz === "utc"
    ? { y: d.getUTCFullYear(), mo: d.getUTCMonth(), day: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes(), s: d.getUTCSeconds() }
    : { y: d.getFullYear(), mo: d.getMonth(), day: d.getDate(), h: d.getHours(), mi: d.getMinutes(), s: d.getSeconds() };
}

/**
 * 2) Fecha "{D} {mes} {YYYY}", día sin cero a la izquierda.
 * Nota CONGELADA (C3): el corte absoluto de formatRelativeTime usa getters UTC;
 * formatDate default local usa la zona del operador. Se acepta la divergencia
 * cerca de medianoche; PROHIBIDO "alinear" tocando formatRelativeTime más allá
 * del export de F0.a.
 */
export function formatDate(iso: string | null | undefined, tz: FormatTz = "local"): string {
  const p = dateParts(iso, tz);
  if (!p) return "—";
  return `${p.day} ${MESES_ABREV[p.mo]} ${p.y}`;
}

/** 3) Hora "{HH}:{mm}:{ss}" 24h. */
export function formatTime(iso: string | null | undefined, tz: FormatTz = "local"): string {
  const p = dateParts(iso, tz);
  if (!p) return "—";
  return `${pad2(p.h)}:${pad2(p.mi)}:${pad2(p.s)}`;
}

/** 4) Fecha+hora "{D} {mes} {YYYY} {HH}:{mm}" (sin segundos). */
export function formatDateTime(iso: string | null | undefined, tz: FormatTz = "local"): string {
  const p = dateParts(iso, tz);
  if (!p) return "—";
  return `${p.day} ${MESES_ABREV[p.mo]} ${p.y} ${pad2(p.h)}:${pad2(p.mi)}`;
}

/** 5) Duración. Sin tier de días: las horas crecen sin tope. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const sec = ms / 1000;
  if (Math.round(sec * 10) / 10 < 60) return `${(Math.round(sec * 10) / 10).toFixed(1)}s`;
  const secR = Math.round(sec);
  if (secR < 3600) return `${Math.floor(secR / 60)}m ${secR % 60}s`;
  return `${Math.floor(secR / 3600)}h ${Math.floor((secR % 3600) / 60)}m`;
}

/** 6) Costo USD, escalonado de DOS niveles. */
export function formatCostUsd(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs !== 0 && abs < 0.01) return `${sign}$${abs.toFixed(4)}`;
  return `${sign}$${abs.toFixed(2)}`;
}

/** 7) Tokens compactos. Idéntica a costCenter.logic.ts PARA ENTEROS (C5). */
export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const r = Math.round(n);
  const abs = Math.abs(r);
  if (abs >= 1_000_000) return `${(r / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(r / 1_000).toFixed(1)}k`;
  return String(r);
}

/** 8) Entero exacto con separador de miles "." (estilo es-AR). */
export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const t = Math.trunc(n);
  const sign = t < 0 ? "-" : "";
  return sign + String(Math.abs(t)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** 9) Bytes base 1024, 1 decimal, con espacio antes de la unidad. */
export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n) || n < 0) return "—";
  if (n < 1024) return `${Math.round(n)} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

/** 10) Porcentaje. Recibe escala 0-100. */
export function formatPercent(pct: number | null | undefined, decimals: number = 0): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return "—";
  return `${pct.toFixed(decimals)}%`;
}

/**
 * 11) [ADICIÓN ARQUITECTO] Duración entre dos timestamps, sin resta a mano
 * en cada superficie (hoy hand-rolled en components/devops/deploymentsModel.ts,
 * congelado en baseline como adoptante futuro).
 */
export function formatDurationBetween(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso || !endIso) return "—";
  const a = new Date(startIso).getTime();
  const b = new Date(endIso).getTime();
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return "—";
  return formatDuration(b - a);
}
