"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
/*
 * FA-24 â€” VS Code extension nativa para Stacky Agents.
 *
 * Comandos:
 *   - stackyAgents.runAgent          â†’ quickPick agente + envÃ­a contexto del archivo
 *   - stackyAgents.openWorkbench      â†’ abre workbench en el browser
 *   - stackyAgents.includeFile        â†’ POST archivo actual como context block
 *   - stackyAgents.includeSelection   â†’ POST selecciÃ³n como context block
 *   - stackyAgents.setActiveTicket    â†’ input para fijar ADO ID
 *
 * Bridge HTTP (puerto 5052 por defecto):
 *   - GET  /health  â†’ liveness probe
 *   - POST /invoke  â†’ inyecta prompt en Copilot Chat y dispara submit
 *   - GET  /models  â†’ lista modelos disponibles en el LM API de VS Code
 *
 * Status bar: muestra el ticket activo. Click â†’ setActiveTicket.
 */
const http = __importStar(require("http"));
const path = __importStar(require("path"));
const vscode = __importStar(require("vscode"));
const TICKET_KEY = "stackyAgents.activeTicket";
const EXTENSION_VERSION = "0.3.2";
let statusBar;
let _bridgeServer;
let _bridgeStartedAt = 0;
function api() {
    return vscode.workspace.getConfiguration("stackyAgents").get("apiBase", "http://localhost:5050");
}
function userEmail() {
    return vscode.workspace.getConfiguration("stackyAgents").get("userEmail", "dev@local");
}
async function fetchJson(url, opts = {}) {
    const res = await fetch(url, {
        ...opts,
        headers: {
            "Content-Type": "application/json",
            "X-User-Email": userEmail(),
            ...opts.headers,
        },
    });
    if (!res.ok) {
        const t = await res.text();
        throw new Error(`${res.status}: ${t}`);
    }
    return res.json();
}
async function listAgents() {
    return fetchJson(`${api()}/api/agents`);
}
async function runAgent(agentType, ticketId, contextBlocks) {
    return fetchJson(`${api()}/api/agents/run`, {
        method: "POST",
        body: JSON.stringify({
            agent_type: agentType,
            ticket_id: ticketId,
            context_blocks: contextBlocks,
        }),
    });
}
async function ensureTicket(context) {
    let stored = context.globalState.get(TICKET_KEY);
    if (stored)
        return stored;
    const value = await vscode.window.showInputBox({
        title: "Stacky Agents â€” ADO ID del ticket activo",
        prompt: "Ej: 1234",
        validateInput: (v) => (/^\d+$/.test(v) ? null : "IngresÃ¡ un nÃºmero"),
    });
    if (!value)
        return null;
    const n = parseInt(value, 10);
    await context.globalState.update(TICKET_KEY, n);
    refreshStatus(context);
    return n;
}
function refreshStatus(context, runningAgent) {
    const t = context.globalState.get(TICKET_KEY);
    if (runningAgent) {
        statusBar.text = `$(sync~spin) Stacky: ${runningAgent}…`;
        statusBar.tooltip = `Ejecutando agente: ${runningAgent}. ADO-${t ?? "?"}`;
        statusBar.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    }
    else if (t) {
        statusBar.text = `$(rocket) Stacky: ADO-${t}`;
        statusBar.tooltip = `Ticket activo: ADO-${t}. Click para cambiar.`;
        statusBar.backgroundColor = undefined;
    }
    else {
        statusBar.text = "$(rocket) Stacky: sin ticket";
        statusBar.tooltip = "Click para fijar el ticket activo";
        statusBar.backgroundColor = undefined;
    }
    statusBar.show();
}
// â”€â”€ Bridge HTTP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
function _isLocalhost(addr) {
    return addr === "127.0.0.1" || addr === "::1" || addr === "::ffff:127.0.0.1";
}
async function _handleInvoke(body, res) {
    // Acepta { system, user } separados o { prompt } combinado (legacy)
    const system = body["system"] ?? "";
    const user = body["user"]
        ?? body["prompt"] ?? "";
    const agent = body["agent"] ?? "";
    const modelReq = body["model"] ?? "";
    const timeoutSec = typeof body["timeout_sec"] === "number" ? body["timeout_sec"] : 240;
    if (!user) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "user / prompt es requerido" }));
        return;
    }
    try {
        const lmApi = vscode.lm;
        if (!lmApi?.selectChatModels) {
            res.writeHead(503, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                ok: false,
                error: "vscode.lm API no disponible. Actualiza VS Code a v1.90+ y verifica que GitHub Copilot este activo.",
            }));
            return;
        }
        // Obtener modelos de Copilot exclusivamente — sin fallback a otros vendors
        const copilotModels = await lmApi.selectChatModels({ vendor: "copilot" });
        if (!copilotModels || copilotModels.length === 0) {
            res.writeHead(503, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                ok: false,
                error: "GitHub Copilot no está disponible en VS Code. Verifica que la extensión Copilot esté instalada y activa con sesión iniciada.",
            }));
            return;
        }
        // Si se pidió un modelo específico, buscarlo dentro de Copilot
        let models = modelReq
            ? copilotModels.filter((m) => m.id === modelReq)
            : copilotModels;
        if (!models || models.length === 0) {
            res.writeHead(503, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                ok: false,
                error: `Modelo Copilot '${modelReq}' no encontrado. Modelos disponibles: ${copilotModels.map((m) => m.id).join(", ")}`,
            }));
            return;
        }
        const chosenModel = models[0];
        const modelId = chosenModel.id ?? "unknown";
        console.log(`[Stacky] /invoke modelo: ${modelId}, agente: ${agent}, system:${system.length}c user:${user.length}c`);
        // Construir mensajes: system como primer User + ack del asistente + prompt real
        const messages = [];
        if (system) {
            messages.push(vscode.LanguageModelChatMessage.User(system));
            messages.push(vscode.LanguageModelChatMessage.Assistant("Entendido. Procedo con la tarea."));
        }
        messages.push(vscode.LanguageModelChatMessage.User(user));
        // CancellationToken con timeout configurable
        const cts = new vscode.CancellationTokenSource();
        const timeoutHandle = setTimeout(() => {
            console.warn(`[Stacky] /invoke timeout (${timeoutSec}s) - cancelando`);
            cts.cancel();
        }, timeoutSec * 1000);
        let fullText = "";
        try {
            const response = await chosenModel.sendRequest(messages, {}, cts.token);
            for await (const chunk of response.text) {
                fullText += chunk;
            }
        }
        finally {
            clearTimeout(timeoutHandle);
            cts.dispose();
        }
        console.log(`[Stacky] /invoke OK: ${fullText.length} chars (modelo: ${modelId})`);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, text: fullText, model_used: modelId, chars: fullText.length }));
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`[Stacky] Error en /invoke: ${msg}`);
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: msg }));
    }
}
async function _handleModels(res) {
    try {
        const lmApi = vscode.lm;
        if (!lmApi?.selectChatModels) {
            res.writeHead(503, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ models: [], error: "vscode.lm API no disponible. Actualiza VS Code a v1.90+" }));
            return;
        }
        // Solo modelos de GitHub Copilot
        const models = await lmApi.selectChatModels({ vendor: "copilot" });
        const out = models.map((m) => ({
            id: m.id,
            name: m.name || m.id,
            vendor: m.vendor || "",
            family: m.family || "",
        }));
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ models: out }));
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ models: [], error: msg }));
    }
}
async function _handleOpenChat(body, res) {
    const message = body["message"] ?? "";
    const agentName = body["agent_name"] ?? "";
    const model = body["model"] ?? "";
    if (!message) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "message es requerido" }));
        return;
    }
    // Prefix the agent mention so any VS Code version picks it up
    const query = agentName ? `@${agentName} ${message}` : message;
    try {
        // Always start a fresh conversation
        const freshChatCommands = [
            "workbench.action.chat.newChat",
            "workbench.action.chat.clear",
            "vscode.editorChat.start",
        ];
        for (const cmd of freshChatCommands) {
            try {
                await vscode.commands.executeCommand(cmd);
                console.log(`[Stacky] /open-chat new chat OK: ${cmd}`);
                break;
            }
            catch {
                // try next
            }
        }
        await _sleep(1800);
        // Write full content to clipboard FIRST.
        // workbench.action.chat.open({ query }) truncates at the first newline,
        // so we open the chat without a query and paste the full content instead.
        await vscode.env.clipboard.writeText(query);
        // Open chat panel (no query → input is empty and focused)
        try {
            await vscode.commands.executeCommand("workbench.action.chat.open");
        }
        catch (e) {
            console.warn(`[Stacky] /open-chat: workbench.action.chat.open falló: ${e}`);
        }
        await _sleep(1000);
        // Paste the full multi-line content into the focused chat input
        try {
            await vscode.commands.executeCommand("editor.action.clipboardPasteAction");
        }
        catch (e) {
            console.warn(`[Stacky] /open-chat: paste falló: ${e}. El contenido sigue en el clipboard.`);
        }
        await _sleep(800);
        // fire-and-forget submit — same strategy as Stacky Pipeline
        vscode.commands.executeCommand("workbench.action.chat.submit").then(() => console.log(`[Stacky] /open-chat submit OK — agente=${agentName || "(none)"}, chars:${query.length}`), (err) => console.error("[Stacky] /open-chat submit error:", err));
        if (model) {
            vscode.window.showInformationMessage(`Stacky → Seleccioná el modelo "${model}" en el chat de Copilot.`);
        }
        console.log(`[Stacky] /open-chat OK: agente=${agentName || "(none)"}, modelo=${model || "(none)"}, msg:${message.length}c`);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, chars: query.length, agent: agentName }));
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`[Stacky] Error en /open-chat: ${msg}`);
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: msg }));
    }
}
function _startBridgeServer() {
    const port = vscode.workspace.getConfiguration("stackyAgents").get("bridgePort") ?? 5052;
    if (!port || port <= 0) {
        console.log("[Stacky] Bridge desactivado (bridgePort=0)");
        return;
    }
    _bridgeServer = http.createServer((req, res) => {
        const method = req.method || "";
        const url = req.url || "";
        const remoteAddr = req.socket.remoteAddress ?? "";
        if (!_isLocalhost(remoteAddr)) {
            res.writeHead(403, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ ok: false, error: "Solo conexiones locales" }));
            return;
        }
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        res.setHeader("Access-Control-Allow-Headers", "Content-Type");
        if (method === "OPTIONS") {
            res.writeHead(204);
            res.end();
            return;
        }
        if (method === "GET" && url === "/health") {
            const copilotExt = vscode.extensions.getExtension("GitHub.copilot-chat");
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                ok: true,
                version: EXTENSION_VERSION,
                copilotChatVersion: copilotExt?.packageJSON?.version ?? null,
                uptimeSeconds: Math.round((Date.now() - _bridgeStartedAt) / 1000),
            }));
            return;
        }
        if (method === "GET" && url === "/models") {
            _handleModels(res);
            return;
        }
        if (method === "POST" && url === "/invoke") {
            let body = "";
            req.on("data", (chunk) => { body += chunk.toString("utf8"); });
            req.on("end", async () => {
                try {
                    const payload = body ? JSON.parse(body) : {};
                    await _handleInvoke(payload, res);
                }
                catch (e) {
                    res.writeHead(400, { "Content-Type": "application/json" });
                    res.end(JSON.stringify({ ok: false, error: String(e) }));
                }
            });
            return;
        }
        if (method === "POST" && url === "/open-chat") {
            let body = "";
            req.on("data", (chunk) => { body += chunk.toString("utf8"); });
            req.on("end", async () => {
                try {
                    const payload = body ? JSON.parse(body) : {};
                    await _handleOpenChat(payload, res);
                }
                catch (e) {
                    res.writeHead(400, { "Content-Type": "application/json" });
                    res.end(JSON.stringify({ ok: false, error: String(e) }));
                }
            });
            return;
        }
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "not found" }));
    });
    _bridgeServer.on("error", (err) => {
        if (err.code === "EADDRINUSE") {
            console.log(`[Stacky] Puerto ${port} en uso â€” otra instancia ya corre`);
        }
        else {
            console.error("[Stacky] Bridge error:", err);
        }
        _bridgeServer = undefined;
    });
    _bridgeServer.listen(port, "127.0.0.1", () => {
        _bridgeStartedAt = Date.now();
        console.log(`[Stacky] Bridge escuchando en 127.0.0.1:${port} (v${EXTENSION_VERSION})`);
    });
}
// â”€â”€ ActivaciÃ³n â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function activate(context) {
    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBar.command = "stackyAgents.setActiveTicket";
    refreshStatus(context);
    _startBridgeServer();
    context.subscriptions.push(statusBar, vscode.commands.registerCommand("stackyAgents.setActiveTicket", async () => {
        const v = await vscode.window.showInputBox({
            title: "ADO ID activo",
            prompt: "Ej: 1234 (vacÃ­o para limpiar)",
        });
        if (v === undefined)
            return;
        if (v === "") {
            await context.globalState.update(TICKET_KEY, undefined);
        }
        else if (/^\d+$/.test(v)) {
            await context.globalState.update(TICKET_KEY, parseInt(v, 10));
        }
        else {
            vscode.window.showErrorMessage("ID invÃ¡lido");
            return;
        }
        refreshStatus(context);
    }), vscode.commands.registerCommand("stackyAgents.openWorkbench", () => {
        vscode.env.openExternal(vscode.Uri.parse("http://localhost:5173"));
    }), vscode.commands.registerCommand("stackyAgents.runAgent", async () => {
        const ticketId = await ensureTicket(context);
        if (!ticketId)
            return;
        try {
            const agents = await listAgents();
            const pick = await vscode.window.showQuickPick(agents.map(a => ({ label: a.name, description: a.type })), { title: "ElegÃ­ un agente" });
            if (!pick)
                return;
            const editor = vscode.window.activeTextEditor;
            const contextBlocks = [];
            if (editor) {
                const fileText = editor.document.getText();
                contextBlocks.push({
                    id: "vscode-file",
                    kind: "auto",
                    title: `Archivo: ${path.basename(editor.document.fileName)}`,
                    content: fileText.slice(0, 20000),
                    source: { type: "vscode-file", path: editor.document.fileName },
                });
            }
            const result = await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: `Stacky — ${pick.label}`,
                cancellable: false,
            }, async (progress) => {
                progress.report({ message: `Ticket ADO-${ticketId} — lanzando…` });
                refreshStatus(context, pick.label);
                const res = await runAgent(pick.description, ticketId, contextBlocks);
                progress.report({ message: `Run #${res.execution_id} iniciado ✓` });
                return res;
            });
            refreshStatus(context);
            const action = await vscode.window.showInformationMessage(`Run lanzado: exec #${result.execution_id}`, "Abrir en browser");
            if (action === "Abrir en browser") {
                vscode.env.openExternal(vscode.Uri.parse(`http://localhost:5173/?exec=${result.execution_id}`));
            }
        }
        catch (e) {
            refreshStatus(context);
            vscode.window.showErrorMessage(`Stacky run failed: ${e.message}`);
        }
    }), vscode.commands.registerCommand("stackyAgents.includeFile", async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor)
            return;
        const filePath = editor.document.fileName;
        try {
            await fetchJson(`${api()}/api/context/inbox`, {
                method: "POST",
                body: JSON.stringify({
                    url: `vscode://file/${filePath}`,
                    title: path.basename(filePath),
                    selection: editor.document.getText().slice(0, 30000),
                }),
            });
            vscode.window.showInformationMessage(`âœ“ Archivo enviado al inbox de Stacky Agents`);
        }
        catch (e) {
            vscode.window.showErrorMessage(`FallÃ³: ${e.message}`);
        }
    }), vscode.commands.registerCommand("stackyAgents.includeSelection", async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor)
            return;
        const sel = editor.document.getText(editor.selection);
        if (!sel) {
            vscode.window.showWarningMessage("Sin selecciÃ³n.");
            return;
        }
        try {
            await fetchJson(`${api()}/api/context/inbox`, {
                method: "POST",
                body: JSON.stringify({
                    url: `vscode://file/${editor.document.fileName}#L${editor.selection.start.line + 1}`,
                    title: `SelecciÃ³n de ${path.basename(editor.document.fileName)}`,
                    selection: sel,
                }),
            });
            vscode.window.showInformationMessage(`âœ“ SelecciÃ³n enviada al inbox`);
        }
        catch (e) {
            vscode.window.showErrorMessage(`FallÃ³: ${e.message}`);
        }
    }));
}
function deactivate() {
    if (_bridgeServer) {
        _bridgeServer.close();
        _bridgeServer = undefined;
    }
}
