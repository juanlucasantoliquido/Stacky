import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import Select from "../ui/Select";
import type { CompareRun, DbEnvironment, SnapshotMeta } from "./dbcompareTypes";
import { selectableTargets, canLaunch } from "./wizardLogic";
import styles from "./dbcompare.module.css";
import { userFacingMessage } from "../../api/gatewayError"; // Plan 273 F4.6

/** Plan 176 F8 — el histórico se suma acá; los dos primeros no cambian. */
const MODES: { value: "fresh" | "cached" | "snapshot"; label: string }[] = [
  { value: "fresh", label: "Fresco (toma snapshots ahora)" },
  { value: "cached", label: "Cacheado (usa el último snapshot)" },
  { value: "snapshot", label: "Histórico (compara dos snapshots ya tomados)" },
];

interface Props {
  environments: DbEnvironment[];
  onLaunched: (run: CompareRun) => void;
  /** Plan 176 F8 — gate del modo histórico (UX v2 del diff). */
  diffUxV2?: boolean;
}

function engineLabel(engine: string): string {
  if (engine === "oracle") return "Oracle";
  if (engine === "sqlite") return "SQLite";
  return "SQL Server";
}

/** 409 = "ya hay una comparación corriendo para este par" (doc 123 §F3, DbCompareBusyError). */
function isBusyError(err: unknown): boolean {
  return err instanceof Error && err.message.startsWith("409");
}

/**
 * Plan 124 F2 — wizard de comparación: elegir origen/destino como cards, modo fresco/cacheado,
 * validación de mismo motor (wizardLogic.ts, ya testeado), y lanzar `DbCompare.compare`.
 */
export function CompareWizard({ environments, onLaunched, diffUxV2 }: Props) {
  const [source, setSource] = useState<DbEnvironment | null>(null);
  const [target, setTarget] = useState<DbEnvironment | null>(null);
  const [mode, setMode] = useState<"fresh" | "cached" | "snapshot">("fresh");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Plan 176 F8 — modo histórico: los snapshots disponibles de cada lado.
  const [sourceSnaps, setSourceSnaps] = useState<SnapshotMeta[]>([]);
  const [targetSnaps, setTargetSnaps] = useState<SnapshotMeta[]>([]);
  const [sourceSnapId, setSourceSnapId] = useState("");
  const [targetSnapId, setTargetSnapId] = useState("");

  useEffect(() => {
    if (mode !== "snapshot") return;
    cargarSnapshots(source?.alias, setSourceSnaps, setSourceSnapId, setError);
    cargarSnapshots(target?.alias, setTargetSnaps, setTargetSnapId, setError);
  }, [mode, source?.alias, target?.alias]);

  const targets = selectableTargets(environments, source);
  const targetByAlias = new Map(targets.map((t) => [t.alias, t]));
  const launch = canLaunch(source, target);

  const selectSource = (env: DbEnvironment) => {
    if (!env.has_password && env.engine !== "sqlite") return;  // Plan 183 §3.2
    setSource(env);
    if (target && (target.alias === env.alias || target.engine !== env.engine)) {
      setTarget(null);
    }
  };

  const selectTarget = (env: DbEnvironment) => {
    const info = targetByAlias.get(env.alias);
    if (!info || !info.enabled) return;
    setTarget(env);
  };

  // En histórico hace falta elegir las dos fotos: con una sola el backend
  // rechaza, y es mejor no dejar apretar el botón que explicar un 400.
  const faltanSnapshots = mode === "snapshot" && (!sourceSnapId || !targetSnapId);

  const handleLaunch = async () => {
    if (!launch.ok || !source || !target || faltanSnapshots) return;
    setLaunching(true);
    setError(null);
    try {
      const res = await DbCompare.compare(
        mode === "snapshot"
          ? {
              source_alias: source.alias,
              target_alias: target.alias,
              source_snapshot_id: sourceSnapId,
              target_snapshot_id: targetSnapId,
            }
          : { source_alias: source.alias, target_alias: target.alias, mode },
      );
      onLaunched(res.run);
    } catch (err) {
      setError(
        isBusyError(err)
          ? "Ya hay una comparación corriendo para este par de ambientes."
          : userFacingMessage(err).title,
      );
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div>
      {error && <div className={styles.errorBanner}>{error}</div>}
      <div className={styles.wizard}>
        <div className={styles.wizardColumn}>
          <h3>Origen (referencia)</h3>
          <div className={styles.grid}>
            {environments.map((env) => (
              <div
                key={env.alias}
                className={styles.wizardCard + " " + styles.card}
                role="button"
                aria-pressed={source?.alias === env.alias}
                aria-disabled={!env.has_password && env.engine !== "sqlite"}
                title={!env.has_password && env.engine !== "sqlite" ? "Este ambiente no tiene contraseña configurada." : undefined}
                onClick={() => selectSource(env)}
              >
                <div className={styles.cardHeader}>
                  <strong>{env.alias}</strong>
                  <span className={styles.badge}>{engineLabel(env.engine)}</span>
                </div>
                <div className={styles.cardBody}>
                  <div>{env.host}</div>
                  {!env.has_password && env.engine !== "sqlite" && <div>⚠ sin contraseña</div>}
                </div>
              </div>
            ))}
            {environments.length === 0 && (
              <div className={styles.emptyState}>Registrá tu primer ambiente para poder comparar.</div>
            )}
          </div>
        </div>

        <div className={styles.wizardColumn}>
          <h3>Destino (a alinear)</h3>
          <div className={styles.grid}>
            {environments.map((env) => {
              const info = targetByAlias.get(env.alias);
              return (
                <div
                  key={env.alias}
                  className={styles.wizardCard + " " + styles.card}
                  role="button"
                  aria-pressed={target?.alias === env.alias}
                  aria-disabled={!info?.enabled}
                  title={info && !info.enabled ? info.reason : undefined}
                  onClick={() => selectTarget(env)}
                >
                  <div className={styles.cardHeader}>
                    <strong>{env.alias}</strong>
                    <span className={styles.badge}>{engineLabel(env.engine)}</span>
                  </div>
                  <div className={styles.cardBody}>
                    <div>{env.host}</div>
                    {info && !info.enabled && <div>{info.reason}</div>}
                  </div>
                </div>
              );
            })}
            {environments.length === 0 && (
              <div className={styles.emptyState}>Registrá al menos dos ambientes del mismo motor.</div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.modeRow}>
        {MODES.filter((m) => m.value !== "snapshot" || diffUxV2).map((m) => (
          <label key={m.value}>
            <input
              type="radio"
              name="dbc-mode"
              checked={mode === m.value}
              onChange={() => setMode(m.value)}
            />
            {m.label}
          </label>
        ))}
      </div>

      {mode === "snapshot" && (
        <div className={styles.modeRow}>
          <SnapshotPicker
            titulo={`Snapshot de ${source?.alias ?? "origen"}`}
            snapshots={sourceSnaps}
            value={sourceSnapId}
            onChange={setSourceSnapId}
          />
          <SnapshotPicker
            titulo={`Snapshot de ${target?.alias ?? "destino"}`}
            snapshots={targetSnaps}
            value={targetSnapId}
            onChange={setTargetSnapId}
          />
        </div>
      )}

      <div className={styles.launchRow}>
        <button onClick={handleLaunch} disabled={!launch.ok || launching || faltanSnapshots}>
          {launching ? "Lanzando…" : "Comparar ambientes"}
        </button>
        {!launch.ok && <span className={styles.recency}>{launch.reason}</span>}
      </div>
    </div>
  );
}

/**
 * Plan 176 F8 — elegir una foto vieja.
 *
 * Se muestra la fecha Y el hash corto: dos snapshots del mismo día son
 * indistinguibles por fecha sola, y elegir el equivocado da un diff que no
 * corresponde a nada.
 */
function SnapshotPicker({
  titulo,
  snapshots,
  value,
  onChange,
}: {
  titulo: string;
  snapshots: SnapshotMeta[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label>
      {titulo}
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Elegí un snapshot…</option>
        {snapshots.map((s) => (
          <option key={s.id} value={s.id}>
            {s.taken_at} · {s.content_hash.slice(0, 8)}
          </option>
        ))}
      </Select>
      {snapshots.length === 0 && (
        <span className={styles.recency}>Sin snapshots guardados para este ambiente.</span>
      )}
    </label>
  );
}

function cargarSnapshots(
  alias: string | undefined,
  setSnaps: (s: SnapshotMeta[]) => void,
  setElegido: (id: string) => void,
  setError: (m: string | null) => void,
) {
  if (!alias) {
    setSnaps([]);
    setElegido("");
    return;
  }
  DbCompare.listSnapshots(alias)
    .then((r) => setSnaps(r.snapshots))
    .catch(() => {
      setSnaps([]);
      setError("No se pudieron cargar los snapshots");
    });
}

export default CompareWizard;
