import React, { type ReactNode } from "react";
import { publishActivity } from "../services/activityCenter"; // Plan 152 F6a
import { copyText } from "../services/copyService"; // Plan 266 F5 — C25: único punto legítimo de escritura al portapapeles (copyDebtRatchet)
import {
  buildActivityBody,
  buildDiagnosticText,
  firstComponentFromStack,
} from "./errorBoundaryDiagnostics";
import styles from "./PageErrorBoundary.module.css";

/**
 * Boundary a nivel PÁGINA (plan 135 F4). Patrón de la casa: copia de
 * NodeErrorBoundary (TicketGraphView.jsx:244) elevada a las 14 páginas de
 * App.tsx. Un throw en el render de un tab ya no blanquea toda la app:
 * TopBar/nav/HealthBanner/CodexConsoleDock/ActiveRunsPanel siguen vivos.
 * Se resetea con el botón Reintentar o al cambiar de tab (resetKey).
 */
interface Props {
  /** Cambiarla (p. ej. el tab activo) resetea el boundary automáticamente. */
  resetKey: string;
  children: ReactNode;
  /** Plan 266 F5 — nombre legible de la superficie (opcional, no rompe los
   * call-sites existentes). Si falta, se usa resetKey (ya es el tab activo). */
  surface?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  componentName: string | null;
  stack: string | null;
}

export default class PageErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null, componentName: null, stack: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, componentName: null, stack: null };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("[PageErrorBoundary] render error:", error, info);
    const stack = info?.componentStack ?? null;
    const componentName = firstComponentFromStack(stack);
    this.setState({ componentName, stack });
    // Plan 152 F6a — deja rastro consultable del error en el Centro de Actividad,
    // aunque el boundary/toast se hayan ido.
    // Plan 266 F5 — ahora incluye superficie + componente (antes solo el mensaje).
    publishActivity({
      key: `error:${Date.now()}`,
      kind: "error",
      severity: "error",
      title: "Error en la UI",
      body: buildActivityBody(
        this.props.surface ?? this.props.resetKey,
        componentName,
        String(error?.message || error),
      ),
      ts: Date.now(),
    });
  }

  componentDidUpdate(prevProps: Props): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null, componentName: null, stack: null });
    }
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null, componentName: null, stack: null });
  };

  handleCopy = (): void => {
    void copyText(
      buildDiagnosticText({
        surface: this.props.surface ?? this.props.resetKey,
        message: String(this.state.error?.message || this.state.error || ""),
        componentName: this.state.componentName,
        stack: this.state.stack,
        iso: new Date().toISOString(),
      }),
    );
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className={styles.root} role="alert">
          <div className={styles.icon} aria-hidden="true">💥</div>
          <h2 className={styles.title}>Esta pestaña falló al renderizar</h2>
          <p className={styles.message}>
            {this.state.error?.message || "Error inesperado"}
          </p>
          <p className={styles.hint}>
            El resto de la aplicación sigue funcionando. Podés reintentar o cambiar de pestaña.
          </p>
          <p className={styles.origin}>
            {this.props.surface ?? this.props.resetKey}
            {this.state.componentName ? ` · ${this.state.componentName}` : ""}
          </p>
          {this.state.stack && (
            <details className={styles.details}>
              <summary>Detalle técnico</summary>
              <pre className={styles.stack}>{this.state.stack}</pre>
            </details>
          )}
          <button type="button" className={styles.action} onClick={this.handleRetry}>
            ↻ Reintentar
          </button>
          <button type="button" className={styles.secondaryAction} onClick={this.handleCopy}>
            ⧉ Copiar diagnóstico
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
