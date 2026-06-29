/**
 * Plan 74 F7 — Wizard HITL de migración ADO → GitLab.
 *
 * 5 pasos: select → plan → confirm → execute → done.
 * El operador SIEMPRE confirma antes de ejecutar (HITL — no auto-migra).
 * La lógica de pasos vive en MigratorWizard.logic.ts (testeable sin JSX).
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Migrator, type MigrationPlanResponse } from "../api/endpoints";
import MigratorPlanPreview from "./MigratorPlanPreview";
import MigratorMappingTable from "./MigratorMappingTable";
import {
  type WizardStep,
  stepIndex,
  stepLabel,
  TOTAL_STEPS,
  formatRunSummary,
  type MigrationRunResult,
} from "./MigratorWizard.logic";

interface Props {
  initialProject?: string;
}

export default function MigratorWizard({ initialProject = "" }: Props) {
  const [step, setStep] = useState<WizardStep>("select");
  const [stackyProject, setStackyProject] = useState(initialProject);
  const [epicPolicy, setEpicPolicy] = useState<"auto" | "free_degrade" | "premium_native">("auto");
  const [plan, setPlan] = useState<MigrationPlanResponse | null>(null);
  const [runResult, setRunResult] = useState<MigrationRunResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const planMut = useMutation({
    mutationFn: () => Migrator.plan(stackyProject, epicPolicy),
    onSuccess: (data) => {
      setPlan(data);
      setStep("plan");
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(`Error al generar plan: ${err.message}`),
  });

  const executeMut = useMutation({
    mutationFn: () =>
      Migrator.execute(stackyProject, plan!.plan_id, plan!.plan_hash, true),
    onSuccess: (data) => {
      setRunResult({
        applied: data.applied,
        skipped: data.skipped,
        failed: data.failed,
        orphaned: data.orphaned,
      });
      setStep("done");
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(`Error al ejecutar migración: ${err.message}`),
  });

  const progress = ((stepIndex(step) + 1) / TOTAL_STEPS) * 100;

  return (
    <div style={{ maxWidth: 720, fontFamily: "system-ui, sans-serif", fontSize: 14 }}>
      {/* Barra de progreso */}
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            height: 4,
            background: "#e0e0e0",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progress}%`,
              background: "#1f6feb",
              transition: "width 0.3s ease",
            }}
          />
        </div>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#555" }}>
          Paso {stepIndex(step) + 1}/{TOTAL_STEPS}: {stepLabel(step)}
        </p>
      </div>

      {errorMsg && (
        <div
          style={{
            background: "#ffeef0",
            border: "1px solid #f97583",
            borderRadius: 4,
            padding: "8px 12px",
            marginBottom: 12,
            color: "#c00",
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* Paso 1: Configurar origen */}
      {step === "select" && (
        <div>
          <h3 style={{ margin: "0 0 12px" }}>Configurar migracion</h3>
          <label style={{ display: "block", marginBottom: 8 }}>
            <span style={{ fontWeight: "bold" }}>Proyecto Stacky (origen ADO):</span>
            <input
              type="text"
              value={stackyProject}
              onChange={(e) => setStackyProject(e.target.value)}
              placeholder="Ej: RSPACIFICO"
              style={{
                display: "block",
                marginTop: 4,
                padding: "6px 10px",
                width: "100%",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
                boxSizing: "border-box",
              }}
            />
          </label>
          <label style={{ display: "block", marginBottom: 16 }}>
            <span style={{ fontWeight: "bold" }}>Politica de epicas:</span>
            <select
              value={epicPolicy}
              onChange={(e) =>
                setEpicPolicy(e.target.value as "auto" | "free_degrade" | "premium_native")
              }
              style={{
                display: "block",
                marginTop: 4,
                padding: "6px 10px",
                width: "100%",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            >
              <option value="auto">Auto (detecta capacidades del destino)</option>
              <option value="premium_native">Premium nativo (requiere GitLab EE)</option>
              <option value="free_degrade">Free (epicas como issues con etiqueta)</option>
            </select>
          </label>
          <button
            onClick={() => planMut.mutate()}
            disabled={!stackyProject || planMut.isPending}
            style={{
              padding: "8px 20px",
              background: "#1f6feb",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: stackyProject && !planMut.isPending ? "pointer" : "not-allowed",
              opacity: !stackyProject || planMut.isPending ? 0.6 : 1,
            }}
          >
            {planMut.isPending ? "Generando plan..." : "Generar plan (dry-run)"}
          </button>
        </div>
      )}

      {/* Paso 2: Vista previa del plan */}
      {step === "plan" && plan && (
        <div>
          <MigratorPlanPreview plan={plan} />
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button
              onClick={() => setStep("select")}
              style={{
                padding: "6px 16px",
                background: "#f6f8fa",
                border: "1px solid #ccc",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              Atras
            </button>
            <button
              onClick={() => setStep("confirm")}
              disabled={plan.total_ops === 0}
              style={{
                padding: "6px 16px",
                background: plan.total_ops > 0 ? "#1f6feb" : "#ccc",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                cursor: plan.total_ops > 0 ? "pointer" : "not-allowed",
              }}
            >
              {plan.total_ops === 0 ? "Nada que migrar" : "Continuar"}
            </button>
          </div>
        </div>
      )}

      {/* Paso 3: Confirmacion HITL */}
      {step === "confirm" && plan && (
        <div>
          <div
            style={{
              background: "#fff8c5",
              border: "1px solid #f5c211",
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 16,
            }}
          >
            <p style={{ margin: 0, fontWeight: "bold" }}>
              Confirmar migracion — accion irreversible
            </p>
            <p style={{ margin: "6px 0 0", fontSize: 13 }}>
              Se crearan <strong>{plan.total_ops}</strong> operacion(es) en GitLab
              para el proyecto <code>{stackyProject}</code>. Esta accion no se puede deshacer
              automaticamente. Los items ya migrados seran omitidos automaticamente.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setStep("plan")}
              style={{
                padding: "6px 16px",
                background: "#f6f8fa",
                border: "1px solid #ccc",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              Cancelar
            </button>
            <button
              onClick={() => {
                setStep("execute");
                executeMut.mutate();
              }}
              style={{
                padding: "6px 16px",
                background: "#cf222e",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              Confirmar y migrar
            </button>
          </div>
        </div>
      )}

      {/* Paso 4: Ejecutando */}
      {step === "execute" && (
        <div style={{ textAlign: "center", padding: 32 }}>
          <p style={{ fontSize: 15, color: "#555" }}>Ejecutando migracion...</p>
          <p style={{ fontSize: 13, color: "#888" }}>
            No cierres esta ventana. Las operaciones ya ejecutadas son idempotentes.
          </p>
        </div>
      )}

      {/* Paso 5: Completado */}
      {step === "done" && runResult && plan && (
        <div>
          <div
            style={{
              background: "#dafbe1",
              border: "1px solid #56d364",
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 16,
            }}
          >
            <p style={{ margin: 0, fontWeight: "bold" }}>Migracion completada</p>
            <p style={{ margin: "4px 0 0", fontSize: 13 }}>
              {formatRunSummary(runResult)}
            </p>
            {runResult.failed.length > 0 && (
              <ul style={{ margin: "8px 0 0", fontSize: 13, color: "#c00", paddingLeft: 18 }}>
                {runResult.failed.map((f, i) => (
                  <li key={i}>
                    ADO {f.ado_id} ({f.op_kind}): {f.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <h4 style={{ margin: "0 0 8px" }}>Mapa de migracion</h4>
          <MigratorMappingTable stackyProject={stackyProject} />
          <button
            onClick={() => {
              setStep("select");
              setPlan(null);
              setRunResult(null);
            }}
            style={{
              marginTop: 16,
              padding: "6px 16px",
              background: "#f6f8fa",
              border: "1px solid #ccc",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Nueva migracion
          </button>
        </div>
      )}
    </div>
  );
}
