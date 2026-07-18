import React, { type ReactNode } from "react";
import { publishActivity } from "../services/activityCenter"; // Plan 152 F6a
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
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class PageErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("[PageErrorBoundary] render error:", error, info);
    // Plan 152 F6a — deja rastro consultable del error en el Centro de Actividad,
    // aunque el boundary/toast se hayan ido. Sin nav (no sabe la superficie destino).
    publishActivity({
      key: `error:${Date.now()}`,
      kind: "error",
      severity: "error",
      title: "Error en la UI",
      body: String(error?.message || error),
      ts: Date.now(),
    });
  }

  componentDidUpdate(prevProps: Props): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null });
    }
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
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
          <button type="button" className={styles.action} onClick={this.handleRetry}>
            ↻ Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
