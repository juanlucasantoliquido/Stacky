import React, { useEffect, useState } from "react";

import { PipelineHandoff } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, Checkbox, Input, SectionHeader, Textarea } from "../ui";
import {
  automaticActions,
  blockedReason,
  frontierSummary,
  manualActions,
  verdictLabel,
  type FrontierAction,
} from "../../devops/pipelineHandoffModel";
import styles from "./PipelineHandoffPanel.module.css";

/**
 * Plan 252 F5 — la frontera de capacidades y el paquete de entrega.
 *
 * Dos listas: lo que hace Stacky y lo que te toca a vos. Un veredicto UNKNOWN cae del
 * lado del operador, nunca del lado de "ya está resuelto": la frontera falla cerrada,
 * porque prometer de más es peor que no prometer.
 *
 * El gate de la flag lo hace el shell por `healthKey`, no este componente.
 */
export const PipelineHandoffPanel: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  const [acciones, setAcciones] = useState<FrontierAction[]>([]);
  const [deploys, setDeploys] = useState(true);
  const [nombre, setNombre] = useState("");
  const [ruta, setRuta] = useState("pipelines/azure-pipelines.yml");
  const [yamlText, setYamlText] = useState("");
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [busy, setBusy] = useState(false);
  const [bundleId, setBundleId] = useState("");

  useEffect(() => {
    let vivo = true;
    PipelineHandoff.frontier(deploys)
      .then((r) => {
        if (vivo) setAcciones(r.actions || []);
      })
      .catch((e) => {
        if (vivo) setError(e instanceof Error ? e.message : "no se pudo leer la frontera");
      });
    return () => {
      vivo = false;
    };
  }, [deploys]);

  const bloqueo = blockedReason({
    flagOn: ctx.health?.handoff_bundle_enabled !== false,
    yamlCount: yamlText.trim() ? 1 : 0,
  });

  const armar = async () => {
    setBusy(true);
    setError("");
    setAviso("");
    try {
      const r = await PipelineHandoff.build({
        pipeline_name: nombre || "pipeline",
        provider: "ado",
        yaml_files: { [ruta]: yamlText },
        pipeline_deploys: deploys,
        spec: {},
      });
      setBundleId(r.bundle_id);
      setAviso(`Paquete listo (${r.bytes} bytes). Id ${r.bundle_id}.`);
    } catch (e) {
      // el 409 del gate anti-secreto es un caso ESPERADO, no un crash
      setBundleId("");
      setError(e instanceof Error ? e.message : "no se pudo armar el paquete");
    } finally {
      setBusy(false);
    }
  };

  const bajar = async () => {
    try {
      await PipelineHandoff.download(bundleId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo descargar");
    }
  };

  const hizo = automaticActions(acciones);
  const toca = manualActions(acciones);

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Paquete de entrega"
        subtitle="Los archivos del pipeline y una guía con lo único que Stacky no puede hacer por vos, en un solo archivo descargable."
      />

      <div className={styles.headline}>{frontierSummary(acciones)}</div>

      <div className={styles.toolbar}>
        <Checkbox
          checked={deploys}
          onChange={(e) => setDeploys(e.target.checked)}
          label="Esta pipeline despliega a un servidor"
        />
      </div>

      <div className={styles.columns}>
        <div className={styles.column}>
          <div className={styles.columnTitle}>Lo hace Stacky</div>
          <ul className={styles.list}>
            {hizo.map((a) => (
              <li key={a.id} className={`${styles.item} ${styles.itemOk}`}>
                <div>{a.label}</div>
                <div className={styles.reason}>{a.reason}</div>
                {a.probe_detail && <div className={styles.verdict}>{a.probe_detail}</div>}
              </li>
            ))}
          </ul>
        </div>
        <div className={styles.column}>
          <div className={styles.columnTitle}>Lo hacés vos</div>
          <ul className={styles.list}>
            {toca.map((a) => (
              <li key={a.id} className={`${styles.item} ${styles.itemManual}`}>
                <div>{a.label}</div>
                <div className={styles.verdict}>{verdictLabel(a.effective)}</div>
                <div className={styles.reason}>{a.reason}</div>
                {a.manual_instruction && (
                  <div className={styles.reason}>{a.manual_instruction}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className={styles.toolbar}>
        <Input
          className={styles.control}
          placeholder="Nombre del pipeline"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
        />
        <Input
          className={styles.control}
          placeholder="Ruta del .yml en el repo"
          value={ruta}
          onChange={(e) => setRuta(e.target.value)}
        />
      </div>
      <Textarea
        className={styles.editor}
        placeholder="Pegá el YAML que querés empaquetar"
        value={yamlText}
        onChange={(e) => setYamlText(e.target.value)}
      />

      <div className={styles.toolbar}>
        <Button variant="primary" disabled={busy || bloqueo !== null} onClick={armar}>
          Armar paquete de entrega
        </Button>
        {bloqueo && <span className={styles.blocked}>{bloqueo}</span>}
        {bundleId && (
          <Button variant="secondary" onClick={bajar}>
            Descargar
          </Button>
        )}
      </div>

      {aviso && <div className={styles.ok}>{aviso}</div>}
      {error && <div className={styles.error}>{error}</div>}
    </div>
  );
};

export default PipelineHandoffPanel;
