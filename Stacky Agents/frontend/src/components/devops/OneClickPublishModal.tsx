/**
 * OneClickPublishModal (Plan 102 F2)
 *
 * UN resumen previo + UN confirm que encadena materializar → commit → trigger.
 *
 * REGLAS DURAS DE ESTE ARCHIVO (es .tsx NUEVO ⇒ alcance 0 de deuda UI):
 *   - CERO estilos en línea y CERO colores literales. Todo por devops.module.css
 *     con tokens del tema.
 *   - Primitivas `Input` y `Checkbox` de components/ui, nunca un campo crudo.
 *   - NINGUNA bifurcación por proveedor. El commit a Azure DevOps es real desde el
 *     Plan 95 F1.a (ado_provider.py:146 pushea de verdad); un diseño previo lo
 *     daba por no soportado leyendo un texto viejo de la UI y bloqueaba esos
 *     presets. Acá, si el commit falla, falla el paso y se muestra el error real.
 *
 * La lógica de la cadena vive en devops/publishChain.ts (10 tests deterministas);
 * acá solo hay presentación y cableado.
 */
import React, { useEffect, useState } from 'react';
import { Dialog, Input, Checkbox, Button } from '../ui';
import { DevOps, PipelineGenerator, CIPipeline } from '../../api/endpoints';
import {
  runPublishChain,
  describeOutcome,
  type ChainProgress,
  type ChainStep,
  type ChainOutcome,
} from '../../devops/publishChain';
import styles from './devops.module.css';

export interface OneClickPublishModalProps {
  project: string;
  presetName: string;
  target: 'gitlab' | 'ado';
  onClose: () => void;
  /** Plan 93 — acá se monta el PreflightPanel REAL (C5), entre resumen y confirm. */
  preflightSlot?: React.ReactNode;
}

const ETIQUETA: Record<ChainStep, string> = {
  materialize: 'Armar el pipeline',
  commit: 'Guardar en el repositorio',
  trigger: 'Disparar la corrida',
};

const CLASE_ESTADO: Record<string, string> = {
  done: styles.ocpStepDone,
  failed: styles.ocpStepFailed,
  running: styles.ocpStepRunning,
};

export const OneClickPublishModal: React.FC<OneClickPublishModalProps> = ({
  project, presetName, target, onClose, preflightSlot,
}) => {
  const [spec, setSpec] = useState<object | null>(null);
  const [resolved, setResolved] = useState<string[]>([]);
  const [unknown, setUnknown] = useState<string[]>([]);
  const [yaml, setYaml] = useState<string>('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [branch, setBranch] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [corriendo, setCorriendo] = useState(false);
  const [progreso, setProgreso] = useState<ChainProgress[]>([]);
  const [outcome, setOutcome] = useState<ChainOutcome | null>(null);

  // Resumen previo: TODO solo-lectura. Nada de esto escribe ni dispara.
  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        const m = await DevOps.materializePublication(project, presetName);
        if (!vivo) return;
        setSpec(m.spec);
        setResolved(m.resolved ?? []);
        setUnknown(m.unknown_processes ?? []);
        const p = await PipelineGenerator.preview(m.spec);
        if (!vivo) return;
        // Solo el YAML del target del preset: el spec acá es FIJO, no se re-pide
        // con debounce (por eso no se monta PipelineYamlPreview).
        setYaml(target === 'ado' ? p.ado : p.gitlab);
      } catch (e: unknown) {
        if (vivo) setLoadError(e instanceof Error ? e.message : 'Error desconocido');
      }
    })();
    return () => { vivo = false; };
  }, [project, presetName, target]);

  const publicar = async () => {
    // Guarda HITL: sin la casilla tildada no se ejecuta nada.
    if (!confirmado || !spec || corriendo) return;
    setCorriendo(true);
    setProgreso([]);
    const res = await runPublishChain(
      {
        materialize: () => DevOps.materializePublication(project, presetName),
        // Mismo body EXACTO que el camino de siempre (CommitPipelineModal.tsx:50):
        // el spec va spreadeado en la raíz, no anidado. Sin bifurcar por target.
        commit: (s, b) =>
          PipelineGenerator.commit({
            ...(s as Record<string, unknown>),
            target,
            branch: b || undefined, // vacío ⇒ el servidor lo deriva
            project,
            confirm: true,
          }) as Promise<{ branch?: string }>,
        trigger: (ref) => CIPipeline.trigger(project, ref, '', '', true),
      },
      JSON.stringify(spec),
      branch,
      (p) => setProgreso((prev) => [...prev, p]),
    );
    setOutcome(res);
    setCorriendo(false);
  };

  const ultimoPorPaso = (step: ChainStep) =>
    [...progreso].reverse().find((p) => p.step === step);

  return (
    <Dialog open onClose={onClose} title="Publicar en un paso" size="lg"
      closeGuard={{ dirty: false, busy: corriendo }}>
      {loadError && <p className={styles.ocpWarn}>No se pudo armar el resumen: {loadError}</p>}

      <div className={styles.ocpSection}>
        <span className={styles.ocpLabel}>Preset</span>
        <div>{presetName} · {target === 'ado' ? 'Azure DevOps' : 'GitLab CI'}</div>
      </div>

      <div className={styles.ocpSection}>
        <span className={styles.ocpLabel}>Procesos resueltos ({resolved.length})</span>
        <ul className={styles.ocpList}>
          {resolved.map((r) => <li key={r}>{r}</li>)}
        </ul>
        {unknown.length > 0 && (
          <p className={styles.ocpWarn}>
            Sin resolver en el catálogo: {unknown.join(', ')}
          </p>
        )}
      </div>

      <div className={styles.ocpSection}>
        <span className={styles.ocpLabel}>Archivo final que se va a guardar</span>
        <pre className={styles.yamlPre}>{yaml}</pre>
      </div>

      <div className={styles.ocpSection}>
        <label className={styles.ocpLabel} htmlFor="ocp-branch">Branch destino</label>
        <Input
          id="ocp-branch"
          value={branch}
          onChange={(e) => setBranch(e.target.value)}
          placeholder="vacío = lo deriva el servidor"
          disabled={corriendo}
        />
        <p className={styles.ocpLabel}>
          Tras guardar, se dispara la corrida sobre ese mismo branch.
        </p>
      </div>

      {/* Plan 93 — semáforo informativo. NUNCA bloquea: el operador decide (C5). */}
      {preflightSlot}

      <div className={styles.ocpSection}>
        <Checkbox
          checked={confirmado}
          onChange={(e) => setConfirmado(e.target.checked)}
          disabled={corriendo || !spec}
          label="Entiendo que esto escribe en el repositorio y dispara una corrida"
        />
      </div>

      {progreso.length > 0 && (
        <ul className={styles.ocpSteps}>
          {(['materialize', 'commit', 'trigger'] as ChainStep[]).map((step) => {
            const p = ultimoPorPaso(step);
            return (
              <li key={step} className={`${styles.ocpStep} ${p ? CLASE_ESTADO[p.state] ?? '' : ''}`}>
                <span>{ETIQUETA[step]}</span>
                <span>{p ? p.state : 'pendiente'}</span>
                {p?.detail && <span>— {p.detail}</span>}
              </li>
            );
          })}
        </ul>
      )}

      {outcome && <p className={styles.ocpOutcome}>{describeOutcome(outcome)}</p>}

      <div className={styles.ocpActions}>
        <Button variant="ghost" onClick={onClose} disabled={corriendo}>
          {outcome ? 'Cerrar' : 'Cancelar'}
        </Button>
        {!outcome && (
          <Button onClick={() => void publicar()} disabled={!confirmado || !spec || corriendo}>
            {corriendo ? 'Publicando…' : 'Publicar'}
          </Button>
        )}
      </div>
    </Dialog>
  );
};
