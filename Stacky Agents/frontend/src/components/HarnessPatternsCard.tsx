// Plan 35 F4 — patrones que el arnés aprendió, para el operador.
//
// Es SOLO LECTURA más confirmar/descartar. No lanza runs, no publica en el
// tracker y no transiciona work items: la regla 11 es innegociable.
//
// Se usa rawGet/rawPost y NO api.get/api.post: api.* lanza excepción en todo
// non-2xx, así que un 404 (id inexistente) o un backend caído terminarían en una
// promesa rechazada sin capturar en vez de en un estado renderizable.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { rawGet, rawPost } from "../api/client";
import { useWorkbench } from "../store/workbench";

export type HarnessPattern = {
  id: string | null;
  project: string;
  agent_type: string;
  ticket_kind: string;
  signal_kind: string;
  signal_key: string;
  remedy_hint: string;
  occurrences: number;
  confidence: number;
  last_seen: string;
};

type PatternsResponse = { project: string; patterns: HarnessPattern[]; total: number };

const SIGNAL_LABEL: Record<string, string> = {
  criterion_fail: "criterio incumplido",
  verifier_fail: "verificación degradada",
  contract_fail: "precondición fallida",
  repair_success: "remedio que funcionó",
  run_failure: "modo de fallo del run",
};

export default function HarnessPatternsCard() {
  // El proyecto activo sale del store, igual que useReviewInboxCount: así la
  // página no necesita cablear una prop más.
  const project = useWorkbench((s) => s.activeProject?.name ?? "");
  const queryClient = useQueryClient();
  const [busyId, setBusyId] = useState<string | null>(null);
  const queryKey = ["harness-patterns", project];

  const patterns = useQuery({
    queryKey,
    enabled: Boolean(project),
    staleTime: 60_000,
    queryFn: async () => {
      const res = await rawGet<PatternsResponse>(
        `/diag/harness-patterns?project=${encodeURIComponent(project)}`
      );
      if (!res.ok || !res.data) return { project, patterns: [], total: 0 };
      return res.data;
    },
  });

  const cambiarEstado = useMutation({
    mutationFn: async ({ id, accion }: { id: string; accion: "dismiss" | "confirm" }) => {
      setBusyId(id);
      return rawPost(`/diag/harness-patterns/${encodeURIComponent(id)}/${accion}`, {});
    },
    onSettled: () => {
      setBusyId(null);
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  if (!project) return null;

  const items = patterns.data?.patterns ?? [];

  return (
    <section>
      <div>
        <Sparkles size={16} aria-hidden="true" />
        <h3>Lo que el arnés aprendió en este proyecto</h3>
      </div>

      {patterns.isLoading ? (
        <p>Cargando patrones…</p>
      ) : items.length === 0 ? (
        <p>
          Sin patrones aún. Se acumulan solos al terminar cada ejecución; una señal
          empieza a usarse como pista recién cuando se repite.
        </p>
      ) : (
        <ul>
          {items.map((p) => (
            <li key={p.id ?? `${p.signal_kind}:${p.signal_key}`}>
              <div>
                <strong>{SIGNAL_LABEL[p.signal_kind] ?? p.signal_kind}</strong>: {p.signal_key}
              </div>
              <div>
                visto {p.occurrences}× · confianza {p.confidence.toFixed(2)} ·{" "}
                {p.agent_type} / {p.ticket_kind}
                {p.remedy_hint ? ` · remedio: ${p.remedy_hint}` : ""}
              </div>
              {p.id ? (
                <div>
                  <button
                    type="button"
                    disabled={busyId === p.id}
                    onClick={() =>
                      cambiarEstado.mutate({ id: p.id as string, accion: "dismiss" })
                    }
                    title="No volver a usar esta pista. El descarte es definitivo: la cosecha no la recrea."
                  >
                    Descartar
                  </button>
                  <button
                    type="button"
                    disabled={busyId === p.id}
                    onClick={() =>
                      cambiarEstado.mutate({ id: p.id as string, accion: "confirm" })
                    }
                    title="Mantener esta pista activa."
                  >
                    Confirmar
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <p>
        Son pistas que se agregan al contexto del próximo run del mismo tipo de
        ticket, con prioridad baja: nunca desplazan al contrato ni a los criterios
        de aceptación. Descartar una es definitivo.
      </p>
    </section>
  );
}
