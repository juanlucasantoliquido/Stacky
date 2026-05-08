/*
 * ModelPicker — muestra los modelos reales disponibles (GitHub Copilot u otros backends)
 * con un botón de refresh y el modelo elegido por el router.
 */
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentType, ContextBlock } from "../types";
import styles from "./ModelPicker.module.css";

interface Props {
  agentType: AgentType | null;
  blocks: ContextBlock[];
}

interface RouteInfo {
  model: string;
  reason: string;
  available: string[];
}

export default function ModelPicker({ agentType, blocks }: Props) {
  const { modelOverride, setModelOverride } = useWorkbench();
  const [auto, setAuto] = useState<RouteInfo | null>(null);
  const queryClient = useQueryClient();

  const modelsQuery = useQuery({
    queryKey: ["agent-models"],
    queryFn: () => Agents.models(),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!agentType) {
      setAuto(null);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(async () => {
      try {
        const r = await Agents.route({
          agent_type: agentType,
          context_blocks: blocks,
          model_override: modelOverride,
        });
        if (!cancelled) setAuto(r);
      } catch {
        if (!cancelled) setAuto(null);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [agentType, blocks, modelOverride]);

  if (!agentType || !auto) return null;

  const liveModels = modelsQuery.data?.models ?? [];
  const liveById = new Map(liveModels.map((m) => [m.id, m] as const));
  const labelFor = (id: string) => {
    const m = liveById.get(id);
    if (!m) return id;
    if (m.vendor && m.name && m.name !== m.id) {
      return `${m.name} · ${m.vendor}`;
    }
    return m.name || id;
  };

  const refreshModels = async () => {
    await Agents.models(true);
    queryClient.invalidateQueries({ queryKey: ["agent-models"] });
  };

  const hint =
    modelsQuery.data?.fallback_used && modelsQuery.data?.error
      ? `Modelos en fallback. ${modelsQuery.data.error}`
      : auto.reason;

  return (
    <div className={styles.box} title={`Reason: ${auto.reason}`}>
      <span className={styles.label}>model:</span>
      <select
        className={styles.select}
        value={modelOverride ?? ""}
        onChange={(e) => setModelOverride(e.target.value || null)}
      >
        <option value="">auto ({labelFor(auto.model)})</option>
        {auto.available.map((id) => (
          <option key={id} value={id}>
            {labelFor(id)}
          </option>
        ))}
      </select>
      <button
        type="button"
        className={styles.refresh}
        onClick={refreshModels}
        disabled={modelsQuery.isFetching}
        title="Recargar lista de modelos desde GitHub Copilot"
      >
        {modelsQuery.isFetching ? "↻" : "⟳"}
      </button>
      <span className={styles.reason}>{hint}</span>
    </div>
  );
}
