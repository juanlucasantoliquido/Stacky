import { useMemo } from "react";

import { useAgentRun } from "../hooks/useAgentRun";
import { useOpenChat } from "../hooks/useOpenChat";
import { useWorkbench } from "../store/workbench";
import type { ContextBlock } from "../types";
import CostPreview from "./CostPreview";
import ModelPicker from "./ModelPicker";
import RunButton from "./RunButton";
import SimilarPanel from "./SimilarPanel";
import SystemPromptDrawer from "./SystemPromptDrawer";
import TokenCounter from "./TokenCounter";
import styles from "./InputContextEditor.module.css";

const TOKEN_LIMIT = 200_000;

export default function InputContextEditor() {
  const {
    activeTicketId,
    activeAgentType,
    blocks,
    patchBlock,
    removeBlock,
    runningExecutionId,
    vsCodeAgent,
  } = useWorkbench();
  const run = useAgentRun();
  const openChat = useOpenChat();

  const tokens = useMemo(() => estimateTokens(blocks), [blocks]);

  const canRun =
    activeTicketId != null &&
    activeAgentType != null &&
    blocks.length > 0 &&
    tokens < TOKEN_LIMIT &&
    runningExecutionId == null &&
    !run.isPending &&
    (activeAgentType !== "custom" || vsCodeAgent != null);

  const canOpenChat =
    activeTicketId != null &&
    vsCodeAgent != null &&
    blocks.length > 0 &&
    !openChat.isPending;

  if (!activeTicketId) {
    return (
      <div className={styles.empty}>
        <h2>Seleccioná un ticket</h2>
        <p className="muted">
          Stacky Agents es un workbench: vos elegís el ticket, vos elegís el agente, vos lo
          corrés.
        </p>
      </div>
    );
  }

  if (!activeAgentType) {
    return (
      <div className={styles.empty}>
        <h2>Elegí un agente</h2>
        <p className="muted">
          Cada agente es independiente. Podés correrlos en cualquier orden.
        </p>
      </div>
    );
  }

  const headerLabel =
    activeAgentType === "custom" && vsCodeAgent
      ? `${vsCodeAgent.name} (copilot agent)`
      : activeAgentType;

  return (
    <div className={styles.editor}>
      <header className={styles.head}>
        <div>
          <div className={styles.title}>INPUT CONTEXT — {headerLabel}</div>
          <div className="muted">ticket #{activeTicketId}</div>
        </div>
        <div className={styles.headRight}>
          <ModelPicker agentType={activeAgentType} blocks={blocks} />
        </div>
      </header>
      <SystemPromptDrawer agentType={activeAgentType} />
      <SimilarPanel />
      <div className={styles.blocks}>
        {blocks.map((b) => (
          <BlockView
            key={b.id}
            block={b}
            onChange={(content) => patchBlock(b.id, { content })}
            onToggleItem={(idx) => {
              if (b.kind !== "choice" || !b.items) return;
              const items = b.items.map((it, i) =>
                i === idx ? { ...it, selected: !it.selected } : it
              );
              patchBlock(b.id, { items });
            }}
            onRemove={() => removeBlock(b.id)}
          />
        ))}
      </div>
      <footer className={styles.foot}>
        <div className={styles.footLeft}>
          <TokenCounter current={tokens} max={TOKEN_LIMIT} />
          <CostPreview agentType={activeAgentType} blocks={blocks} />
        </div>
        <div className={styles.footRight}>
          {vsCodeAgent && (
            <button
              className={styles.chatBtn}
              disabled={!canOpenChat}
              title="Abrir en Copilot Chat con el agente y contexto pre-cargados"
              onClick={() => {
                openChat.mutate({
                  ticket_id: activeTicketId!,
                  context_blocks: blocks,
                });
              }}
            >
              {openChat.isPending ? "Abriendo…" : "↗ Abrir en Chat"}
            </button>
          )}
          <RunButton
            state={run.isPending || runningExecutionId != null ? "running" : "idle"}
            disabled={!canRun}
            onClick={() => {
              run.mutate({
                agent_type: activeAgentType,
                ticket_id: activeTicketId,
                context_blocks: blocks,
              });
            }}
          />
        </div>
      </footer>
    </div>
  );
}

function BlockView({
  block,
  onChange,
  onToggleItem,
  onRemove,
}: {
  block: ContextBlock;
  onChange: (c: string) => void;
  onToggleItem: (i: number) => void;
  onRemove: () => void;
}) {
  return (
    <div className={styles.block}>
      <div className={styles.blockHead}>
        <span className={styles.blockTitle}>{block.title}</span>
        <span className={styles.blockKind}>[{block.kind}]</span>
        <button className={styles.x} onClick={onRemove} title="Sacar bloque">
          ×
        </button>
      </div>
      {block.kind === "editable" && (
        <textarea
          className={styles.textarea}
          rows={4}
          placeholder="Escribí notas, restricciones, prioridades…"
          value={block.content ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {block.kind === "auto" && (
        <pre className={styles.auto}>{block.content}</pre>
      )}
      {block.kind === "choice" && block.items && (
        <ul className={styles.choices}>
          {block.items.map((it, idx) => (
            <li key={idx}>
              <label>
                <input
                  type="checkbox"
                  checked={it.selected}
                  onChange={() => onToggleItem(idx)}
                />{" "}
                {it.label}
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function estimateTokens(blocks: ContextBlock[]): number {
  let chars = 0;
  for (const b of blocks) {
    if (b.content) chars += b.content.length;
    if (b.items) chars += b.items.filter((x) => x.selected).reduce((s, x) => s + x.label.length, 0);
  }
  return Math.ceil(chars / 4);
}
