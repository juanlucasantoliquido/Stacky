/**
 * extension.ts — X-08: Plugin de Integracion Stacky para VS Code
 *
 * Integra el pipeline Stacky directamente en VS Code:
 *  - Panel lateral con ticket activo, countdown y cola
 *  - Status bar con etapa actual + tiempo restante
 *  - Decoraciones inline en archivos con blast radius warnings
 *  - Comandos de accion rapida (marcar DEV completado, pausar, etc.)
 *  - Polling del dashboard Stacky cada N segundos
 */

import * as vscode from 'vscode';
import * as http from 'http';

// ── Types ────────────────────────────────────────────────────────────────────

interface TicketStatus {
    ticket_id: string;
    stage: string;
    project: string;
    elapsed_min: number | null;
    timeout_min: number | null;
    last_event: string;
}

interface PipelineStatus {
    project: string;
    total_active: number;
    active: TicketStatus[];
    stage_counts: Record<string, number>;
}

interface LivePairContext {
    ticket_id: string;
    stage: string;
    file: string;
    analisis_snippet: string;
    blast_warnings: string[];
    timeout_info: {
        remaining_minutes: number;
        elapsed_minutes: number;
        is_near: boolean;
    };
}

// ── Estado global ─────────────────────────────────────────────────────────────

let _statusBarItem: vscode.StatusBarItem;
let _pollingTimer: ReturnType<typeof setInterval> | undefined;
let _pipelineStatus: PipelineStatus | null = null;
let _activeTicket: TicketStatus | null = null;
let _blastDecorationType: vscode.TextEditorDecorationType;
let _bridgeServer: http.Server | undefined;
let _bridgeStartedAt: number = 0;
const _EXTENSION_VERSION = '1.1.0';

// ── Activacion ────────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
    console.log('[Stacky] Extension activada');

    // Status bar
    _statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    _statusBarItem.command = 'stacky.openDashboard';
    context.subscriptions.push(_statusBarItem);

    // Tipo de decoracion para blast radius
    _blastDecorationType = vscode.window.createTextEditorDecorationType({
        backgroundColor: 'rgba(255, 100, 0, 0.15)',
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: 'rgba(255, 100, 0, 0.5)',
        overviewRulerColor: 'rgba(255, 100, 0, 0.8)',
        overviewRulerLane: vscode.OverviewRulerLane.Right,
        after: {
            contentText: ' ⚠ Blast Radius',
            color: 'rgba(255, 100, 0, 0.8)',
            fontStyle: 'italic',
            fontWeight: 'normal',
        }
    });
    context.subscriptions.push(_blastDecorationType);

    // Registrar comandos
    context.subscriptions.push(
        vscode.commands.registerCommand('stacky.refreshStatus', () => _refresh()),
        vscode.commands.registerCommand('stacky.markDevComplete', () => _markDevComplete()),
        vscode.commands.registerCommand('stacky.pausePipeline', () => _pausePipeline()),
        vscode.commands.registerCommand('stacky.openDashboard', () => _openDashboard()),
        vscode.commands.registerCommand('stacky.showTicketContext', () => _showTicketContext()),
    );

    // Iniciar providers de vistas
    const ticketProvider  = new TicketViewProvider(context);
    const queueProvider   = new QueueViewProvider(context);
    vscode.window.registerTreeDataProvider('stacky.ticketView', ticketProvider);
    vscode.window.registerTreeDataProvider('stacky.queueView', queueProvider);

    // Escuchar cambios de archivo activo
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor) {
                _handleFileChange(editor);
            }
        })
    );

    // Iniciar polling
    _startPolling(ticketProvider, queueProvider);
    _refresh();

    // Iniciar keypress bridge (para auto_enter_daemon.py)
    _startKeypressBridge();
}

export function deactivate() {
    if (_pollingTimer) {
        clearInterval(_pollingTimer);
    }
    if (_bridgeServer) {
        _bridgeServer.close();
        _bridgeServer = undefined;
    }
}

// ── Keypress bridge (para auto_enter_daemon.py) ───────────────────────────────

function _startKeypressBridge() {
    const port = vscode.workspace.getConfiguration('stacky').get<number>('bridgePort') ?? 5051;
    if (!port || port <= 0) {
        console.log('[Stacky] Keypress bridge desactivado (bridgePort=0)');
        return;
    }

    _bridgeServer = http.createServer((req, res) => {
        const method = req.method || '';
        const url    = req.url || '';

        // Defense-in-depth: aunque el listen() bindea a 127.0.0.1, rechazamos
        // explícitamente cualquier conexión que no venga de loopback.
        const remoteAddr = req.socket.remoteAddress ?? '';
        if (!_isLocalhost(remoteAddr)) {
            res.writeHead(403, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: 'Solo se aceptan conexiones locales' }));
            return;
        }

        // CORS para el dashboard en localhost:5050
        res.setHeader('Access-Control-Allow-Origin', 'http://localhost:5050');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
        if (method === 'OPTIONS') {
            res.writeHead(204); res.end(); return;
        }

        // GET /health — liveness probe usado por copilot_bridge.py y watchdog
        if (method === 'GET' && url === '/health') {
            const copilotExt = vscode.extensions.getExtension('GitHub.copilot-chat');
            const copilotVersion = copilotExt?.packageJSON?.version ?? null;
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                ok:                 true,
                version:            _EXTENSION_VERSION,
                copilotChatVersion: copilotVersion,
                uptimeSeconds:      Math.round((Date.now() - _bridgeStartedAt) / 1000),
            }));
            return;
        }

        // Endpoints que consumen body JSON
        if (method !== 'POST') {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: 'not found' }));
            return;
        }

        // POST /approve — reservado para Fase 2 (aprobación selectiva de prompts)
        if (url === '/approve') {
            res.writeHead(501, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                ok:    false,
                error: 'reserved for Fase 2 — use /submit for now',
            }));
            return;
        }

        const isKeypress = url === '/keypress';
        const isSubmit   = url === '/submit';
        const isInvoke   = url === '/invoke';
        if (!isKeypress && !isSubmit && !isInvoke) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: 'not found' }));
            return;
        }

        let body = '';
        req.on('data', (chunk: Buffer) => { body += chunk.toString('utf8'); });
        req.on('end', async () => {
            try {
                const payload = body ? JSON.parse(body) : {};
                let ok = false;

                if (isSubmit) {
                    // /submit → Ctrl+Enter vía comando chat submit (reusa la misma
                    // cadena de candidatos que /keypress ctrl+enter)
                    ok = await _executeBridgeRequest({ key: 'ctrl+enter' });
                } else if (isInvoke) {
                    // /invoke — inyecta el prompt en Copilot Chat y dispara submit.
                    // Portado de la extensión ripley-vscode-bridge (v1.0.0).
                    await _handleInvoke(payload, res);
                    return;
                } else {
                    ok = await _executeBridgeRequest(payload);
                }

                res.writeHead(ok ? 200 : 500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: false, error: String(e) }));
            }
        });
    });

    _bridgeServer.on('error', (err: NodeJS.ErrnoException) => {
        if (err.code === 'EADDRINUSE') {
            console.log(`[Stacky] Puerto ${port} ocupado — probablemente otra instancia ya lo tiene`);
        } else {
            console.error('[Stacky] Bridge error:', err);
        }
        _bridgeServer = undefined;
    });

    // Bind solo a loopback por seguridad
    _bridgeServer.listen(port, '127.0.0.1', () => {
        _bridgeStartedAt = Date.now();
        console.log(`[Stacky] Bridge escuchando en 127.0.0.1:${port} (v${_EXTENSION_VERSION})`);
    });
}

async function _executeBridgeRequest(payload: { key?: string; command?: string }): Promise<boolean> {
    // Escape hatch: comando directo por nombre
    if (payload.command) {
        try {
            await vscode.commands.executeCommand(payload.command);
            return true;
        } catch (_e) {
            return false;
        }
    }

    const key = (payload.key || '').toLowerCase().replace(/\s+/g, '');
    // Mapeo de combinaciones de teclas a comandos probables.
    // Se prueban en orden; el primero que resuelva sin excepción gana.
    const KEY_MAP: Record<string, string[]> = {
        'ctrl+enter': [
            'workbench.action.chat.submit',
            'workbench.action.chat.acceptInput',
            'github.copilot.chat.acceptInput',
        ],
    };
    const candidates = KEY_MAP[key];
    if (!candidates) return false;

    for (const cmd of candidates) {
        try {
            await vscode.commands.executeCommand(cmd);
            return true;
        } catch (_e) {
            // Probar el siguiente
        }
    }
    return false;
}

// ── /invoke: inyección de prompt + submit ────────────────────────────────────

async function _handleInvoke(
    body: Record<string, unknown>,
    res:  http.ServerResponse,
): Promise<void> {
    const prompt          = (body['prompt'] as string | undefined) ?? '';
    const agent           = (body['agent']  as string | undefined) ?? '';
    const newConversation = Boolean(body['new_conversation']);

    if (!prompt) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: 'prompt es requerido' }));
        return;
    }

    try {
        if (newConversation) {
            const freshChatCommands = [
                'workbench.action.chat.newChat',
                'workbench.action.chat.clear',
                'vscode.editorChat.start',
            ];
            for (const cmd of freshChatCommands) {
                try {
                    await vscode.commands.executeCommand(cmd);
                    console.log(`[Stacky] Fresh chat command OK: ${cmd}`);
                    break;
                } catch (_err) {
                    console.log(`[Stacky] Fresh chat command unavailable: ${cmd}`);
                }
            }
            await _sleep(1800);
            try {
                await vscode.commands.executeCommand('workbench.action.chat.open');
            } catch (_err) { /* ignorar si ya está abierto */ }
            await _sleep(700);
            await vscode.env.clipboard.writeText(prompt);
            await vscode.commands.executeCommand('editor.action.clipboardPasteAction');
        } else {
            try {
                await vscode.commands.executeCommand('workbench.action.chat.open', { query: prompt });
            } catch {
                await vscode.commands.executeCommand('workbench.action.chat.open');
                await _sleep(800);
                await vscode.env.clipboard.writeText(prompt);
                await vscode.commands.executeCommand('editor.action.clipboardPasteAction');
            }
        }

        await _sleep(1200);

        // fire-and-forget: no bloquear la respuesta HTTP esperando a la IA
        vscode.commands.executeCommand('workbench.action.chat.submit').then(
            () => console.log(`[Stacky] /invoke chat.submit OK — chars: ${prompt.length}`),
            (err: unknown) => console.error('[Stacky] /invoke chat.submit error:', err),
        );

        console.log(`[Stacky] /invoke enviado — agente: ${agent || '(sin agente)'}, chars: ${prompt.length}`);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, chars: prompt.length, agent }));

    } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`[Stacky] Error en /invoke: ${msg}`);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: msg }));
    }
}

function _isLocalhost(addr: string): boolean {
    return addr === '127.0.0.1'
        || addr === '::1'
        || addr === '::ffff:127.0.0.1'
        || addr === 'localhost';
}

function _sleep(ms: number): Promise<void> {
    return new Promise(r => setTimeout(r, ms));
}

// ── Polling ───────────────────────────────────────────────────────────────────

function _startPolling(ticketProv: TicketViewProvider, queueProv: QueueViewProvider) {
    const config   = vscode.workspace.getConfiguration('stacky');
    const interval = (config.get<number>('pollingInterval') || 30) * 1000;

    _pollingTimer = setInterval(async () => {
        await _fetchAndUpdate(ticketProv, queueProv);
    }, interval);
}

async function _fetchAndUpdate(ticketProv: TicketViewProvider, queueProv: QueueViewProvider) {
    try {
        const status = await _fetchPipelineStatus();
        _pipelineStatus = status;
        _activeTicket   = status.active[0] || null;

        _updateStatusBar();
        ticketProv.refresh(_activeTicket);
        queueProv.refresh(status.active);

        // Actualizar decoraciones del editor activo
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            _handleFileChange(editor);
        }
    } catch (_e) {
        _statusBarItem.text   = '$(warning) Stacky: sin conexion';
        _statusBarItem.tooltip = 'No se puede conectar al dashboard Stacky';
        _statusBarItem.show();
    }
}

async function _refresh() {
    const editor = vscode.window.activeTextEditor;
    const status = await _fetchPipelineStatus().catch(() => null);
    if (status) {
        _pipelineStatus = status;
        _activeTicket   = status.active[0] || null;
        _updateStatusBar();
        if (editor) _handleFileChange(editor);
    }
}

// ── Status bar ────────────────────────────────────────────────────────────────

function _updateStatusBar() {
    if (!_activeTicket) {
        _statusBarItem.text    = '$(check) Stacky: sin tickets activos';
        _statusBarItem.tooltip = 'Abrir dashboard Stacky';
        _statusBarItem.show();
        return;
    }

    const t        = _activeTicket;
    const stageIcon = _stageIcon(t.stage);
    const remaining = t.timeout_min !== null && t.elapsed_min !== null
        ? Math.max(0, t.timeout_min - t.elapsed_min)
        : null;
    const timeStr  = remaining !== null ? ` — ${Math.floor(remaining)}m` : '';
    const isNear   = remaining !== null && remaining < 10;

    _statusBarItem.text      = `${stageIcon} Stacky: #${t.ticket_id} ${t.stage}${timeStr}`;
    _statusBarItem.tooltip   = `Ticket: ${t.ticket_id}\nEtapa: ${t.stage}\nElapsado: ${t.elapsed_min?.toFixed(0)}m`;
    _statusBarItem.backgroundColor = isNear
        ? new vscode.ThemeColor('statusBarItem.warningBackground')
        : undefined;
    _statusBarItem.show();
}

function _stageIcon(stage: string): string {
    if (stage.includes('pm'))      return '$(search)';
    if (stage.includes('dev'))     return '$(code)';
    if (stage.includes('tester') || stage.includes('qa')) return '$(beaker)';
    if (stage.includes('error'))   return '$(error)';
    return '$(sync~spin)';
}

// ── Decoraciones de blast radius ──────────────────────────────────────────────

async function _handleFileChange(editor: vscode.TextEditor) {
    const config = vscode.workspace.getConfiguration('stacky');
    if (!config.get<boolean>('showBlastRadiusDecorations')) {
        return;
    }

    const filename = editor.document.fileName.split(/[/\\]/).pop() || '';
    if (!filename.match(/\.(cs|aspx|vb|sql)$/i)) {
        return;
    }

    try {
        const ctx = await _fetchLivePairContext(filename);
        if (ctx && ctx.blast_warnings.length > 0) {
            // Decorar la primera linea del archivo con el warning
            const decoration: vscode.DecorationOptions = {
                range: new vscode.Range(0, 0, 0, 0),
                hoverMessage: new vscode.MarkdownString(
                    `**Stacky — Blast Radius Warning**\n\n` +
                    ctx.blast_warnings.map(w => `- ${w}`).join('\n')
                ),
            };
            editor.setDecorations(_blastDecorationType, [decoration]);
        } else {
            editor.setDecorations(_blastDecorationType, []);
        }
    } catch (_e) {
        // Silencioso si no hay contexto
    }
}

// ── Comandos ──────────────────────────────────────────────────────────────────

async function _markDevComplete() {
    if (!_activeTicket) {
        vscode.window.showInformationMessage('No hay ticket activo en el pipeline.');
        return;
    }
    const confirm = await vscode.window.showQuickPick(['Si, marcar DEV completado', 'Cancelar'], {
        placeHolder: `Marcar DEV completado para ticket #${_activeTicket.ticket_id}?`,
    });
    if (confirm?.startsWith('Si')) {
        await _postToStacky(`/api/v1/tickets/${_activeTicket.ticket_id}/complete-dev`, {});
        vscode.window.showInformationMessage(`Ticket #${_activeTicket.ticket_id}: DEV marcado como completado.`);
        _refresh();
    }
}

async function _pausePipeline() {
    if (!_activeTicket) {
        vscode.window.showInformationMessage('No hay ticket activo en el pipeline.');
        return;
    }
    await _postToStacky(`/api/v1/tickets/${_activeTicket.ticket_id}/pause`, {});
    vscode.window.showInformationMessage(`Pipeline del ticket #${_activeTicket.ticket_id} pausado.`);
    _refresh();
}

function _openDashboard() {
    const config = vscode.workspace.getConfiguration('stacky');
    const url    = config.get<string>('dashboardUrl') || 'http://localhost:5050';
    vscode.env.openExternal(vscode.Uri.parse(url));
}

async function _showTicketContext() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const filename = editor.document.fileName.split(/[/\\]/).pop() || '';
    const ctx = await _fetchLivePairContext(filename).catch(() => null);

    if (!ctx) {
        vscode.window.showInformationMessage('No hay contexto Stacky para este archivo.');
        return;
    }

    const panel = vscode.window.createWebviewPanel(
        'stackyContext', `Stacky — ${filename}`,
        vscode.ViewColumn.Beside,
        { enableScripts: false }
    );

    const timeoutInfo = ctx.timeout_info
        ? `**Tiempo restante:** ${ctx.timeout_info.remaining_minutes.toFixed(0)} min`
        : '';

    panel.webview.html = `<!DOCTYPE html><html><body style="font-family:Arial;padding:16px">
        <h2>Stacky — Contexto para ${filename}</h2>
        <p><strong>Ticket:</strong> #${ctx.ticket_id} | <strong>Etapa:</strong> ${ctx.stage}</p>
        ${timeoutInfo ? `<p>${timeoutInfo}</p>` : ''}
        ${ctx.blast_warnings.length ? `<h3>⚠️ Blast Radius</h3><ul>${ctx.blast_warnings.map(w => `<li>${w}</li>`).join('')}</ul>` : ''}
        <h3>Analisis Tecnico</h3>
        <pre style="background:#f4f4f4;padding:12px;white-space:pre-wrap">${escapeHtml(ctx.analisis_snippet)}</pre>
    </body></html>`;
}

function escapeHtml(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

function _getBaseUrl(): string {
    const config = vscode.workspace.getConfiguration('stacky');
    return config.get<string>('dashboardUrl') || 'http://localhost:5050';
}

function _fetchPipelineStatus(): Promise<PipelineStatus> {
    const project = vscode.workspace.getConfiguration('stacky').get<string>('project') || 'RIPLEY';
    return _getJson(`${_getBaseUrl()}/api/v1/pipeline/status?project=${project}`);
}

function _fetchLivePairContext(filename: string): Promise<LivePairContext> {
    return _getJson(`${_getBaseUrl()}/api/live-pair/context?file=${encodeURIComponent(filename)}`);
}

function _getJson<T>(url: string): Promise<T> {
    return new Promise((resolve, reject) => {
        http.get(url, { timeout: 5000 }, res => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try { resolve(JSON.parse(data) as T); }
                catch (e) { reject(e); }
            });
        }).on('error', reject).on('timeout', () => reject(new Error('timeout')));
    });
}

function _postToStacky(path: string, body: object): Promise<unknown> {
    const base  = _getBaseUrl();
    const url   = new URL(path, base);
    const json  = JSON.stringify(body);
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: url.hostname,
            port:     Number(url.port) || 5050,
            path:     url.pathname,
            method:   'POST',
            headers:  { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(json) },
            timeout:  5000,
        }, res => {
            let data = '';
            res.on('data', c => data += c);
            res.on('end', () => resolve(JSON.parse(data || '{}')));
        });
        req.on('error', reject);
        req.write(json);
        req.end();
    });
}

// ── TreeDataProviders ─────────────────────────────────────────────────────────

class TicketViewProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private _ticket: TicketStatus | null = null;

    constructor(private context: vscode.ExtensionContext) {}

    refresh(ticket: TicketStatus | null) {
        this._ticket = ticket;
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(el: vscode.TreeItem) { return el; }

    getChildren(): vscode.TreeItem[] {
        if (!this._ticket) {
            return [new vscode.TreeItem('Sin ticket activo')];
        }
        const t = this._ticket;
        const remaining = t.timeout_min !== null && t.elapsed_min !== null
            ? Math.max(0, t.timeout_min - t.elapsed_min)
            : null;
        return [
            _makeItem(`Ticket: #${t.ticket_id}`, 'note'),
            _makeItem(`Etapa: ${t.stage}`, 'play'),
            _makeItem(`Elapsado: ${t.elapsed_min?.toFixed(0) ?? '-'} min`, 'clock'),
            remaining !== null
                ? _makeItem(`Restante: ${remaining.toFixed(0)} min`, remaining < 10 ? 'warning' : 'check')
                : _makeItem('Timeout: desconocido', 'question'),
        ];
    }
}

class QueueViewProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private _tickets: TicketStatus[] = [];

    constructor(private context: vscode.ExtensionContext) {}

    refresh(tickets: TicketStatus[]) {
        this._tickets = tickets;
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(el: vscode.TreeItem) { return el; }

    getChildren(): vscode.TreeItem[] {
        if (this._tickets.length === 0) {
            return [new vscode.TreeItem('Cola vacia')];
        }
        return this._tickets.map(t =>
            _makeItem(`#${t.ticket_id} — ${t.stage}`, 'circle-outline')
        );
    }
}

function _makeItem(label: string, icon: string): vscode.TreeItem {
    const item = new vscode.TreeItem(label);
    item.iconPath = new vscode.ThemeIcon(icon);
    return item;
}
