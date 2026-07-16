/**
 * LocalLlmPlaygroundPanel (Plan 106 — mejora aditiva "Playground IA local")
 *
 * Panel para PROBAR el modelo local desde la UI:
 * - Selector de modelos poblado desde GET /api/llm/local-models (current preseleccionado).
 * - Textarea de prompt libre + system opcional.
 * - Botón "Probar" → POST /api/llm/playground.
 * - Área de resultado + estado de conexión.
 *
 * Solo activo si la flag está ON: si local-models responde 404, el panel muestra
 * el aviso de "apagado" y no permite probar (HITL: nunca 500, nunca bloqueo).
 */
import { useEffect, useState } from "react";
import { LocalLlmApi } from "../api/endpoints";
import EgressSentinelBlock from "./EgressSentinelBlock";
import type { EgressSentinelData } from "./EgressSentinelBlock";
import styles from "./LocalLlmPlaygroundPanel.module.css";

export default function LocalLlmPlaygroundPanel() {
  // null = todavía no se supo; false = flag OFF (404) → panel deshabilitado; true = disponible.
  const [available, setAvailable] = useState<boolean | null>(null);
  const [reachable, setReachable] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [system, setSystem] = useState("");
  const [showSystem, setShowSystem] = useState(false);

  const [loadingModels, setLoadingModels] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [resultModel, setResultModel] = useState<string | null>(null);

  // Plan 121 — Centinela de egreso: escaneo on-demand pre-flight.
  const [scanText, setScanText] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<EgressSentinelData | null>(null);

  const loadModels = () => {
    setLoadingModels(true);
    setError(null);
    LocalLlmApi.localModels()
      .then((res) => {
        setAvailable(true);
        setReachable(res.reachable === true);
        setModels(res.models ?? []);
        // Preseleccionar el modelo default; si no está en la lista, agregarlo como opción.
        const current = res.current ?? "";
        setModel((prev) => prev || current);
      })
      .catch(() => {
        // 404 => flag OFF; cualquier otro error de red => tratamos como no disponible.
        setAvailable(false);
      })
      .finally(() => setLoadingModels(false));
  };

  useEffect(() => {
    loadModels();
  }, []);

  const handleRun = async () => {
    if (!prompt.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setResultModel(null);
    try {
      const res = await LocalLlmApi.playground({
        prompt,
        model: model || undefined,
        system: showSystem && system.trim() ? system : undefined,
      });
      setResult(res.response ?? "");
      setResultModel(res.model ?? null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error desconocido";
      setError(`No se pudo probar el modelo local: ${msg}`);
    } finally {
      setRunning(false);
    }
  };

  const handleScan = async () => {
    if (!scanText.trim()) return;
    setScanning(true);
    setScanError(null);
    setScanResult(null);
    try {
      const res = await LocalLlmApi.scanEgress({ text: scanText, kind: "manual" });
      setScanResult({
        status: res.status,
        findings: res.findings ?? [],
        deterministic_classes: res.deterministic_classes ?? [],
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error desconocido";
      setScanError(
        msg.includes("egress_sentinel_disabled")
          ? 'Activá "Centinela de egreso (IA local)" en Configuración → Arnés'
          : msg,
      );
    } finally {
      setScanning(false);
    }
  };

  if (available === false) {
    return (
      <div className={styles.panel}>
        <p className={styles.intro}>
          El modelo local está apagado. Activá la flag{" "}
          <strong>Modelo local (Ollama/LM Studio/vLLM)</strong> en la pestaña{" "}
          <strong>Arnes</strong> y configurá el endpoint para usar el Playground.
        </p>
      </div>
    );
  }

  // El modelo actual puede no estar en la lista devuelta (server caído): lo mostramos igual.
  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;

  return (
    <div className={styles.panel}>
      <p className={styles.intro}>
        Probá tu modelo de IA local con un prompt libre. Elegí entre los modelos
        instalados en tu servidor. Solo analiza y responde: no ejecuta ni edita nada
        (human-in-the-loop).
      </p>

      <div className={styles.status}>
        <span className={reachable ? styles.dotOk : styles.dotOff} />
        <span className={styles.statusText}>
          {loadingModels
            ? "Consultando servidor local…"
            : reachable
              ? `Servidor local conectado · ${models.length} modelo(s)`
              : "Servidor local sin conexión"}
        </span>
        <button className={styles.linkBtn} onClick={loadModels} disabled={loadingModels}>
          Refrescar
        </button>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Modelo</label>
        <select
          className={styles.select}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          disabled={loadingModels}
        >
          {modelOptions.length === 0 && <option value="">(sin modelos detectados)</option>}
          {modelOptions.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Prompt</label>
        <textarea
          className={styles.textarea}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Escribí lo que querés preguntarle al modelo local…"
          rows={5}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.toggleLine}>
          <input
            type="checkbox"
            checked={showSystem}
            onChange={(e) => setShowSystem(e.target.checked)}
          />
          <span>System prompt personalizado (opcional)</span>
        </label>
        {showSystem && (
          <textarea
            className={styles.textarea}
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            placeholder="Instrucción de sistema (dejalo vacío para usar la genérica con reglas HITL)…"
            rows={3}
          />
        )}
      </div>

      <div className={styles.actions}>
        <button
          className={styles.primaryBtn}
          onClick={() => void handleRun()}
          disabled={running || !prompt.trim()}
        >
          {running ? "Probando…" : "Probar"}
        </button>
      </div>

      {error && <div className={styles.errorText}>{error}</div>}

      {result !== null && (
        <div className={styles.result}>
          <div className={styles.resultHead}>
            Respuesta{resultModel ? ` · ${resultModel}` : ""}
          </div>
          <pre className={styles.resultBody}>{result || "(respuesta vacía)"}</pre>
        </div>
      )}

      {/* Plan 121 — Centinela de egreso: escaneo on-demand pre-flight (HITL). */}
      <div className={styles.field}>
        <label className={styles.label}>Centinela de egreso</label>
        <p className={styles.intro}>
          Pegá un texto y escaneálo ANTES de mandarlo: la IA local busca contraseñas,
          claves u otros datos sensibles, incluso narrados en lenguaje natural.
        </p>
        <textarea
          className={styles.textarea}
          value={scanText}
          onChange={(e) => setScanText(e.target.value)}
          placeholder="Pegá acá el texto que querés revisar antes de enviarlo…"
          rows={4}
        />
        <div className={styles.actions}>
          <button
            className={styles.primaryBtn}
            onClick={() => void handleScan()}
            disabled={scanning || !scanText.trim()}
          >
            {scanning ? "Escaneando…" : "Escanear antes de enviar"}
          </button>
        </div>
        {scanError && <div className={styles.errorText}>{scanError}</div>}
        <EgressSentinelBlock sentinel={scanResult} />
      </div>
    </div>
  );
}
