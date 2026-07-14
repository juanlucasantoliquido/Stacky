import { useEffect, useState } from "react";
import FlowConfigPage from "./FlowConfigPage";
import ConfigTransferPanel from "../components/ConfigTransferPanel";
import ClientProfileEditor from "../components/ClientProfileEditor";
import HarnessFlagsPanel from "../components/HarnessFlagsPanel";
import LocalLlmPlaygroundPanel from "../components/LocalLlmPlaygroundPanel";
import { Webhooks } from "../api/endpoints";
import {
  LOCKED_SECTIONS,
  OPTIONAL_SECTIONS,
  setSectionVisible,
  type OptionalSection,
} from "../services/uiSections";
import { useUiSectionsStore } from "../store/uiSectionsStore";
import { readQueryParam } from "../utils/queryParams";
import styles from "./SettingsPage.module.css";

type SubTab = "flow" | "sections" | "client-profile" | "transfer" | "webhooks" | "harness" | "playground";

const OPTIONAL_LABELS: Record<OptionalSection, { title: string; hint: string }> = {
  pm:   { title: "📊 PM",          hint: "Tablero de Project Management y métricas de sprint." },
  logs: { title: "🔍 System Logs", hint: "Vista cruda de logs estructurados del backend." },
  docs: { title: "📄 Docs",        hint: "Navegador de documentación indexada del proyecto." },
  memory: { title: "Memoria",      hint: "Curacion de memoria colaborativa y hallazgos de validacion." },
};

const LOCKED_LABELS: Record<typeof LOCKED_SECTIONS[number], { title: string; hint: string }> = {
  team:     { title: "⚡ Mi Equipo",      hint: "Pantalla principal de operación." },
  tickets:  { title: "📋 Tickets ADO",    hint: "Tablero de tickets sincronizados con Azure DevOps." },
  settings: { title: "⚙️ Configuración", hint: "Esta misma pantalla — no puede ocultarse." },
};

function SectionsVisibilityPanel() {
  const sections = useUiSectionsStore((s) => s.sections);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<OptionalSection | null>(null);

  const toggle = async (key: OptionalSection, next: boolean) => {
    setError(null);
    setBusy(key);
    try {
      await setSectionVisible(key, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el cambio.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.sectionsPanel}>
      <p className={styles.sectionsIntro}>
        Elegí qué pestañas de la barra superior querés ver. Las marcadas como{" "}
        <span className={styles.lockedBadge}>Obligatoria</span> no se pueden ocultar.
      </p>

      {OPTIONAL_SECTIONS.map((key) => {
        const meta = OPTIONAL_LABELS[key];
        const checked = sections[key];
        const disabled = busy === key;
        return (
          <div key={key} className={styles.row}>
            <div className={styles.rowLabel}>
              <span className={styles.rowTitle}>{meta.title}</span>
              <span className={styles.rowHint}>{meta.hint}</span>
            </div>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(e) => toggle(key, e.target.checked)}
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        );
      })}

      {LOCKED_SECTIONS.map((key) => {
        const meta = LOCKED_LABELS[key];
        return (
          <div key={key} className={styles.row}>
            <div className={styles.rowLabel}>
              <span className={styles.rowTitle}>{meta.title}</span>
              <span className={styles.rowHint}>{meta.hint}</span>
            </div>
            <span className={styles.lockedBadge}>Obligatoria</span>
          </div>
        );
      })}

      {error && <div className={styles.errorText}>{error}</div>}
    </div>
  );
}

export default function SettingsPage() {
  const [sub, setSub] = useState<SubTab>("flow");
  // Plan 129 — deep-link receptor: ?flag=<key> abre el sub-tab Arnes y resalta esa fila.
  const [highlightFlagKey, setHighlightFlagKey] = useState<string | null>(null);

  useEffect(() => {
    const raw = readQueryParam("flag");
    if (!raw) return;
    setSub("harness");
    setHighlightFlagKey(raw);
  }, []);

  return (
    <div className={styles.root}>
      <div className={styles.subTabs}>
        <button
          className={`${styles.subTab} ${sub === "flow" ? styles.active : ""}`}
          onClick={() => setSub("flow")}
        >
          Flujo
        </button>
        <button
          className={`${styles.subTab} ${sub === "sections" ? styles.active : ""}`}
          onClick={() => setSub("sections")}
        >
          Vista / Secciones
        </button>
        <button
          className={`${styles.subTab} ${sub === "client-profile" ? styles.active : ""}`}
          onClick={() => setSub("client-profile")}
        >
          Perfil del cliente
        </button>
        <button
          className={`${styles.subTab} ${sub === "transfer" ? styles.active : ""}`}
          onClick={() => setSub("transfer")}
        >
          Exportar / Importar
        </button>
        <button
          className={`${styles.subTab} ${sub === "webhooks" ? styles.active : ""}`}
          onClick={() => setSub("webhooks")}
        >
          Webhooks
        </button>
        <button
          className={`${styles.subTab} ${sub === "harness" ? styles.active : ""}`}
          onClick={() => setSub("harness")}
        >
          Arnes
        </button>
        <button
          className={`${styles.subTab} ${sub === "playground" ? styles.active : ""}`}
          onClick={() => setSub("playground")}
        >
          Playground IA
        </button>
      </div>

      <div className={styles.content}>
        {sub === "flow" && <FlowConfigPage />}
        {sub === "sections" && <SectionsVisibilityPanel />}
        {sub === "client-profile" && <ClientProfileEditor />}
        {sub === "transfer" && <ConfigTransferPanel />}
        {sub === "webhooks" && <WebhooksPanel />}
        {sub === "harness" && <HarnessFlagsPanel highlightKey={highlightFlagKey} />}
        {sub === "playground" && <LocalLlmPlaygroundPanel />}
      </div>
    </div>
  );
}

type WebhookRow = {
  id: number;
  project: string | null;
  event: string;
  url: string;
  active: boolean;
  format?: "raw" | "teams";
  fires: number;
  last_status: string | null;
};

function WebhooksPanel() {
  const [rows, setRows] = useState<WebhookRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [event, setEvent] = useState("exec.completed");
  const [format, setFormat] = useState<"raw" | "teams">("raw");
  const [secret, setSecret] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    Webhooks.list()
      .then((data) => setRows(data as WebhookRow[]))
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!url.trim()) return;
    setError(null);
    try {
      await Webhooks.create({
        url: url.trim(),
        event,
        format,
        secret: secret.trim() || undefined,
      });
      setUrl("");
      setSecret("");
      load();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    }
  };

  const deactivate = async (id: number) => {
    try {
      await Webhooks.deactivate(id);
      load();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    }
  };

  return (
    <div className={styles.sectionsPanel}>
      <p className={styles.sectionsIntro}>
        Suscribí endpoints para recibir eventos de ejecución (v2 multi-runtime).
      </p>

      <div className={styles.row}>
        <input
          className={styles.inputInline}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/webhook"
        />
      </div>
      <div className={styles.row}>
        <select className={styles.selectInline} value={event} onChange={(e) => setEvent(e.target.value)}>
          <option value="exec.completed">exec.completed</option>
          <option value="exec.failed">exec.failed</option>
          <option value="exec.needs_review">exec.needs_review</option>
        </select>
        <select
          className={styles.selectInline}
          value={format}
          onChange={(e) => setFormat(e.target.value as "raw" | "teams")}
        >
          <option value="raw">raw</option>
          <option value="teams">teams</option>
        </select>
      </div>
      <div className={styles.row}>
        <input
          className={styles.inputInline}
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="Secret opcional (HMAC)"
        />
        <button className={styles.subTab} onClick={create}>Crear</button>
      </div>

      {loading && <div className={styles.rowHint}>Cargando webhooks…</div>}
      {error && <div className={styles.errorText}>{error}</div>}

      {!loading && rows.map((row) => (
        <div key={row.id} className={styles.row}>
          <div className={styles.rowLabel}>
            <span className={styles.rowTitle}>{row.event} · {row.format ?? "raw"}</span>
            <span className={styles.rowHint}>{row.url}</span>
            <span className={styles.rowHint}>fires={row.fires} · last={row.last_status ?? "-"}</span>
          </div>
          <button className={styles.subTab} onClick={() => deactivate(row.id)}>
            Desactivar
          </button>
        </div>
      ))}
    </div>
  );
}
