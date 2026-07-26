import React, { useMemo, useState } from "react";

import { PipelineEditor } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, Checkbox, Input, SectionHeader, Select, Textarea } from "../ui";
import {
  COMMIT_BLOCK_COPY,
  EDIT_VERBS,
  canCommit,
  canRenderDiff,
  emptyEditForm,
  formatPreservation,
  isPlanRequestReady,
  prefillOnlyEmpty,
  summarizeHunks,
  type EditFormState,
  type EditPosition,
  type EditVerb,
  type Hunk,
  type PreservationDto,
} from "../../devops/pipelineEditModel";
import { buildDiffLines } from "./pipelineLint";
import styles from "./PipelineEditNlPanel.module.css";

/**
 * Plan 250 F4/F5 — editar una pipeline que YA existe.
 *
 * El editor NO regenera: parchea el documento original por splice de líneas. Un
 * `parse → modelo → render` sobre el corpus dorado borra 337/337 comentarios y el 48 %
 * de las líneas; acá todo lo que no se tocó queda byte-idéntico, y el sello de
 * preservación lo dice ANTES del botón, sobre el archivo real del operador.
 *
 * Toda la lógica testeable vive en el modelo puro `pipelineEditModel.ts`; acá sólo se
 * pinta y se cablea. El gate de flag-off lo hace el shell por `healthKey`
 * (DevOpsPage.tsx), no este componente.
 */

interface GateDto {
  gate: string;
  passed: boolean;
  new_errors: Array<{ code: string; message: string }>;
  new_warnings: Array<{ code: string; message: string }>;
  resolved: Array<{ code: string; message: string }>;
  skipped_reason: string;
}

interface ReviewDto {
  ok: boolean;
  summary: string;
  unsupported: string[];
  preservation: PreservationDto;
  gates: GateDto[];
}

interface PlanDto {
  ops: number;
  hunks: Hunk[];
  review: ReviewDto;
  yaml: string;
  before_sha256: string;
  after_sha256: string;
}

const diffClass = (kind: string): string =>
  kind === "add" ? styles.diffAdd : kind === "del" ? styles.diffDel : styles.diffSame;

const diffPrefix = (kind: string): string => (kind === "add" ? "+ " : kind === "del" ? "- " : "  ");

export const PipelineEditNlPanel: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  const [form, setForm] = useState<EditFormState>(emptyEditForm());
  const [inputsRaw, setInputsRaw] = useState("");
  const [nlText, setNlText] = useState("");
  const [plan, setPlan] = useState<PlanDto | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [questions, setQuestions] = useState<string[]>([]);
  const [branch, setBranch] = useState("");
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [commitMsg, setCommitMsg] = useState("");

  const set = <K extends keyof EditFormState>(clave: K, valor: EditFormState[K]) => {
    setForm((prev) => ({ ...prev, [clave]: valor }));
    setPlan(null);
    setConfirmChecked(false);
  };

  const inputsParsed = useMemo((): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const linea of inputsRaw.split("\n")) {
      const i = linea.indexOf("=");
      if (i <= 0) continue;
      out[linea.slice(0, i).trim()] = linea.slice(i + 1).trim();
    }
    return out;
  }, [inputsRaw]);

  const estado: EditFormState = { ...form, inputs: inputsParsed };
  const listo = isPlanRequestReady(estado);

  const intentBody = () => ({
    verb: estado.verb,
    target_path: estado.targetPath,
    anchor_ref: estado.anchorRef || null,
    position: estado.position,
    task_ref: estado.taskRef || null,
    inputs: estado.inputs,
    display_name: estado.displayName,
  });

  const pedirDiff = async () => {
    setBusy(true);
    setError("");
    setCommitMsg("");
    try {
      const r = await PipelineEditor.plan({ yaml: estado.beforeYaml, intent: intentBody() });
      setPlan(r);
      setConfirmChecked(false);
    } catch (e) {
      setPlan(null);
      setError(e instanceof Error ? e.message : "no se pudo calcular el cambio");
    } finally {
      setBusy(false);
    }
  };

  const interpretar = async () => {
    setBusy(true);
    setError("");
    setQuestions([]);
    try {
      const r = await PipelineEditor.interpret({ text: nlText, yaml: estado.beforeYaml });
      setNotes(r.notes || []);
      setQuestions(r.questions || []);
      if (r.intent) {
        // Contrato plan 106 F5: PRE-RELLENA sólo lo vacío; nunca pisa lo que el
        // operador ya escribió.
        setForm((prev) =>
          prefillOnlyEmpty(prev, {
            verb: r.intent!.verb as EditVerb,
            targetPath: r.intent!.target_path,
            anchorRef: r.intent!.anchor_ref,
            position: r.intent!.position as EditPosition,
            taskRef: r.intent!.task_ref,
            displayName: r.intent!.display_name,
          }),
        );
        if (!inputsRaw.trim() && r.intent.inputs) {
          setInputsRaw(
            Object.entries(r.intent.inputs)
              .map(([k, v]) => `${k}=${v}`)
              .join("\n"),
          );
        }
      }
      setPlan(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo interpretar el pedido");
    } finally {
      setBusy(false);
    }
  };

  const permiso = canCommit(estado, ctx.health, {
    reviewOk: plan ? plan.review.ok : null,
    confirmChecked,
    hasHunks: !!plan && plan.hunks.length > 0,
  });

  const guardar = async () => {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const r = await PipelineEditor.commit({
        yaml: estado.beforeYaml,
        intent: intentBody(),
        path: estado.repoPath,
        branch,
        before_sha256: plan.before_sha256,
        approved_after_sha256: plan.after_sha256,
        confirm: true,
      });
      setCommitMsg(
        r.status === "unchanged"
          ? `Sin cambios: el contenido ya era idéntico en ${r.branch}.`
          : `Guardado en ${r.branch} (${r.status}).`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo guardar");
    } finally {
      setBusy(false);
    }
  };

  const preservacion = plan ? plan.review.preservation : null;
  const puedeDiff = plan ? canRenderDiff(estado.beforeYaml, plan.yaml) : false;

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Editar pipeline"
        subtitle="Cambia una pipeline que ya existe sin regenerarla: se parchean sólo las líneas del cambio y todo lo demás queda byte-idéntico."
      />

      <div className={styles.grid}>
        <Textarea
          className={styles.editor}
          placeholder="Pegá acá el YAML de la pipeline que querés editar"
          value={form.beforeYaml}
          onChange={(e) => set("beforeYaml", e.target.value)}
        />
        <div className={styles.form}>
          <div className={styles.row}>
            <span className={styles.label}>Ruta en el repo</span>
            <Input
              className={styles.control}
              placeholder="pipelines/ci-cd-online.yml"
              value={form.repoPath}
              onChange={(e) => set("repoPath", e.target.value)}
            />
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Qué cambio</span>
            <Select
              className={styles.control}
              value={form.verb}
              onChange={(e) => set("verb", e.target.value as EditVerb)}
            >
              <option value="">Elegí…</option>
              {EDIT_VERBS.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Bloque</span>
            <Input
              className={styles.control}
              placeholder="stages[0].jobs[0].steps"
              value={form.targetPath}
              onChange={(e) => set("targetPath", e.target.value)}
            />
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Paso de referencia</span>
            <Input
              className={styles.control}
              placeholder="PublishBuildArtifacts@1"
              value={form.anchorRef ?? ""}
              onChange={(e) => set("anchorRef", e.target.value || null)}
            />
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Posición</span>
            <Select
              className={styles.control}
              value={form.position}
              onChange={(e) => set("position", e.target.value as EditPosition)}
            >
              <option value="end">al final</option>
              <option value="before">antes de la referencia</option>
              <option value="after">después de la referencia</option>
            </Select>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Tarea del catálogo</span>
            <Input
              className={styles.control}
              placeholder="PublishCodeCoverageResults@2"
              value={form.taskRef ?? ""}
              onChange={(e) => set("taskRef", e.target.value || null)}
            />
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Nombre visible</span>
            <Input
              className={styles.control}
              value={form.displayName}
              onChange={(e) => set("displayName", e.target.value)}
            />
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Inputs (uno por línea, clave=valor)</span>
            <Textarea
              className={styles.control}
              value={inputsRaw}
              onChange={(e) => {
                setInputsRaw(e.target.value);
                setPlan(null);
              }}
            />
          </div>
        </div>
      </div>

      <Textarea
        className={styles.nlBox}
        placeholder="O describilo en una frase: «agregá la publicación de la cobertura después de los tests»"
        value={nlText}
        onChange={(e) => setNlText(e.target.value)}
      />
      <div className={styles.row}>
        <Button
          variant="secondary"
          disabled={busy || !nlText.trim() || !form.beforeYaml.trim()}
          onClick={interpretar}
        >
          Interpretar el pedido
        </Button>
        <Button variant="primary" disabled={busy || !listo} onClick={pedirDiff}>
          Ver diff
        </Button>
      </div>

      {questions.length > 0 && (
        <ul className={styles.notes}>
          {questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      )}
      {notes.length > 0 && (
        <ul className={styles.notes}>
          {notes.map((n, i) => (
            <li key={i}>Supuesto: {n}</li>
          ))}
        </ul>
      )}
      {error && <div className={styles.error}>{error}</div>}

      {plan && (
        <>
          <div className={styles.summary}>{summarizeHunks(plan.hunks)}</div>
          {preservacion && (
            <div className={preservacion.ok ? styles.seal : `${styles.seal} ${styles.sealBad}`}>
              {formatPreservation(preservacion)}
            </div>
          )}
          {plan.review.gates.map((g) => (
            <div key={g.gate} className={`${styles.gate} ${g.passed ? styles.gateOk : styles.gateBad}`}>
              {g.gate}: {g.passed ? "sin problemas nuevos" : "bloquea"}
              {g.new_errors.map((f) => ` · ${f.code}: ${f.message}`).join("")}
              {g.resolved.length > 0 && ` · resuelve ${g.resolved.length} hallazgo(s)`}
              {g.skipped_reason && ` · ${g.skipped_reason}`}
            </div>
          ))}
          {plan.review.unsupported.length > 0 && (
            <div className={styles.blocked}>
              Construcciones no modeladas presentes (se informan, no bloquean):{" "}
              {plan.review.unsupported.join(", ")}
            </div>
          )}
          <ul className={styles.hunks}>
            {plan.hunks.map((h, i) => (
              <li key={i} className={styles.hunk}>
                líneas {h.start_line}–{Math.max(h.start_line, h.end_line)}: {h.reason}
              </li>
            ))}
          </ul>
          {puedeDiff ? (
            <pre className={styles.diff}>
              {buildDiffLines(estado.beforeYaml, plan.yaml).rows.map((r, k) => (
                <div key={k} className={diffClass(r.kind)}>
                  {diffPrefix(r.kind)}
                  {r.text}
                </div>
              ))}
            </pre>
          ) : (
            <div className={styles.blocked}>
              El archivo es demasiado grande para dibujar el diff; abajo está el YAML resultante.
            </div>
          )}
          <div className={styles.row}>
            <span className={styles.label}>Rama destino</span>
            <Input
              className={styles.control}
              placeholder="feature/edicion-pipeline"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
          </div>
          <Checkbox
            labelClassName={styles.confirm}
            checked={confirmChecked}
            onChange={(e) => setConfirmChecked(e.target.checked)}
            label="Confirmo que revisé el diff y quiero guardarlo en esa rama."
          />
          <div className={styles.row}>
            <Button
              variant="primary"
              disabled={busy || !permiso.allowed || !branch.trim()}
              onClick={guardar}
            >
              Guardar en el repositorio
            </Button>
            {!permiso.allowed && (
              <span className={styles.blocked}>{COMMIT_BLOCK_COPY[permiso.reason]}</span>
            )}
          </div>
          {commitMsg && <div className={styles.summary}>{commitMsg}</div>}
        </>
      )}
    </div>
  );
};

export default PipelineEditNlPanel;
