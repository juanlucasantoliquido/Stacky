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
import * as http from "http";
import * as path from "path";
import * as vscode from "vscode";

const TICKET_KEY = "stackyAgents.activeTicket";
const EXTENSION_VERSION = "0.3.4";

let statusBar: vscode.StatusBarItem;
let _bridgeServer: http.Server | undefined;
let _bridgeStartedAt = 0;

function api(): string {
  return vscode.workspace.getConfiguration("stackyAgents").get("apiBase",
    "http://localhost:5050");
}

function userEmail(): string {
  return vscode.workspace.getConfiguration("stackyAgents").get("userEmail", "dev@local");
}

async function fetchJson<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-User-Email": userEmail(),
      ...(opts.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${res.status}: ${t}`);
  }
  return res.json() as Promise<T>;
}

async function listAgents(): Promise<{ type: string; name: string }[]> {
  return fetchJson(`${api()}/api/agents`);
}

async function runAgent(
  agentType: string,
  ticketId: number,
  contextBlocks: any[],
): Promise<{ execution_id: number }> {
  return fetchJson(`${api()}/api/agents/run`, {
    method: "POST",
    body: JSON.stringify({
      agent_type: agentType,
      ticket_id: ticketId,
      context_blocks: contextBlocks,
    }),
  });
}

async function ensureTicket(context: vscode.ExtensionContext): Promise<number | null> {
  let stored = context.globalState.get<number>(TICKET_KEY);
  if (stored) return stored;
  const value = await vscode.window.showInputBox({
    title: "Stacky Agents â€” ADO ID del ticket activo",
    prompt: "Ej: 1234",
    validateInput: (v) => (/^\d+$/.test(v) ? null : "IngresÃ¡ un nÃºmero"),
  });
  if (!value) return null;
  const n = parseInt(value, 10);
  await context.globalState.update(TICKET_KEY, n);
  refreshStatus(context);
  return n;
}

function refreshStatus(context: vscode.ExtensionContext, runningAgent?: string) {
  const t = context.globalState.get<number>(TICKET_KEY);
  if (runningAgent) {
    statusBar.text = `$(sync~spin) Stacky: ${runningAgent}…`;
    statusBar.tooltip = `Ejecutando agente: ${runningAgent}. ADO-${t ?? "?"}`;
    statusBar.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
  } else if (t) {
    statusBar.text = `$(rocket) Stacky: ADO-${t}`;
    statusBar.tooltip = `Ticket activo: ADO-${t}. Click para cambiar.`;
    statusBar.backgroundColor = undefined;
  } else {
    statusBar.text = "$(rocket) Stacky: sin ticket";
    statusBar.tooltip = "Click para fijar el ticket activo";
    statusBar.backgroundColor = undefined;
  }
  statusBar.show();
}

// â”€â”€ Bridge HTTP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function _sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function _isLocalhost(addr: string): boolean {
  return addr === "127.0.0.1" || addr === "::1" || addr === "::ffff:127.0.0.1";
}

async function _handleInvoke(
  body: Record<string, unknown>,
  res: http.ServerResponse,
): Promise<void> {
  // Acepta { system, user } separados o { prompt } combinado (legacy)
  const system   = (body["system"] as string | undefined) ?? "";
  const user     = (body["user"]   as string | undefined)
                ?? (body["prompt"] as string | undefined) ?? "";
  const agent    = (body["agent"]  as string | undefined) ?? "";
  const modelReq = (body["model"]  as string | undefined) ?? "";
  const timeoutSec = typeof body["timeout_sec"] === "number" ? (body["timeout_sec"] as number) : 240;

  if (!user) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "user / prompt es requerido" }));
    return;
  }

  try {
    const lmApi = (vscode as any).lm;
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
      ? copilotModels.filter((m: any) => m.id === modelReq)
      : copilotModels;
    if (!models || models.length === 0) {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        ok: false,
        error: `Modelo Copilot '${modelReq}' no encontrado. Modelos disponibles: ${copilotModels.map((m: any) => m.id).join(", ")}`,
      }));
      return;
    }

    const chosenModel = models[0];
    const modelId = chosenModel.id ?? "unknown";
    console.log(`[Stacky] /invoke modelo: ${modelId}, agente: ${agent}, system:${system.length}c user:${user.length}c`);

    // Construir mensajes: system como primer User + ack del asistente + prompt real
    const messages: vscode.LanguageModelChatMessage[] = [];
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
    } finally {
      clearTimeout(timeoutHandle);
      cts.dispose();
    }

    console.log(`[Stacky] /invoke OK: ${fullText.length} chars (modelo: ${modelId})`);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, text: fullText, model_used: modelId, chars: fullText.length }));

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[Stacky] Error en /invoke: ${msg}`);
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: msg }));
  }
}
async function _handleModels(res: http.ServerResponse): Promise<void> {
  try {
    const lmApi = (vscode as any).lm;
    if (!lmApi?.selectChatModels) {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ models: [], error: "vscode.lm API no disponible. Actualiza VS Code a v1.90+" }));
      return;
    }
    // Solo modelos de GitHub Copilot
    const models = await lmApi.selectChatModels({ vendor: "copilot" });
    const out = (models as any[]).map((m: any) => ({
      id:     m.id,
      name:   m.name || m.id,
      vendor: m.vendor || "",
      family: m.family || "",
    }));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ models: out }));
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ models: [], error: msg }));
  }
}

async function _handleOpenChat(
  body: Record<string, unknown>,
  res: http.ServerResponse,
): Promise<void> {
  const message   = (body["message"]    as string | undefined) ?? "";
  const agentName = (body["agent_name"] as string | undefined) ?? "";
  const model     = (body["model"]      as string | undefined) ?? "";

  if (!message) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "message es requerido" }));
    return;
  }

  // Prefix the agent mention so any VS Code version picks it up
  const query = agentName ? `@${agentName} ${message}` : message;

  // Respond immediately — VS Code commands can hang indefinitely on some versions.
  // The actual chat-open flow runs fire-and-forget in the background.
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ ok: true, chars: query.length, agent: agentName }));

  // Background: open VS Code Copilot Chat with the full context
  (async () => {
    try {
    // Always start a fresh conversation.
    // Wrap each command with a 3 s timeout so a hanging promise doesn't block the flow.
    const freshChatCommands = [
      "workbench.action.chat.newChat",
      "workbench.action.chat.clear",
      "vscode.editorChat.start",
    ];
    for (const cmd of freshChatCommands) {
      try {
        await Promise.race([
          vscode.commands.executeCommand(cmd),
          new Promise<void>((_, reject) =>
            setTimeout(() => reject(new Error(`timeout: ${cmd}`)), 3000)
          ),
        ]);
        console.log(`[Stacky] /open-chat new chat OK: ${cmd}`);
        break;
      } catch {
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
    } catch (e) {
      console.warn(`[Stacky] /open-chat: workbench.action.chat.open falló: ${e}`);
    }
    await _sleep(1000);

    // Paste the full multi-line content into the focused chat input
    try {
      await vscode.commands.executeCommand("editor.action.clipboardPasteAction");
    } catch (e) {
      console.warn(`[Stacky] /open-chat: paste falló: ${e}. El contenido sigue en el clipboard.`);
    }

    await _sleep(800);

    // fire-and-forget submit — same strategy as Stacky Pipeline
    vscode.commands.executeCommand("workbench.action.chat.submit").then(
      () => console.log(`[Stacky] /open-chat submit OK — agente=${agentName || "(none)"}, chars:${query.length}`),
      (err: unknown) => console.error("[Stacky] /open-chat submit error:", err),
    );

    if (model) {
      vscode.window.showInformationMessage(
        `Stacky → Seleccioná el modelo "${model}" en el chat de Copilot.`
      );
    }

    console.log(`[Stacky] /open-chat OK: agente=${agentName || "(none)"}, modelo=${model || "(none)"}, msg:${message.length}c`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[Stacky] Error en /open-chat background: ${msg}`);
    }
  })();
}

function _startBridgeServer(): void {
  const port = vscode.workspace.getConfiguration("stackyAgents").get<number>("bridgePort") ?? 5052;
  if (!port || port <= 0) {
    console.log("[Stacky] Bridge desactivado (bridgePort=0)");
    return;
  }

  _bridgeServer = http.createServer((req, res) => {
    const method = req.method || "";
    const url    = req.url || "";

    const remoteAddr = req.socket.remoteAddress ?? "";
    if (!_isLocalhost(remoteAddr)) {
      res.writeHead(403, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: "Solo conexiones locales" }));
      return;
    }

    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    if (method === "OPTIONS") { res.writeHead(204); res.end(); return; }

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
      req.on("data", (chunk: Buffer) => { body += chunk.toString("utf8"); });
      req.on("end", async () => {
        try {
          const payload = body ? JSON.parse(body) : {};
          await _handleInvoke(payload, res);
        } catch (e) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: String(e) }));
        }
      });
      return;
    }

    if (method === "POST" && url === "/open-chat") {
      let body = "";
      req.on("data", (chunk: Buffer) => { body += chunk.toString("utf8"); });
      req.on("end", async () => {
        try {
          const payload = body ? JSON.parse(body) : {};
          await _handleOpenChat(payload, res);
        } catch (e) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: String(e) }));
        }
      });
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "not found" }));
  });

  _bridgeServer.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "EADDRINUSE") {
      console.log(`[Stacky] Puerto ${port} en uso â€” otra instancia ya corre`);
    } else {
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

export function activate(context: vscode.ExtensionContext) {
  statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left, 100
  );
  statusBar.command = "stackyAgents.setActiveTicket";
  refreshStatus(context);

  _startBridgeServer();

  context.subscriptions.push(
    statusBar,

    vscode.commands.registerCommand("stackyAgents.setActiveTicket", async () => {
      const v = await vscode.window.showInputBox({
        title: "ADO ID activo",
        prompt: "Ej: 1234 (vacÃ­o para limpiar)",
      });
      if (v === undefined) return;
      if (v === "") {
        await context.globalState.update(TICKET_KEY, undefined);
      } else if (/^\d+$/.test(v)) {
        await context.globalState.update(TICKET_KEY, parseInt(v, 10));
      } else {
        vscode.window.showErrorMessage("ID invÃ¡lido");
        return;
      }
      refreshStatus(context);
    }),

    vscode.commands.registerCommand("stackyAgents.openWorkbench", () => {
      vscode.env.openExternal(vscode.Uri.parse("http://localhost:5173"));
    }),

    vscode.commands.registerCommand("stackyAgents.runAgent", async () => {
      const ticketId = await ensureTicket(context);
      if (!ticketId) return;
      try {
        const agents = await listAgents();
        const pick = await vscode.window.showQuickPick(
          agents.map(a => ({ label: a.name, description: a.type })),
          { title: "ElegÃ­ un agente" }
        );
        if (!pick) return;

        const editor = vscode.window.activeTextEditor;
        const contextBlocks: any[] = [];
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

        const result = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: `Stacky — ${pick.label}`,
            cancellable: false,
          },
          async (progress) => {
            progress.report({ message: `Ticket ADO-${ticketId} — lanzando…` });
            refreshStatus(context, pick.label);
            const res = await runAgent(pick.description!, ticketId, contextBlocks);
            progress.report({ message: `Run #${res.execution_id} iniciado ✓` });
            return res;
          },
        );

        refreshStatus(context);

        const action = await vscode.window.showInformationMessage(
          `Run lanzado: exec #${result.execution_id}`,
          "Abrir en browser"
        );
        if (action === "Abrir en browser") {
          vscode.env.openExternal(
            vscode.Uri.parse(`http://localhost:5173/?exec=${result.execution_id}`)
          );
        }
      } catch (e: any) {
        refreshStatus(context);
        vscode.window.showErrorMessage(`Stacky run failed: ${e.message}`);
      }
    }),

    vscode.commands.registerCommand("stackyAgents.includeFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
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
      } catch (e: any) {
        vscode.window.showErrorMessage(`FallÃ³: ${e.message}`);
      }
    }),

    vscode.commands.registerCommand("stackyAgents.includeSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
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
      } catch (e: any) {
        vscode.window.showErrorMessage(`FallÃ³: ${e.message}`);
      }
    }),
  );
}

export function deactivate() {
  if (_bridgeServer) {
    _bridgeServer.close();
    _bridgeServer = undefined;
  }
}

