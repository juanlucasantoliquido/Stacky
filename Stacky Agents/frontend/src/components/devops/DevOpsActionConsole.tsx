/**
 * Plan 267 F6 — Consola de acciones del agente DevOps.
 *
 * El operador escribe qué quiere hacer en castellano; el backend responde una
 * ACCIÓN TIPADA (no prosa) y esto la muestra como tarjeta: qué acción, sobre qué
 * entorno, qué impacto, qué va a pasar -> confirmación -> recibo.
 *
 * HUMAN-IN-THE-LOOP: nada se ejecuta sin un click del operador, y lo que escribe
 * pasa además por confirmGateway vía runDevOpsAction. Con
 * STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED en OFF (su default) la tarjeta se ve
 * COMPLETA y el botón lleva al panel a hacerlo a mano.
 *
 * PARIDAD DE 3 RUNTIMES por construcción: /propose es determinista, no llama a
 * ningún modelo. Codex CLI, Claude Code CLI y GitHub Copilot Pro obtienen lo
 * mismo. Sin sondeo: se pide sólo cuando el operador aprieta.
 *
 * CERO estilos en línea, CERO diálogos nativos del navegador, CERO sondeo. El
 * ratchet cuenta esos patrones también dentro de los comentarios, así que esta
 * prosa no puede citarlos literalmente sin auto-cazarse.
 */
import React, { useCallback, useState } from 'react';
import { rawGet, rawPost } from '../../api/client';
import { useConfirm } from '../ui';
import { bindingFor } from '../../services/devopsActionBindings';
import type { DevOpsActionReceipt } from '../../services/devopsActionRunner';
import { runDevOpsAction } from '../../services/devopsActionRunner';
import type { DevOpsActionMeta } from '../../services/devopsActionTypes';
import { DevOpsActionProposalCard } from './DevOpsActionProposalCard';
import styles from './DevOpsActionConsole.module.css';
import type { ProposalBlock, ProposalView } from './devopsActionConsoleModel';

interface ProposalDto {
  action_id: string;
  label: string;
  summary: string;
  section_id: string | null;
  nav_path: string;
  effect: 'read' | 'write';
  impact: 'none' | 'low' | 'high';
  targets_environment: boolean;
  environment: string;
  params: { name: string; value: string; source: string }[];
  what_will_happen: string;
  open_questions: string[];
  alternatives: string[];
  confidence: number;
  needs_confirmation: boolean;
  blocked_reason: string;
}

interface ProposeResponse {
  ok: boolean;
  proposal: ProposalDto | null;
  blocked_reason?: string;
  suggestions?: string[];
}

/** DTO del backend -> vista. Los labels se toman del catálogo si está. */
function toView(dto: ProposalDto, catalogo: DevOpsActionMeta[]): ProposalView {
  const meta = catalogo.find((a) => a.id === dto.action_id);
  return {
    actionId: dto.action_id,
    label: dto.label,
    summary: dto.summary,
    navPath: dto.nav_path,
    effect: dto.effect,
    impact: dto.impact,
    targetsEnvironment: dto.targets_environment,
    environment: dto.environment,
    params: dto.params.map((p) => ({
      name: p.name,
      label: meta?.params.find((mp) => mp.name === p.name)?.label ?? p.name,
      value: p.value,
      source: (p.source as ProposalView['params'][number]['source']) ?? 'missing',
    })),
    whatWillHappen: dto.what_will_happen,
    openQuestions: dto.open_questions,
    alternatives: dto.alternatives,
    confidence: dto.confidence,
    needsConfirmation: dto.needs_confirmation,
    blockedReason: (dto.blocked_reason || '') as ProposalBlock,
  };
}

export interface DevOpsActionConsoleProps {
  /** health.action_nl_enabled: con la flag OFF esto no se monta. */
  enabled: boolean;
  project: string;
  onNavigate: (path: string) => void;
}

export const DevOpsActionConsole: React.FC<DevOpsActionConsoleProps> = ({
  enabled,
  project,
  onNavigate,
}) => {
  const askConfirm = useConfirm();
  const [texto, setTexto] = useState('');
  const [busy, setBusy] = useState(false);
  const [vista, setVista] = useState<ProposalView | null>(null);
  const [sugerencias, setSugerencias] = useState<string[]>([]);
  const [recibo, setRecibo] = useState<DevOpsActionReceipt | null>(null);
  const [catalogo, setCatalogo] = useState<DevOpsActionMeta[]>([]);

  /** Params actuales de la tarjeta, como los espera runDevOpsAction. */
  const paramsDe = (v: ProposalView): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const p of v.params) if (p.value) out[p.name] = p.value;
    if (project && !out.project) out.project = project;
    return out;
  };

  /** Trae el catálogo una vez, a pedido. rawGet NO lanza con el 404 de flag OFF. */
  const asegurarCatalogo = useCallback(async (): Promise<DevOpsActionMeta[]> => {
    if (catalogo.length) return catalogo;
    const r = await rawGet<{ ok: boolean; actions: DevOpsActionMeta[] }>(
      '/devops/actions/catalog',
    );
    const acciones = r.ok && r.data ? r.data.actions ?? [] : [];
    setCatalogo(acciones);
    return acciones;
  }, [catalogo]);

  const proponer = async (frase: string) => {
    if (!frase.trim() || busy) return;
    setBusy(true);
    setRecibo(null);
    try {
      const acciones = await asegurarCatalogo();
      const r = await rawPost<ProposeResponse>('/devops/actions/propose', {
        text: frase,
        params: project ? { project } : {},
      });
      if (!r.ok || !r.data) {
        setVista(null);
        setSugerencias([]);
        return;
      }
      if (!r.data.proposal) {
        setVista(null);
        setSugerencias(r.data.suggestions ?? []);
        return;
      }
      setSugerencias([]);
      setVista(toView(r.data.proposal, acciones));
    } finally {
      setBusy(false);
    }
  };

  /** Recalcula la propuesta con los params corregidos. SOLO LECTURA. */
  const reprevisualizar = async (v: ProposalView, params: Record<string, string>) => {
    const r = await rawPost<ProposeResponse>('/devops/actions/preview', {
      action_id: v.actionId,
      params,
    });
    if (r.ok && r.data?.proposal) setVista(toView(r.data.proposal, catalogo));
  };

  const cambiarParam = (name: string, value: string) => {
    if (!vista) return;
    const siguiente: ProposalView = {
      ...vista,
      params: vista.params.map((p) => (p.name === name ? { ...p, value } : p)),
    };
    setVista(siguiente);
    void reprevisualizar(siguiente, paramsDe(siguiente));
  };

  const ejecutar = async () => {
    if (!vista || busy) return;
    const meta =
      catalogo.find((a) => a.id === vista.actionId) ??
      // Sin catálogo servido, el fallback embebido conserva effect e impact.
      (undefined as DevOpsActionMeta | undefined);
    if (!meta) {
      setRecibo(null);
      return;
    }
    setBusy(true);
    try {
      const r = await runDevOpsAction(meta, paramsDe(vista), bindingFor(vista.actionId), {
        askConfirm,
        navigate: onNavigate,
        now: () => Date.now(),
        onReceipt: setRecibo,
      });
      setRecibo(r);
    } finally {
      setBusy(false);
    }
  };

  if (!enabled) return null;

  return (
    <div className={styles.console}>
      <div className={styles.askRow}>
        <input
          className={styles.askInput}
          aria-label="Qué querés hacer"
          placeholder="Escribí qué querés hacer, por ejemplo «ver los logs»"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void proponer(texto);
          }}
        />
        <button
          type="button"
          className={styles.askButton}
          disabled={busy || !texto.trim()}
          onClick={() => void proponer(texto)}
        >
          Ver qué haría
        </button>
      </div>
      <p className={styles.hint}>
        Nada se ejecuta hasta que lo confirmes. Primero te muestro qué acción es, sobre
        qué entorno, qué impacto tiene y qué va a pasar.
      </p>

      {sugerencias.length > 0 && (
        <ul className={styles.questions}>
          {sugerencias.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}

      {vista && (
        <DevOpsActionProposalCard
          proposal={vista}
          receipt={recibo}
          busy={busy}
          onParamChange={cambiarParam}
          onRun={() => void ejecutar()}
          onNavigate={onNavigate}
          onPickAlternative={(actionId) =>
            void reprevisualizar({ ...vista, actionId }, paramsDe(vista))
          }
        />
      )}
    </div>
  );
};

export default DevOpsActionConsole;
