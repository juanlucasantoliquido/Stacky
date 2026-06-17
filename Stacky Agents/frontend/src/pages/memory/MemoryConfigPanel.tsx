import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HarnessFlags, Memory, type HarnessFlagView } from "../../api/endpoints";
import styles from "./MemoryConfigPanel.module.css";

// Plan 26 M0.2 + M3.1 + M3.2 — gobierno de la memoria desde su propia página:
// toggle master, allowlist por proyecto, caps por agente, scopes inyectables,
// preview "qué se inyectaría" y panel de salud de directivas. Reusa el registry
// de flags (fuente única) — no crea endpoints de flags nuevos.

const FLAG = {
  master: "STACKY_MEMORY_INJECTION_ENABLED",
  projects: "STACKY_MEMORY_INJECTION_PROJECTS",
  caps: "STACKY_MEMORY_CAPS_JSON",
  scopes: "STACKY_MEMORY_INJECT_SCOPES",
};

const ALL_SCOPES = ["project", "team", "global", "personal"];

function flagValue(flags: HarnessFlagView[] | undefined, key: string): HarnessFlagView | undefined {
  return flags?.find((f) => f.key === key);
}

export default function MemoryConfigPanel({ project }: { project: string }) {
  const qc = useQueryClient();
  const flagsQuery = useQuery({ queryKey: ["harness-flags"], queryFn: () => HarnessFlags.list() });
  const typesQuery = useQuery({ queryKey: ["memory-types"], queryFn: () => Memory.types() });
  const flags = flagsQuery.data?.flags;
  const flagsMissing = flagsQuery.isError || (flagsQuery.data && !flagValue(flags, FLAG.master));

  const update = useMutation({
    mutationFn: (updates: Record<string, boolean | number | string>) => HarnessFlags.update(updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["harness-flags"] }),
  });

  // ── master + allowlist ────────────────────────────────────────────────────
  const masterOn = Boolean(flagValue(flags, FLAG.master)?.value);
  const [allowlist, setAllowlist] = useState("");
  useEffect(() => {
    const v = flagValue(flags, FLAG.projects)?.value;
    if (typeof v === "string") setAllowlist(v);
  }, [flags]);

  // ── caps por agente (JSON) ──────────────────────────────────────────────────
  const [capsText, setCapsText] = useState("");
  useEffect(() => {
    const v = flagValue(flags, FLAG.caps)?.value;
    if (typeof v === "string") setCapsText(v);
  }, [flags]);
  const capsValid = useMemo(() => {
    if (!capsText.trim()) return true;
    try {
      JSON.parse(capsText);
      return true;
    } catch {
      return false;
    }
  }, [capsText]);

  // ── scopes inyectables ──────────────────────────────────────────────────────
  const scopesValue = String(flagValue(flags, FLAG.scopes)?.value ?? "project,team,global");
  const activeScopes = new Set(
    scopesValue
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
  );
  const toggleScope = (s: string) => {
    const next = new Set(activeScopes);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    update.mutate({ [FLAG.scopes]: Array.from(next).join(",") });
  };

  // ── preview "qué se inyectaría" ─────────────────────────────────────────────
  const [agentType, setAgentType] = useState("developer");
  const [query, setQuery] = useState("");
  const preview = useQuery({
    queryKey: ["memory-context-preview", project, agentType, query],
    queryFn: () => Memory.contextPreview({ project, agent_type: agentType, q: query || null }),
    enabled: false,
  });

  // ── salud de directivas ─────────────────────────────────────────────────────
  const health = useQuery({
    queryKey: ["directive-health", project],
    queryFn: () => Memory.directiveHealth(project),
    enabled: !!project,
  });

  if (flagsMissing) {
    return (
      <div className={styles.empty}>
        No se pudieron leer los flags del arnés. El panel queda en modo lectura.
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      {/* M0.2 — Inyección */}
      <section className={styles.card}>
        <h3>Inyección de memoria</h3>
        <label className={styles.toggleRow}>
          <input
            type="checkbox"
            checked={masterOn}
            onChange={(e) => update.mutate({ [FLAG.master]: e.target.checked })}
            disabled={update.isPending}
          />
          <span>Inyección habilitada (master)</span>
          <em className={masterOn ? styles.on : styles.off}>{masterOn ? "ON" : "OFF"}</em>
        </label>

        <label className={styles.field}>
          <span>Allowlist de proyectos (CSV; vacío = todos)</span>
          <div className={styles.inlineRow}>
            <input value={allowlist} onChange={(e) => setAllowlist(e.target.value)} placeholder="Proj_A, Proj_B" />
            <button
              onClick={() => update.mutate({ [FLAG.projects]: allowlist })}
              disabled={update.isPending}
            >
              Guardar
            </button>
          </div>
        </label>
      </section>

      {/* M0.1/M0.2 — Caps por agente */}
      <section className={styles.card}>
        <h3>Caps por agente (JSON)</h3>
        <p className={styles.hint}>
          Shape: <code>{`{"developer": [16, 16000], "qa": [8, 8000]}`}</code>. Vacío = defaults del código.
        </p>
        <textarea
          className={capsValid ? "" : styles.invalid}
          rows={4}
          value={capsText}
          onChange={(e) => setCapsText(e.target.value)}
        />
        <div className={styles.inlineRow}>
          <button
            onClick={() => update.mutate({ [FLAG.caps]: capsText })}
            disabled={!capsValid || update.isPending}
          >
            Guardar caps
          </button>
          {!capsValid && <span className={styles.warn}>JSON inválido</span>}
        </div>
      </section>

      {/* M3.1 — Scopes inyectables + types */}
      <section className={styles.card}>
        <h3>Scopes inyectables</h3>
        <div className={styles.scopeRow}>
          {ALL_SCOPES.map((s) => (
            <label key={s} className={styles.scopeChip}>
              <input
                type="checkbox"
                checked={activeScopes.has(s)}
                onChange={() => toggleScope(s)}
                disabled={update.isPending}
              />
              {s}
            </label>
          ))}
        </div>
        <h4>Tipos de memoria</h4>
        <div className={styles.typeList}>
          <div>
            <strong>Injectables (canal USER):</strong> {(typesQuery.data?.injectable ?? []).join(", ") || "—"}
          </div>
          <div className={styles.reserved}>
            <strong>Reservados (B5/SYSTEM):</strong> {(typesQuery.data?.reserved ?? []).join(", ") || "—"}
          </div>
        </div>
      </section>

      {/* M0.2 — Preview "qué se inyectaría" */}
      <section className={styles.card}>
        <h3>¿Qué se inyectaría?</h3>
        <div className={styles.inlineRow}>
          <input value={agentType} onChange={(e) => setAgentType(e.target.value)} placeholder="agent_type" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="texto del ticket (opcional)"
          />
          <button onClick={() => preview.refetch()} disabled={preview.isFetching}>
            {preview.isFetching ? "…" : "Probar"}
          </button>
        </div>
        {!masterOn && <p className={styles.warn}>Inyección apagada — el preview puede venir vacío.</p>}
        {preview.data && (
          <div className={styles.previewBox}>
            <div className={styles.previewMeta}>
              <span>chars: {preview.data.content?.length ?? 0}</span>
              <span>hits: {preview.data.hits}</span>
              <span>activas: {preview.data.active_hits ?? 0}</span>
              <span>suprimidas: {preview.data.suppressed_hits ?? 0}</span>
              <span>directivas: {preview.data.directive_hits ?? 0}</span>
            </div>
            {preview.data.directives_crowded_out_observations && (
              <p className={styles.warn}>Las directivas consumieron todo el presupuesto (cap muy chico).</p>
            )}
            <pre className={styles.previewContent}>{preview.data.content || "(bloque vacío)"}</pre>
          </div>
        )}
      </section>

      {/* M3.2 — Salud de directivas */}
      <section className={styles.card}>
        <h3>Salud de directivas</h3>
        {health.isLoading && <div className={styles.empty}>Cargando…</div>}
        {health.data && (
          <div className={styles.healthGrid}>
            <div>
              <h4>Solapamientos ({health.data.overlapping.length})</h4>
              {health.data.overlapping.length === 0 && <p className={styles.ok}>Sin solapamientos.</p>}
              {health.data.overlapping.map((o, i) => (
                <p key={i} className={styles.healthItem}>
                  {o.ids.join(" ↔ ")} — {JSON.stringify(o.shared_targeting)}
                </p>
              ))}
            </div>
            <div>
              <h4>Presión de presupuesto</h4>
              {health.data.budget_pressure.length === 0 && <p className={styles.ok}>Sin directivas.</p>}
              {health.data.budget_pressure.map((b, i) => (
                <p key={i} className={b.ratio > 0.8 ? styles.warn : styles.healthItem}>
                  {b.agent_type}: {b.directive_chars}/{b.cap} ({Math.round(b.ratio * 100)}%)
                </p>
              ))}
            </div>
            <div>
              <h4>Obsoletas ({health.data.stale.length})</h4>
              {health.data.stale.length === 0 && <p className={styles.ok}>Ninguna vencida.</p>}
              {health.data.stale.map((s) => (
                <p key={s.id} className={styles.warn}>
                  {s.id} — review: {s.review_after ?? "—"} / expira: {s.expires_at ?? "—"}
                </p>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
