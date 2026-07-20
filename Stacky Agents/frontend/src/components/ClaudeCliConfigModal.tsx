import React, { useEffect, useState } from "react";
import { Terminal, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { ClaudeCli, type ClaudeSessionStatus, type ClaudeTestResult } from "../api/endpoints";
import { Dialog } from "./ui";
import styles from "./ClaudeCliConfigModal.module.css";

interface ClaudeCliConfigModalProps {
  onClose: () => void;
  /** Se llama cuando la config queda lista (binario OK + sesión activa). */
  onConfigured?: () => void;
}

/**
 * Configuración "fácil" de Claude Code CLI.
 *
 * Al abrir, sondea el binario (`claude --version`) y el estado de sesión
 * (`claude auth status`). Permite:
 *   - ajustar/detectar la ruta del binario,
 *   - iniciar sesión vía OAuth (`claude auth login`, abre el navegador),
 *   - cerrar sesión,
 *   - guardar la ruta del binario en el .env del backend.
 *
 * El runtime queda "listo" cuando el binario responde versión Y la sesión
 * está activa.
 */
export default function ClaudeCliConfigModal({ onClose, onConfigured }: ClaudeCliConfigModalProps) {
  const [binPath, setBinPath] = useState("");
  const [test, setTest] = useState<ClaudeTestResult | null>(null);
  const [session, setSession] = useState<ClaudeSessionStatus | null>(null);
  const [probing, setProbing] = useState(true);
  const [testing, setTesting] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ready = Boolean(test?.ok && session?.logged_in);

  async function probe(showSpinner = true) {
    if (showSpinner) setProbing(true);
    setError(null);
    try {
      const [t, s] = await Promise.all([
        ClaudeCli.test(binPath || undefined),
        ClaudeCli.session(),
      ]);
      setTest(t);
      setSession(s);
      if (!binPath && t.bin) setBinPath(t.bin);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProbing(false);
    }
  }

  useEffect(() => {
    void probe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleTest() {
    setTesting(true);
    setNotice(null);
    setError(null);
    try {
      const t = await ClaudeCli.test(binPath || undefined);
      setTest(t);
      if (t.bin) setBinPath(t.bin);
      if (!t.ok) setError(t.error ?? "No se pudo verificar el binario.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  }

  async function handleLogin() {
    setLoggingIn(true);
    setNotice("Abriendo el navegador para iniciar sesión… completá el login y volvé acá.");
    setError(null);
    try {
      const r = await ClaudeCli.login(binPath || undefined);
      if (!r.ok) {
        setError(r.error ?? "El login no se completó.");
      } else {
        setNotice("Sesión iniciada correctamente.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoggingIn(false);
      await probe(false);
    }
  }

  async function handleLogout() {
    setError(null);
    setNotice(null);
    try {
      await ClaudeCli.logout();
      setNotice("Sesión cerrada.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      await probe(false);
    }
  }

  async function handleSaveAndClose() {
    setSaving(true);
    setError(null);
    try {
      // Solo persistimos una ruta explícita si el usuario la editó respecto al
      // binario autodetectado (no guardamos la ruta autodetectada para no
      // hardcodear rutas de winget con sufijo aleatorio en el .env).
      if (binPath && test?.bin && binPath !== test.bin) {
        await ClaudeCli.saveConfig({ CLAUDE_CODE_CLI_BIN: binPath });
      }
      onConfigured?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <Dialog
      open
      onClose={onClose}
      closeGuard={{ dirty: false, busy: saving }}
      ariaLabel="Configurar Claude Code CLI"
      size="md"
    >
        <div className={styles.header}>
          <Terminal size={18} strokeWidth={2.2} />
          <div className={styles.headerText}>
            <span className={styles.title}>Configurar Claude Code</span>
            <span className={styles.subtitle}>
              Necesario para ejecutar agentes con el runtime Claude Code CLI.
            </span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
        </div>

        {probing ? (
          <div className={styles.probing}>
            <Loader2 size={18} className={styles.spin} />
            <span>Detectando Claude Code…</span>
          </div>
        ) : (
          <div className={styles.body}>
            {/* Paso 1 — Binario */}
            <section className={styles.step}>
              <div className={styles.stepHead}>
                <span className={styles.stepNum}>1</span>
                <span className={styles.stepTitle}>Binario de Claude Code</span>
                {test?.ok ? (
                  <span className={styles.okPill}><CheckCircle2 size={14} /> {test.version}</span>
                ) : (
                  <span className={styles.failPill}><XCircle size={14} /> no encontrado</span>
                )}
              </div>
              <div className={styles.binRow}>
                <input
                  className={styles.binInput}
                  type="text"
                  placeholder="claude (autodetectado) o ruta completa al ejecutable"
                  value={binPath}
                  onChange={(e) => setBinPath(e.target.value)}
                  spellCheck={false}
                />
                <button className={styles.secondaryBtn} onClick={handleTest} disabled={testing}>
                  {testing ? "Probando…" : "Probar"}
                </button>
              </div>
              {!test?.ok && (
                <p className={styles.hint}>
                  Instalá Claude Code con{" "}
                  <code>npm install -g @anthropic-ai/claude-code</code> o{" "}
                  <code>winget install Anthropic.ClaudeCode</code>, o pegá la ruta completa al ejecutable.
                </p>
              )}
            </section>

            {/* Paso 2 — Sesión */}
            <section className={styles.step}>
              <div className={styles.stepHead}>
                <span className={styles.stepNum}>2</span>
                <span className={styles.stepTitle}>Sesión de Anthropic</span>
                {session?.logged_in ? (
                  <span className={styles.okPill}><CheckCircle2 size={14} /> conectado</span>
                ) : (
                  <span className={styles.failPill}><XCircle size={14} /> sin sesión</span>
                )}
              </div>
              {session?.logged_in ? (
                <div className={styles.sessionInfo}>
                  <div>
                    <strong>{session.email}</strong>
                    {session.org_name && <span> · {session.org_name}</span>}
                    {session.subscription_type && (
                      <span className={styles.subBadge}>{session.subscription_type}</span>
                    )}
                  </div>
                  <button className={styles.linkBtn} onClick={handleLogout}>
                    Cerrar sesión
                  </button>
                </div>
              ) : (
                <div className={styles.sessionInfo}>
                  <span className={styles.hint}>
                    Iniciá sesión con tu cuenta o suscripción de Anthropic.
                  </span>
                  <button
                    className={styles.primaryBtn}
                    onClick={handleLogin}
                    disabled={loggingIn || !test?.ok}
                  >
                    {loggingIn ? (
                      <><Loader2 size={14} className={styles.spin} /> Esperando…</>
                    ) : (
                      "Iniciar sesión"
                    )}
                  </button>
                </div>
              )}
            </section>

            {notice && <div className={styles.notice}>{notice}</div>}
            {error && (
              <div className={styles.error} role="alert">
                <span>⚠️ {error}</span>
              </div>
            )}
          </div>
        )}

        <div className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
          <button
            className={styles.doneBtn}
            onClick={handleSaveAndClose}
            disabled={!ready || saving}
            title={ready ? "Listo" : "Necesitás binario válido y sesión activa"}
          >
            {saving ? "Guardando…" : ready ? "✓ Listo" : "Completá los pasos"}
          </button>
        </div>
    </Dialog>
  );
}
