import { api, apiBase, rawPost } from "./client";
export const Tickets = {
    list: (project) => api.get(`/api/tickets${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    byId: (id) => api.get(`/api/tickets/${id}`),
    hierarchy: (project) => api.get(`/api/tickets/hierarchy${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    fingerprint: (id) => api.get(`/api/tickets/${id}/fingerprint`), // N3
    glossary: (id) => api.get(`/api/tickets/${id}/glossary`), // FA-09
    comments: (id) => api.get(`/api/tickets/${id}/comments`),
    adoPipelineStatus: (id, forceRefresh = false) => api.get(`/api/tickets/${id}/ado-pipeline-status${forceRefresh ? "?force_refresh=true" : ""}`),
    adoPipelineBatch: (ticketIds, forceRefresh = false) => api.post("/api/tickets/ado-pipeline-batch", {
        ticket_ids: ticketIds,
        force_refresh: forceRefresh,
    }),
    invalidatePipelineCache: (id) => api.delete(`/api/tickets/${id}/ado-pipeline-cache`),
    sync: (project) => api.post("/api/tickets/sync", project ? { project } : {}),
    // P7: sync con rate limiting y campos extendidos
    syncV2: (trigger = "manual", project) => fetch(`${apiBase}/api/tickets/sync-v2`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Stacky-Trigger": trigger },
        body: JSON.stringify(project ? { project } : {}),
    }).then(r => r.json()),
    syncStatus: (project) => api.get(`/api/tickets/sync/status${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    // P7: sync status extendido
    syncStatusV2: (project) => api.get(`/api/tickets/sync/status-v2${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    // P7: config del frontend
    frontendConfig: () => api.get("/api/tickets/config/frontend"),
    // P6: recomendador de asignacion
    assignmentRecommendations: (ticketId, filters) => api.post(`/api/tickets/${ticketId}/assignment-recommendations`, filters || {}),
    // P6: aplicar asignacion (siempre dry_run=true por defecto)
    assignTicket: (ticketId, payload) => api.post(`/api/tickets/${ticketId}/assign`, payload),
    // P6: estadisticas por usuario
    userStats: (user) => api.get(`/api/tickets/user-stats${user ? `?user=${encodeURIComponent(user)}` : ""}`),
    // P6: sincronizar usuarios desde ADO
    syncUsersFromAdo: () => api.post("/api/tickets/users/sync-from-ado", {}),
    // Feature B: diagnosticos causales
    diagnostics: (ticketId) => api.get(`/api/tickets/${ticketId}/diagnostics`),
    invalidateDiagnosticsCache: (ticketId) => api.delete(`/api/tickets/${ticketId}/diagnostics/cache`),
    /** Devuelve el stacky_status actual + historial de transiciones del ticket */
    stackyStatus: (id, limit = 20) => api.get(`/api/tickets/${id}/stacky-status?limit=${limit}`),
    /** Actualiza manualmente el stacky_status de un ticket (reset operacional) */
    setStackyStatus: (id, status, reason) => api.patch(`/api/tickets/${id}/stacky-status`, { status, reason }),
    /**
     * Cierre manual fallback de un ticket (Fase 4).
     * Envía X-Completion-Source: manual_ui para trazabilidad en SystemLogs.
     */
    finishWork: (id, payload) => api.postWithHeaders(`/api/tickets/${id}/finish-work`, payload, { "X-Completion-Source": "manual_ui" }),
    // ── Fase 2: pending-tasks y create-child-task ──────────────────────────────
    /**
     * Lista los pending-task.json no consumidos para un Epic.
     * GET /api/tickets/by-ado/{epic_ado_id}/pending-tasks
     */
    listPendingTasks: (epicAdoId) => api.get(`/api/tickets/by-ado/${epicAdoId}/pending-tasks`),
    /**
     * Crea una Task hija del Epic en ADO consumiendo un pending-task.json.
     * POST /api/tickets/by-ado/{epic_ado_id}/create-child-task
     * Envía X-Completion-Source: manual_ui para trazabilidad.
     */
    createChildTask: (epicAdoId, payload) => api.postWithHeaders(`/api/tickets/by-ado/${epicAdoId}/create-child-task`, payload, { "X-Completion-Source": "manual_ui" }),
    // P2.3 — adjuntos del ticket (portado de WS2)
    attachments: (id) => api.get(`/api/tickets/${id}/attachments`),
    attachmentContent: (id, url, name) => api.get(`/api/tickets/${id}/attachments/content?url=${encodeURIComponent(url)}&name=${encodeURIComponent(name)}`),
    deleteAttachments: (id, attachments) => api.delete(`/api/tickets/${id}/attachments`, { attachments }),
    uploadAttachment: (id, name, content) => api.post(`/api/tickets/${id}/attachments`, { name, content }),
};
export const Agents = {
    list: () => api.get("/api/agents"),
    vsCodeAgents: () => api.get("/api/agents/vscode"),
    history: (filename, limit = 50, project) => {
        const p = new URLSearchParams({ limit: String(limit) });
        if (project)
            p.set("project", project);
        return api.get(`/api/agents/vscode/${encodeURIComponent(filename)}/history?${p.toString()}`);
    },
    run: (payload) => api.post("/api/agents/run", payload),
    cancel: (executionId) => api.post(`/api/agents/cancel/${executionId}`),
    estimate: (payload) => api.post("/api/agents/estimate", payload),
    route: (payload) => api.post("/api/agents/route", payload),
    systemPrompt: (agentType) => api.get(`/api/agents/${agentType}/system-prompt`),
    models: (refresh = false) => api.get(`/api/agents/models${refresh ? "?refresh=true" : ""}`),
    schema: (agentType) => api.get(`/api/agents/${agentType}/schema`),
    nextSuggestion: (afterAgent) => api.get(`/api/agents/next-suggestion?after_agent=${afterAgent}`),
    runWithOptions: (payload) => api.post("/api/agents/run", payload),
    openChat: (payload) => api.post("/api/agents/open-chat", payload),
};
export const AntiPatterns = {
    list: () => api.get("/api/anti-patterns"),
    create: (payload) => api.post("/api/anti-patterns", payload),
    deactivate: (id) => api.delete(`/api/anti-patterns/${id}`),
};
export const Webhooks = {
    list: () => api.get("/api/webhooks"),
    create: (payload) => api.post("/api/webhooks", payload),
    deactivate: (id) => api.delete(`/api/webhooks/${id}`),
};
export const Executions = {
    list: (q) => {
        const params = new URLSearchParams();
        if (q.ticket_id)
            params.set("ticket_id", String(q.ticket_id));
        if (q.agent_type)
            params.set("agent_type", q.agent_type);
        if (q.agent_filename)
            params.set("agent_filename", q.agent_filename);
        if (q.status)
            params.set("status", q.status);
        if (q.project)
            params.set("project", q.project);
        if (q.include_output)
            params.set("include_output", "true");
        if (q.limit)
            params.set("limit", String(q.limit));
        const qs = params.toString();
        return api.get(`/api/executions${qs ? `?${qs}` : ""}`);
    },
    byId: (id) => api.get(`/api/executions/${id}`),
    approve: (id) => api.post(`/api/executions/${id}/approve`),
    discard: (id) => api.post(`/api/executions/${id}/discard`),
    publish: (id, target = "comment") => api.post(`/api/executions/${id}/publish-to-ado`, { target }),
    sendCodexInput: (id, text) => api.post(`/api/executions/${id}/input`, { text }),
    diff: (a, b) => api.get(`/api/executions/${a}/diff/${b}`),
    streamUrl: (id) => `${apiBase}/api/executions/${id}/logs/stream`,
    // P2.3 — endpoints portados de WS2
    forceTransition: (id) => api.post(`/api/executions/${id}/force-transition`),
    reattach: (id) => api.post(`/api/executions/${id}/reattach`),
    deleteOne: (id) => api.delete(`/api/executions/${id}`),
    deleteByTicket: (ticketId, agentFilename) => api.delete(`/api/executions/bulk-by-ticket?ticket_id=${ticketId}&agent_filename=${encodeURIComponent(agentFilename)}`),
};
export const Similarity = {
    // FA-45
    forTicket: (ticketId, agentType, limit = 5) => {
        const p = new URLSearchParams({ ticket_id: String(ticketId), limit: String(limit) });
        if (agentType)
            p.set("agent_type", agentType);
        return api.get(`/api/similarity/similar?${p.toString()}`);
    },
    // FA-14
    graveyard: (query, agentType, limit = 10) => {
        const p = new URLSearchParams({ q: query, limit: String(limit) });
        if (agentType)
            p.set("agent_type", agentType);
        return api.get(`/api/similarity/graveyard?${p.toString()}`);
    },
};
export const Packs = {
    list: () => api.get("/api/packs"),
    start: (payload) => api.post("/api/packs/start", payload),
    byId: (id) => api.get(`/api/packs/runs/${id}`),
    advance: (id) => api.post(`/api/packs/runs/${id}/advance`),
    pause: (id) => api.post(`/api/packs/runs/${id}/pause`),
    resume: (id) => api.post(`/api/packs/runs/${id}/resume`),
    abandon: (id) => api.delete(`/api/packs/runs/${id}`),
};
export const Metrics = {
    agentComparison: (params) => {
        const p = new URLSearchParams();
        if (params?.days)
            p.set("days", String(params.days));
        if (params?.agent_type)
            p.set("agent_type", params.agent_type);
        const qs = p.toString();
        return api.get(`/api/metrics/agent-comparison${qs ? `?${qs}` : ""}`);
    },
};
// FA-13
export const Decisions = {
    list: () => api.get("/api/decisions"),
    create: (payload) => api.post("/api/decisions", payload),
    deactivate: (id) => api.delete(`/api/decisions/${id}`),
};
// FA-05
export const Git = {
    fileContext: (path, n = 5) => api.get(`/api/git/file-context?path=${encodeURIComponent(path)}&n=${n}`),
    contextBlock: (paths, n = 3) => api.post("/api/git/context-block", { paths, n }),
};
// FA-22
export const Translator = {
    translate: (payload) => api.post("/api/translate", payload),
};
// FA-23
export const Exporter = {
    export: (payload) => api.post("/api/export", payload),
};
// FA-43
export const Coaching = {
    tips: (user, days = 30) => {
        const p = new URLSearchParams({ days: String(days) });
        if (user)
            p.set("user", user);
        return api.get(`/api/coaching/tips?${p.toString()}`);
    },
};
// FA-46
export const BestPractices = {
    feed: (days = 7) => api.get(`/api/best-practices/feed?days=${days}`),
};
// FA-07
export const Release = {
    context: (project) => api.get(`/api/release/context${project ? `?project=${project}` : ""}`),
    block: (project) => api.get(`/api/release/block${project ? `?project=${project}` : ""}`),
};
// FA-16
export const Drift = {
    alerts: (unacknowledgedOnly = false) => api.get(`/api/drift/alerts${unacknowledgedOnly ? "?unacknowledged=true" : ""}`),
    run: (windowDays = 7) => api.post("/api/drift/run", { window_days: windowDays }),
    ack: (id) => api.post(`/api/drift/alerts/${id}/ack`),
};
// FA-25
export const ContextInbox = {
    bookmarkletUrl: () => `${apiBase}/api/context/bookmarklet.js`,
    send: (payload) => api.post("/api/context/inbox", payload),
};
// FA-15
export const Glossary = {
    entries: (project) => api.get(`/api/glossary/entries${project ? `?project=${project}` : ""}`),
    candidates: (status = "pending") => api.get(`/api/glossary/candidates?status=${status}`),
    scan: (project, days = 30) => api.post("/api/glossary/scan", { project, days }),
    promote: (id, definition) => api.post(`/api/glossary/candidates/${id}/promote`, { definition }),
    reject: (id) => api.post(`/api/glossary/candidates/${id}/reject`),
};
export const SystemLogs = {
    list: (params) => {
        const p = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== "")
                p.set(k, String(v));
        });
        const qs = p.toString();
        return api.get(`/api/logs${qs ? `?${qs}` : ""}`);
    },
    byId: (id) => api.get(`/api/logs/${id}`),
    stats: () => api.get("/api/logs/stats"),
    exportUrl: (params) => {
        const p = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined)
                p.set(k, String(v));
        });
        return `${apiBase}/api/logs/export?${p.toString()}`;
    },
    purge: (days) => api.delete(`/api/logs/purge?days=${days}`),
};
// ── Multi-project ─────────────────────────────────────────────────────────────
export const Projects = {
    list: () => api.get("/api/projects"),
    getActive: () => api.get("/api/active_project"),
    setActive: (name) => api.post("/api/active_project", { name }),
    init: (payload) => api.post("/api/init_project", payload),
    update: (name, payload) => api.patch(`/api/projects/${name}`, payload),
    testDocsPaths: (name, payload) => api.post(`/api/projects/${name}/test_docs_paths`, payload),
    browseFolder: (payload) => api.post("/api/browse_folder", payload ?? {}),
    remove: (name) => api.delete(`/api/projects/${name}`),
    byName: (name) => api.get(`/api/projects/${name}`),
    getAgents: (name) => api.get(`/api/projects/${name}/agents`),
    putAgents: (name, pinnedAgents) => api.put(`/api/projects/${name}/agents`, { pinned_agents: pinnedAgents }),
    getCredentials: (name) => api.get(`/api/projects/${name}/credentials`),
    launchVsCode: (name) => api.post(`/api/projects/${name}/launch-vscode`),
    vscodeStatus: (name) => api.get(`/api/projects/${name}/vscode-status`),
    trackerStates: (name) => api.get(`/api/projects/${name}/tracker-states`),
    getAgentWorkflow: (projectName, filename) => api.get(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`),
    getAllAgentWorkflows: (projectName) => api.get(`/api/projects/${encodeURIComponent(projectName)}/agent-workflows`),
    putAgentWorkflow: (projectName, filename, workflow) => api.put(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`, workflow),
    // P1.1 ChatDrawer: bootstrap del workspace_root del proyecto activo
    agentBootstrap: () => api.get("/api/agent_bootstrap"),
};
export const Mantis = {
    listProjects: (params) => api.post("/api/mantis/projects", params),
};
// ── QA UAT — Sprint 9 endpoints ───────────────────────────────────────────────
export const QaUat = {
    /** Launch the QA UAT pipeline for a ticket. Returns execution_id. */
    run: (payload) => api.post("/api/qa-uat/run", payload),
    /** Poll a QA UAT execution result (alias: getRunResult). */
    status: (executionId) => api.get(`/api/qa-uat/run/${executionId}`),
    /** Poll a QA UAT execution result. */
    getRunResult: (executionId) => api.get(`/api/qa-uat/run/${executionId}`),
    /** List all data resolution requests for a run. */
    listDataRequests: (runId, ticketId, status) => api.get(`/api/qa-uat/data-request?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${status ? `&status=${status}` : ""}`),
    /** Get status of a specific data request. */
    getDataRequestStatus: (requestId, runId, ticketId) => api.get(`/api/qa-uat/data-request/${encodeURIComponent(requestId)}/status?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`),
    /** Resolve a pending data request (submit value or choose decision). */
    resolveDataRequest: (requestId, payload) => api.post(`/api/qa-uat/data-request/${encodeURIComponent(requestId)}/resolve`, payload),
    /** Create data resolution broker requests from a readiness result. */
    createDataRequests: (runId, payload) => api.post(`/api/qa-uat/data-request/${encodeURIComponent(runId)}`, payload),
    // ── Sprint 10: SQL Seed Proposal ───────────────────────────────────────────
    /** List seed proposals for a run (reads evidence artifacts). */
    listSeedProposals: (runId, ticketId, scenarioId) => api.get(`/api/qa-uat/seed-proposal?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`),
    /** Validate an arbitrary SQL script against safety rules. */
    validateSeedScript: (sqlText, source) => api.post("/api/qa-uat/seed-proposal/validate", { sql_text: sqlText, source: source ?? "operator_submitted" }),
    // ── Sprint 11: Human Approval + Cleanup ────────────────────────────────────
    /** Approve a seed proposal and optionally execute it (dry_run=true by default). */
    approveSeedProposal: (payload) => api.post("/api/qa-uat/seed-proposal/approve", payload),
    /** Trigger cleanup for seeded data. */
    triggerCleanup: (payload) => api.post("/api/qa-uat/seed-proposal/cleanup", payload),
    /** List seed approval records for a run. */
    listSeedApprovals: (runId, ticketId) => api.get(`/api/qa-uat/seed-proposal/approvals?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`),
    // ── Sprint 12: Catalog Readiness ──────────────────────────────────────────
    /** Get catalog readiness artifacts for a run (from evidence dir). */
    listCatalogReadiness: (runId, ticketId, scenarioId) => api.get(`/api/qa-uat/catalog-readiness?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`),
    /** Trigger an on-demand catalog readiness check. */
    checkCatalogReadiness: (payload) => api.post("/api/qa-uat/catalog-readiness/check", payload),
    /** List catalog fixture definitions from catalog_fixtures.yml. */
    listCatalogFixtures: () => api.get("/api/qa-uat/catalog-readiness/fixtures"),
    // ── Sprint 13: Oracle Engine + Weak Assertion Detector ────────────────────
    /** List oracle_result.json artifacts for a run. */
    listOracleResults: (runId, ticketId, scenarioId) => api.get(`/api/qa-uat/oracle-result?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`),
    /** Trigger on-demand oracle evaluation for a run. */
    evaluateOracles: (payload) => api.post("/api/qa-uat/oracle-result/evaluate", payload),
    /** Get weak assertion report for a run. */
    getWeakAssertions: (runId, ticketId) => api.get(`/api/qa-uat/oracle-result/weak-assertions?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`),
    // ── Sprint 14: Test Confidence + Data Lineage ─────────────────────────────
    /** Get confidence report for a run. */
    getConfidenceReport: (runId, ticketId) => api.get(`/api/qa-uat/confidence-report?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`),
    /** Trigger on-demand confidence scoring for a run. */
    scoreConfidence: (payload) => api.post("/api/qa-uat/confidence-report/score", payload),
    /** Get data lineage artifact for a run. */
    getDataLineage: (runId, ticketId) => api.get(`/api/qa-uat/data-lineage?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`),
    /** Trigger on-demand data lineage build for a run. */
    buildDataLineage: (payload) => api.post("/api/qa-uat/data-lineage/build", payload),
};
export const QaBrowser = {
    startRun: (payload) => api.post("/api/qa-browser/runs", payload),
};
export const LocalDiagnostics = {
    get: () => api.get("/api/diag/local"),
    runBackup: () => api.post("/api/diag/backup/run", {}),
    exportLogsUrl: () => `${apiBase}/api/diag/logs/export`,
};
export const Docs = {
    /** Devuelve las fuentes de documentación disponibles para el proyecto activo. */
    getSources: (project) => {
        const qs = project ? `?project=${encodeURIComponent(project)}` : "";
        return api.get(`/api/docs/sources${qs}`);
    },
    /** Devuelve el árbol completo de documentos indexados. */
    getIndex: (params) => {
        const query = new URLSearchParams();
        if (params?.project)
            query.set("project", params.project);
        if (params?.sourceId)
            query.set("source_id", params.sourceId);
        const qs = query.toString();
        return api.get(`/api/docs/index${qs ? `?${qs}` : ""}`);
    },
    /** Devuelve el contenido raw de un documento por su path relativo. */
    getContent: (path, params) => {
        const query = new URLSearchParams({ path });
        if (params?.project)
            query.set("project", params.project);
        if (params?.sourceId)
            query.set("source_id", params.sourceId);
        return api.get(`/api/docs/content?${query.toString()}`);
    },
};
export const FlowConfig = {
    list: (project) => api.get(`/api/flow-config${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    create: (body) => api.post("/api/flow-config", body),
    update: (id, body) => api.put(`/api/flow-config/${id}`, body),
    delete: (id, project) => api.delete(`/api/flow-config/${id}${project ? `?project=${encodeURIComponent(project)}` : ""}`),
    resolve: (adoState, project) => api.get(`/api/flow-config/resolve?ado_state=${encodeURIComponent(adoState)}${project ? `&project=${encodeURIComponent(project)}` : ""}`),
};
export const UiSections = {
    list: () => api.get("/api/ui-sections"),
    set: (section, visible) => api.put(`/api/ui-sections/${encodeURIComponent(section)}`, { visible }),
};
/**
 * Gateway de finalización de agentes.
 *
 * Llama a POST /api/tickets/by-ado/{ado_id}/agent-completion.
 *
 * Devuelve RawResponse en vez de lanzar excepción para que el caller
 * pueda diferenciar 409 html_already_published → diálogo force=true
 * de otros errores → toast de error.
 *
 * Auth: X-Stacky-Agent-Token leído desde import.meta.env.VITE_STACKY_AGENT_TOKEN.
 * Si no está configurado, se envía cadena vacía (el backend responderá 401).
 */
export const AgentCompletion = {
    complete: (adoId, payload) => {
        const token = import.meta.env?.VITE_STACKY_AGENT_TOKEN ?? "";
        return rawPost(`/api/tickets/by-ado/${adoId}/agent-completion`, payload, token ? { "X-Stacky-Agent-Token": token } : {});
    },
};
export const AgentRoles = {
    list: () => api.get("/api/agent-roles"),
    update: (patch) => api.put("/api/agent-roles", patch),
};
export const Chat = {
    turn: (payload) => api.post("/api/chat/turn", payload),
};
export const DocsRag = {
    index: (payload) => api.post("/api/docs-rag/index", payload),
    stats: (projectName) => api.get(`/api/docs-rag/stats${projectName ? `?project_name=${encodeURIComponent(projectName)}` : ""}`),
    chat: (payload) => api.post("/api/docs-rag/chat", payload),
};
// Feature A: Sprint Board
export const PM = {
    sprintBoard: (project) => {
        const qs = project ? `?project=${encodeURIComponent(project)}` : "";
        return api.get(`/api/pm/sprint/board${qs}`);
    },
};
