/**
 * Plan 74 F7 — Previsualización del plan de migración (dry-run).
 *
 * Muestra: número total de ops, counts_by_type, warnings, y items ya omitidos.
 * NO dispara ninguna acción: es solo informativa.
 */
import type { MigrationPlanResponse } from "../api/endpoints";
import { hasHighRiskWarnings } from "./MigratorWizard.logic";

interface Props {
  plan: MigrationPlanResponse;
}

export default function MigratorPlanPreview({ plan }: Props) {
  const highRisk = hasHighRiskWarnings({
    ...plan,
    plan_id: plan.plan_id,
    total_ops: plan.total_ops,
  });

  return (
    <div style={{ fontFamily: "monospace", fontSize: 13 }}>
      <h4 style={{ margin: "0 0 8px" }}>Plan de migracion — vista previa</h4>

      <table style={{ borderCollapse: "collapse", width: "100%", marginBottom: 8 }}>
        <tbody>
          <tr>
            <td style={{ padding: "2px 8px", fontWeight: "bold" }}>ID del plan</td>
            <td style={{ padding: "2px 8px", color: "#888" }}>{plan.plan_id}</td>
          </tr>
          <tr>
            <td style={{ padding: "2px 8px", fontWeight: "bold" }}>Total de ops</td>
            <td style={{ padding: "2px 8px" }}>{plan.total_ops}</td>
          </tr>
          <tr>
            <td style={{ padding: "2px 8px", fontWeight: "bold" }}>Items omitidos (ya migrados)</td>
            <td style={{ padding: "2px 8px" }}>{plan.skipped_at_plan}</td>
          </tr>
        </tbody>
      </table>

      {Object.keys(plan.counts_by_type).length > 0 && (
        <>
          <p style={{ margin: "4px 0 2px", fontWeight: "bold" }}>Tipos a migrar:</p>
          <ul style={{ margin: "0 0 8px", paddingLeft: 20 }}>
            {Object.entries(plan.counts_by_type).map(([type, count]) => (
              <li key={type}>
                {type}: {count}
              </li>
            ))}
          </ul>
        </>
      )}

      {plan.warnings.length > 0 && (
        <div
          style={{
            background: highRisk ? "#fff3cd" : "#e8f4fd",
            border: `1px solid ${highRisk ? "#ffc107" : "#bee5eb"}`,
            borderRadius: 4,
            padding: "6px 10px",
          }}
        >
          <p style={{ margin: "0 0 4px", fontWeight: "bold" }}>
            {highRisk ? "Advertencias (riesgo alto):" : "Advertencias:"}
          </p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {plan.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
