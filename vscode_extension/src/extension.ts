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
}

export function deactivate() {
    if (_pollingTimer) {
        clearInterval(_pollingTimer);
    }
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
