import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { HarnessFlags, PipelineEnvironments, type DeclarePreviewResponseDto } from "../../api/endpoints";
import { userFacingMessage } from "../../api/gatewayError"; // Plan 273 F4.7
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
import {
  agruparSkipped,
  avisoContadorNoBaja,
  avisoMasking,
  resumenDeclaracion,
  type DeclarePlanView,
} from "../../devops/pipelineDeclareModel";
import styles from "./PipelineEnvMatrixPanel.module.css";

/** Plan 260 F6 — handoff liviano hacia VariablesSection (mismo patrón que
 *  ALMACEN más abajo: localStorage, sin tocar DevOpsSectionContext). */
const ALMACEN_DECLARAR = "stacky.devops.envMatrix.declararKey";

function guardarKeyParaDeclarar(key: string, secret: boolean): void {
  try {
    window.localStorage.setItem(ALMACEN_DECLARAR, JSON.stringify({ key, secret }));
  } catch {
    /* sin persistencia: VariablesSection simplemente no precarga nada */
  }
}

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

  // Plan 260 F3/F6 — declarar nombres faltantes (HITL: preview -> confirmar).
  const [declarePreview, setDeclarePreview] = useState<DeclarePreviewResponseDto | null>(null);
  const [declareError, setDeclareError] = useState("");
  const [declaring, setDeclaring] = useState(false);
  const [needsMasking, setNeedsMasking] = useState<string[]>([]);

  // C12 — el inventario del plan 246 se lee por type guard: compila con y sin ese plan.
  const inventario = readInventory(ctx);

  // Plan 260 — visible SOLO con STACKY_PIPELINE_ENV_DECLARE_ENABLED (mismo
  // patrón que PipelineTriggerCard.tsx: leer /api/harness-flags).
  const { data: flagsData } = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
    staleTime: 30_000,
  });
  const declareEnabled = !!flagsData?.flags?.find(
    (f) => f.key === "STACKY_PIPELINE_ENV_DECLARE_ENABLED",
  )?.value;

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
      setError(userFacingMessage(e).title);
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
  // Plan 260 — el CTA "Completar" ahora lleva la key preseleccionada.
  const irAVariables = (r?: EnvRequirement) => {
    if (r) guardarKeyParaDeclarar(r.name, r.is_secret);
    ctx.setActiveSection?.("variables");
  };

  // Plan 260 F3 — SOLO LECTURA: proyecta qué se declararía, sin escribir nada.
  const previsualizarDeclaracion = async () => {
    setDeclaring(true);
    setDeclareError("");
    try {
      const res = await PipelineEnvironments.declarePreview({ yaml_text: yamlText, provider });
      if (!res.ok || !res.data) {
        setDeclareError(res.errorBody?.error || res.errorBody?.message || "no se pudo previsualizar la declaración");
        setDeclarePreview(null);
        return;
      }
      setDeclarePreview(res.data);
    } catch (e) {
      setDeclareError(userFacingMessage(e).title);
    } finally {
      setDeclaring(false);
    }
  };

  // Plan 260 F3 — HITL: crea, con valor VACÍO, los nombres del plan de arriba.
  const confirmarDeclaracion = async () => {
    setDeclaring(true);
    setDeclareError("");
    try {
      const res = await PipelineEnvironments.declare({
        yaml_text: yamlText, provider, confirm: true,
      });
      if (!res.ok || !res.data) {
        setDeclareError(res.errorBody?.error || res.errorBody?.message || "no se pudo declarar");
        return;
      }
      setDeclarePreview(null);
      setNeedsMasking(res.data.needs_masking || []);
      await analizar(); // refresca la matriz: el pendiente visible NO debe bajar
    } catch (e) {
      setDeclareError(userFacingMessage(e).title);
    } finally {
      setDeclaring(false);
    }
  };

  const cta = (r: EnvRequirement) => {
    if (canCompleteInStacky(r)) {
      return (
        <Button variant="secondary" size="sm" onClick={() => irAVariables(r)}>
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

          {declareEnabled && (
            <div className={styles.declareBox}>
              {!declarePreview && (
                <Button variant="secondary" size="sm" disabled={declaring} onClick={() => void previsualizarDeclaracion()}>
                  {declaring ? "Analizando..." : "Declarar los nombres"}
                </Button>
              )}
              {declareError && <div className={styles.error}>{declareError}</div>}
              {!declarePreview && needsMasking.length > 0 && (
                <div className={styles.declareWarn}>{avisoMasking(needsMasking)}</div>
              )}
              {declarePreview && (
                <>
                  <div className={styles.declareSummary}>
                    {resumenDeclaracion(declarePreview.plan as DeclarePlanView)}
                  </div>
                  <div className={styles.declareWarn}>
                    {avisoContadorNoBaja(
                      declarePreview.pendiente_visible_actual,
                      declarePreview.pendiente_visible_proyectado,
                    )}
                  </div>
                  {declarePreview.plan.skipped.length > 0 && (
                    <ul className={styles.declareSkipped}>
                      {[...agruparSkipped(declarePreview.plan as DeclarePlanView)].map(([motivo, keys]) => (
                        <li key={motivo}>{keys.join(", ")}: {motivo}</li>
                      ))}
                    </ul>
                  )}
                  <div className={styles.declareActions}>
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={declaring || declarePreview.plan.items.length === 0}
                      onClick={() => void confirmarDeclaracion()}
                    >
                      {declaring ? "Declarando..." : "Confirmar"}
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setDeclarePreview(null)}>
                      Cancelar
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}

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
