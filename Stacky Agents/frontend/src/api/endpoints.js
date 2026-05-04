import { api, apiBase } from "./client";
export const Tickets = {
    list: () => api.get("/api/tickets"),
    byId: (id) => api.get(`/api/tickets/${id}`),
    fingerprint: (id) => api.get(`/api/tickets/${id}/fingerprint`), // N3
    glossary: (id) => api.get(`/api/tickets/${id}/glossary`), // FA-09
    comments: (id) => api.get(`/api/tickets/${id}/comments`),
    sync: () => api.post("/api/tickets/sync"),
    syncStatus: () => api.get("/api/tickets/sync/status"),
};
export const Agents = {
    list: () => api.get("/api/agents"),
    vsCodeAgents: () => api.get("/api/agents/vscode"),
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
        if (q.status)
            params.set("status", q.status);
        const qs = params.toString();
        return api.get(`/api/executions${qs ? `?${qs}` : ""}`);
    },
    byId: (id) => api.get(`/api/executions/${id}`),
    approve: (id) => api.post(`/api/executions/${id}/approve`),
    discard: (id) => api.post(`/api/executions/${id}/discard`),
    publish: (id, target = "comment") => api.post(`/api/executions/${id}/publish-to-ado`, { target }),
    diff: (a, b) => api.get(`/api/executions/${a}/diff/${b}`),
    streamUrl: (id) => `${apiBase}/api/executions/${id}/logs/stream`,
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
