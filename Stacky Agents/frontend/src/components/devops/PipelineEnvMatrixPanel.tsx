import React, { useMemo, useState } from "react";

import { PipelineEnvironments } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, SectionHeader, Select, Textarea } from "../ui";
import {
  canCompleteInStacky,
  cellKey,
  headline,
  indexCells,
  pendingByEnvironment,
  pendingDelta,
  readInventory,
  sortRequirements,
  type EnvMatrixResponse,
  type EnvRequirement,
} from "../../devops/pipelineEnvMatrixModel";
import styles from "./PipelineEnvMatrixPanel.module.css";

/**
 * Plan 251 F5 — la matriz entorno × valor.
 *
 * SOLO LECTURA: no escribe en el repo, ni en el proveedor, ni en el servidor. El único
 * camino de escritura sigue siendo el formulario del Plan 94 (write-only, con
 * `confirm:true` server-side); acá no hay una segunda superficie de escritura.
 *
 * Stacky NO rellena, no adivina y no propone valores: presenta hechos y, cuando el
 * YAML trae un `default`, lo muestra tal cual para que el operador confirme o cambie.
 */

const ICONO: Record<string, string> = {
  definido: "✅",
  default: "⚪",
  falta: "🔴",
  manual: "⚙️",
};

const CTA_MANUAL =
  "Esto no lo puede hacer Stacky: queda documentado en el paquete de entrega (plan 252).";

const ALMACEN = "stacky.devops.envMatrix.lastFingerprint";

export const PipelineEnvMatrixPanel: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  const [yamlText, setYamlText] = useState("");
  const [provider, setProvider] = useState("azure_devops");
  const [matriz, setMatriz] = useState<EnvMatrixResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [delta, setDelta] = useState("");

  // C12 — el inventario del plan 246 se lee por type guard: compila con y sin ese plan.
  const inventario = readInventory(ctx);

  const analizar = async () => {
    setBusy(true);
    setError("");
    try {
      const previo = leerPrevio();
      const r = await PipelineEnvironments.analyze({ yaml_text: yamlText, provider });
      setMatriz(r);
      setDelta(pendingDelta(r, previo));
      guardarPrevio(r);
    } catch (e) {
      setMatriz(null);
      setError(e instanceof Error ? e.message : "no se pudo analizar la pipeline");
    } finally {
      setBusy(false);
    }
  };

  const indice = useMemo(() => (matriz ? indexCells(matriz) : new Map()), [matriz]);
  const filas = useMemo(() => (matriz ? sortRequirements(matriz) : []), [matriz]);
  const pendientes = useMemo(
    () => (matriz ? pendingByEnvironment(matriz) : {}),
    [matriz],
  );

  const irAServidores = () => ctx.setActiveSection?.("servidores");
  const irAVariables = () => ctx.setActiveSection?.("variables");

  const cta = (r: EnvRequirement) => {
    if (canCompleteInStacky(r)) {
      return (
        <Button variant="secondary" size="sm" onClick={irAVariables}>
          Completar
        </Button>
      );
    }
    if (r.kind === "server") {
      return (
        <Button variant="secondary" size="sm" onClick={irAServidores}>
          Registrar servidor
        </Button>
      );
    }
    return <span className={styles.note}>{CTA_MANUAL}</span>;
  };

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Matriz de entornos"
        subtitle="Todo lo que esta pipeline necesita para poder correr, cruzado contra sus entornos reales. Stacky busca primero en lo que ya sabe y te pide sólo lo que falta."
      />

      {!inventario && (
        <div className={styles.note}>
          El inventario de pipelines (plan 246) no está disponible: pegá el YAML de la
          pipeline que querés analizar.
        </div>
      )}

      <div className={styles.toolbar}>
        <Textarea
          className={styles.editor}
          placeholder="Pegá acá el YAML de la pipeline"
          value={yamlText}
          onChange={(e) => setYamlText(e.target.value)}
        />
        <Select
          className={styles.control}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="azure_devops">Azure DevOps</option>
          <option value="gitlab">GitLab</option>
        </Select>
        <Button variant="primary" disabled={busy || !yamlText.trim()} onClick={analizar}>
          Analizar
        </Button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {matriz && (
        <>
          <div className={styles.headline}>{headline(matriz)}</div>
          {delta && <div className={styles.delta}>{delta}</div>}

          <div className={styles.chips}>
            {matriz.environments.map((env) => (
              <span
                key={env}
                className={
                  pendientes[env] ? `${styles.chip} ${styles.chipPending}` : styles.chip
                }
              >
                {env}: {pendientes[env] || 0} sin cargar
              </span>
            ))}
          </div>

          {matriz.degraded.map((d, i) => (
            <div key={i} className={styles.banner}>
              {d}
            </div>
          ))}

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Valor</th>
                  {matriz.environments.map((env) => (
                    <th key={env}>{env}</th>
                  ))}
                  <th>Qué hacer</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((r) => (
                  <tr key={`${r.kind}:${r.name}`}>
                    <td>
                      <div className={styles.name}>{r.name}</div>
                      <div className={styles.kind}>
                        {r.kind}
                        {r.is_secret ? " 🔒" : ""}
                        {r.confidence === "baja" ? " · confianza baja" : ""}
                      </div>
                      {r.declared_default != null && (
                        <div className={styles.note}>default: {r.declared_default}</div>
                      )}
                      {r.note && <div className={styles.note}>{r.note}</div>}
                      {r.evidence.length > 0 && (
                        <ul className={styles.evidence}>
                          {r.evidence.map((e, i) => (
                            <li key={i}>
                              {e.path}: {e.excerpt}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    {matriz.environments.map((env) => {
                      const celda = indice.get(cellKey(r.name, env));
                      return (
                        <td key={env}>
                          <span>{celda ? ICONO[celda.state] || "" : ""}</span>{" "}
                          <span className={styles.kind}>{celda?.state}</span>
                          {celda?.note && <div className={styles.note}>{celda.note}</div>}
                        </td>
                      );
                    })}
                    <td className={styles.actions}>{cta(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

function leerPrevio(): { fingerprint: string; pending: number } | null {
  try {
    const crudo = window.localStorage.getItem(ALMACEN);
    return crudo ? (JSON.parse(crudo) as { fingerprint: string; pending: number }) : null;
  } catch {
    return null;
  }
}

function guardarPrevio(m: EnvMatrixResponse): void {
  try {
    window.localStorage.setItem(
      ALMACEN,
      JSON.stringify({ fingerprint: m.pending_fingerprint, pending: m.pending_count }),
    );
  } catch {
    /* sin persistencia: el delta simplemente no se muestra */
  }
}

export default PipelineEnvMatrixPanel;
