import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Memory,
  type StackyDirectiveTargeting,
  type StackyMemoryObservation,
} from "../../api/endpoints";
import styles from "./MemoryEditor.module.css";

// Plan 26 M2.1/M2.2 — alta y edición de memorias/directivas desde la UI.
// Sin deps nuevas: los targetings multivaluados se editan como CSV y se parsean
// a arrays. El preview imperativo se compone en el cliente (no toca el backend).

type Mode = "create" | "edit";

const DIMENSION_FIELDS: { key: keyof StackyDirectiveTargeting; label: string; placeholder: string }[] = [
  { key: "agent_types", label: "Agentes", placeholder: "functional, developer" },
  { key: "projects", label: "Proyectos", placeholder: "Strategist_Pacifico" },
  { key: "work_item_types", label: "Work item types", placeholder: "Epic, User Story" },
  { key: "title_keywords", label: "Keywords del ticket", placeholder: "facturación, nota de crédito" },
  { key: "tags", label: "Tags (organización)", placeholder: "proceso-cobranzas" },
];

function splitCsv(raw: string): string[] {
  return raw
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function joinCsv(arr: string[] | undefined): string {
  return (arr ?? []).join(", ");
}

function hasTargeting(t: StackyDirectiveTargeting): boolean {
  return DIMENSION_FIELDS.some((f) => (t[f.key] ?? []).length > 0);
}

export default function MemoryEditor({
  project,
  mode,
  existing,
  injectableTypes,
  onClose,
  onSaved,
}: {
  project: string;
  mode: Mode;
  existing?: StackyMemoryObservation;
  injectableTypes: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [type, setType] = useState(existing?.type ?? injectableTypes[0] ?? "pattern");
  const [title, setTitle] = useState(existing?.title ?? "");
  const [content, setContent] = useState(existing?.content ?? "");
  const [scope, setScope] = useState(existing?.scope ?? "project");
  const [enforcement, setEnforcement] = useState<"suggest" | "always">(
    existing?.enforcement === "always" ? "always" : "suggest",
  );
  const [priority, setPriority] = useState<number>(existing?.priority ?? 0);
  const [targeting, setTargeting] = useState<Record<string, string>>(() => {
    const t = existing?.applies_to ?? {};
    return Object.fromEntries(DIMENSION_FIELDS.map((f) => [f.key, joinCsv(t[f.key])]));
  });

  const isDirective = type === "directive";
  const appliesTo: StackyDirectiveTargeting = useMemo(() => {
    const out: StackyDirectiveTargeting = {};
    for (const f of DIMENSION_FIELDS) {
      const vals = splitCsv(targeting[f.key] ?? "");
      if (vals.length) (out[f.key] as string[]) = vals;
    }
    return out;
  }, [targeting]);

  const targetingOk = !isDirective || hasTargeting(appliesTo);

  const previewText = useMemo(() => {
    if (!isDirective) return "";
    const parts: string[] = [];
    if (appliesTo.agent_types?.length) parts.push(`el agente sea ${appliesTo.agent_types.join("/")}`);
    if (appliesTo.projects?.length) parts.push(`el proyecto sea ${appliesTo.projects.join("/")}`);
    if (appliesTo.work_item_types?.length) parts.push(`el work item sea ${appliesTo.work_item_types.join("/")}`);
    if (appliesTo.title_keywords?.length)
      parts.push(`el ticket mencione ${appliesTo.title_keywords.map((k) => `“${k}”`).join(" o ")}`);
    const cond = parts.length ? parts.join(" y ") : "(sin targeting — definí al menos una dimensión)";
    const verb = enforcement === "always" ? "se inyectará SIEMPRE" : "se sugerirá";
    return `Esta directiva ${verb} cuando ${cond}.`;
  }, [isDirective, appliesTo, enforcement]);

  const save = useMutation({
    mutationFn: async (): Promise<void> => {
      if (mode === "edit" && existing) {
        await Memory.update(existing.memory_id, {
          title,
          content,
          ...(existing.type === "directive"
            ? { enforcement, priority, applies_to: appliesTo }
            : {}),
        });
        return;
      }
      await Memory.create({
        project,
        type,
        title,
        content,
        scope,
        ...(isDirective ? { enforcement, priority, applies_to: appliesTo } : {}),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memory-list", project] });
      qc.invalidateQueries({ queryKey: ["directive-health", project] });
      onSaved();
      onClose();
    },
  });

  const canSubmit = !!title.trim() && !!content.trim() && targetingOk && !save.isPending;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Editor de memoria">
      <div className={styles.modal}>
        <header className={styles.modalHeader}>
          <h2>{mode === "edit" ? "Editar memoria" : "Nueva memoria"}</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </header>

        <div className={styles.body}>
          <label className={styles.field}>
            <span>Tipo</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              disabled={mode === "edit"}
            >
              {injectableTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            <span>Título</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Resumen corto" />
          </label>

          <label className={styles.field}>
            <span>Contenido</span>
            <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={5} />
          </label>

          {mode === "create" && (
            <label className={styles.field}>
              <span>Scope</span>
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="project">project</option>
                <option value="team">team</option>
                <option value="global">global</option>
                <option value="personal">personal</option>
              </select>
            </label>
          )}

          {isDirective && (
            <fieldset className={styles.targeting}>
              <legend>Targeting (¿a qué runs aplica?)</legend>
              {DIMENSION_FIELDS.map((f) => (
                <label className={styles.field} key={f.key}>
                  <span>{f.label}</span>
                  <input
                    value={targeting[f.key] ?? ""}
                    placeholder={f.placeholder}
                    onChange={(e) => setTargeting((s) => ({ ...s, [f.key]: e.target.value }))}
                  />
                </label>
              ))}
              <div className={styles.inlineRow}>
                <label className={styles.field}>
                  <span>Enforcement</span>
                  <select value={enforcement} onChange={(e) => setEnforcement(e.target.value as "suggest" | "always")}>
                    <option value="suggest">suggest (sugerida)</option>
                    <option value="always">always (obligatoria)</option>
                  </select>
                </label>
                <label className={styles.field}>
                  <span>Prioridad</span>
                  <input
                    type="number"
                    value={priority}
                    onChange={(e) => setPriority(Number(e.target.value) || 0)}
                  />
                </label>
              </div>
              <p className={styles.preview} data-testid="directive-preview">
                {previewText}
              </p>
              {!targetingOk && (
                <p className={styles.warn}>Una directiva necesita al menos una dimensión de targeting.</p>
              )}
            </fieldset>
          )}

          {save.isError && (
            <p className={styles.warn}>No se pudo guardar. Revisá los campos (targeting/enforcement).</p>
          )}
        </div>

        <footer className={styles.modalFooter}>
          <button onClick={onClose}>Cancelar</button>
          <button className={styles.primary} disabled={!canSubmit} onClick={() => save.mutate()}>
            {save.isPending ? "Guardando…" : mode === "edit" ? "Guardar cambios" : "Crear"}
          </button>
        </footer>
      </div>
    </div>
  );
}
