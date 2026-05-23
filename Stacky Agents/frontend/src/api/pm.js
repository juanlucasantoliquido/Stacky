/**
 * PM Intelligence Suite — cliente API (Fase 1 MVP, sin IA).
 *
 * Contratos derivados de docs/11_PM_INTELLIGENCE_SUITE.md §2.
 * Todos los endpoints están bajo /api/pm/* y requieren proyecto con tracker_type=azure_devops.
 */
import { api } from "./client";
// ── helpers ────────────────────────────────────────────────────────────────────
function qs(params) {
    const parts = [];
    for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === null || v === "")
            continue;
        parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
    return parts.length ? `?${parts.join("&")}` : "";
}
// ── endpoints ──────────────────────────────────────────────────────────────────
export const PmApi = {
    syncAdo: async (input) => {
        const res = await api.post("/api/pm/sync-ado", input);
        return res.result;
    },
    sprintCurrent: async (project) => {
        const res = await api.get(`/api/pm/sprint/current${qs({ project })}`);
        return res.result;
    },
    sprintHistory: async (project, lastN = 10) => {
        const res = await api.get(`/api/pm/sprint/history${qs({ project, last_n: lastN })}`);
        return res.result;
    },
    listRisks: async (input = {}) => {
        const res = await api.get(`/api/pm/risks${qs(input)}`);
        return res.result;
    },
    acknowledgeRisk: async (riskId, acknowledgedBy) => {
        const res = await api.post(`/api/pm/risks/${encodeURIComponent(riskId)}/acknowledge`, acknowledgedBy ? { acknowledged_by: acknowledgedBy } : {});
        return res.result;
    },
    listComments: async (adoId, limit = 50) => {
        const res = await api.get(`/api/pm/comments${qs({ ado_id: adoId, limit })}`);
        return res.result;
    },
    indexComments: async (input) => {
        const res = await api.post("/api/pm/comments/index", input);
        return res.result;
    },
    aiUsage: async (input = {}) => {
        const res = await api.get(`/api/pm/ai/usage${qs(input)}`);
        return res.result;
    },
    aiModels: async () => {
        const res = await api.get("/api/pm/ai/models");
        return res.result;
    },
    // ── Evals ─────────────────────────────────────────────────────────────────
    evalComponents: async () => {
        const res = await api.get("/api/pm/evals/components");
        return res.result.components;
    },
    runEvals: async (input) => {
        const res = await api.post("/api/pm/evals/run", input);
        return res.result;
    },
    // ── Sentiment ─────────────────────────────────────────────────────────────
    analyzeSentiment: async (input) => {
        const res = await api.post("/api/pm/sentiment/analyze", input);
        return res.result;
    },
    // ── Recommendations ───────────────────────────────────────────────────────
    generateRecommendations: async (input = {}) => {
        const res = await api.post("/api/pm/recommendations/generate", input);
        return res.result;
    },
    listRecommendations: async (input = {}) => {
        const res = await api.get(`/api/pm/recommendations${qs(input)}`);
        return res.result;
    },
    acknowledgeRecommendation: async (recId, acknowledgedBy) => {
        const res = await api.post(`/api/pm/recommendations/${encodeURIComponent(recId)}/acknowledge`, acknowledgedBy ? { acknowledged_by: acknowledgedBy } : {});
        return res.result;
    },
};
