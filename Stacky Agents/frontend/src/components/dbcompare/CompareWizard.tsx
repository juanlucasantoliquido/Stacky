import { useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { CompareRun, DbEnvironment } from "./dbcompareTypes";
import { selectableTargets, canLaunch } from "./wizardLogic";
import styles from "./dbcompare.module.css";

interface Props {
  environments: DbEnvironment[];
  onLaunched: (run: CompareRun) => void;
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
export function CompareWizard({ environments, onLaunched }: Props) {
  const [source, setSource] = useState<DbEnvironment | null>(null);
  const [target, setTarget] = useState<DbEnvironment | null>(null);
  const [mode, setMode] = useState<"fresh" | "cached">("fresh");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targets = selectableTargets(environments, source);
  const targetByAlias = new Map(targets.map((t) => [t.alias, t]));
  const launch = canLaunch(source, target);

  const selectSource = (env: DbEnvironment) => {
    if (!env.has_password) return;
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

  const handleLaunch = async () => {
    if (!launch.ok || !source || !target) return;
    setLaunching(true);
    setError(null);
    try {
      const res = await DbCompare.compare({ source_alias: source.alias, target_alias: target.alias, mode });
      onLaunched(res.run);
    } catch (err) {
      setError(
        isBusyError(err)
          ? "Ya hay una comparación corriendo para este par de ambientes."
          : err instanceof Error
            ? err.message
            : String(err),
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
                aria-disabled={!env.has_password}
                title={!env.has_password ? "Este ambiente no tiene contraseña configurada." : undefined}
                onClick={() => selectSource(env)}
              >
                <div className={styles.cardHeader}>
                  <strong>{env.alias}</strong>
                  <span className={styles.badge}>{engineLabel(env.engine)}</span>
                </div>
                <div className={styles.cardBody}>
                  <div>{env.host}</div>
                  {!env.has_password && <div>⚠ sin contraseña</div>}
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
        <label>
          <input type="radio" name="dbc-mode" checked={mode === "fresh"} onChange={() => setMode("fresh")} />
          Fresco (toma snapshots ahora)
        </label>
        <label>
          <input type="radio" name="dbc-mode" checked={mode === "cached"} onChange={() => setMode("cached")} />
          Cacheado (usa el último snapshot)
        </label>
      </div>

      <div className={styles.launchRow}>
        <button onClick={handleLaunch} disabled={!launch.ok || launching}>
          {launching ? "Lanzando…" : "Comparar ambientes"}
        </button>
        {!launch.ok && <span className={styles.recency}>{launch.reason}</span>}
      </div>
    </div>
  );
}

export default CompareWizard;
