/**
 * CopyAsButton.tsx — Plan 194 F3. Grupo inline "Copiar: …" (SIN popover/dropdown).
 * Componente chico y tonto: llama a los builders puros de copyFormats, usa
 * copyService (fallback + copia rica), muestra el Toast de la casa y respeta la
 * flag STACKY_COPY_EXPORT_ENABLED. Toda la lógica está cubierta por F1/F2; esto
 * es una cáscara fina verificada con tsc + smoke (G4).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HarnessFlags } from "../api/endpoints";
import {
  copyText,
  copyRichText,
  resolveCopyExportEnabled,
  COPY_TOAST_SUCCESS,
  COPY_TOAST_ERROR,
  type CopySuccessMethod,
} from "../services/copyService";
import { Button } from "./ui";
import Toast, { type ToastState } from "./Toast";
import styles from "./CopyAsButton.module.css";

export interface CopyAsOption {
  /** Texto EXACTO del botón: "Markdown" | "CSV" | "Texto" | "Tabla (ADO)" | "Enlace". */
  label: string;
  /** Formateador puro (text/plain); se evalúa recién al click. */
  build: () => string;
  /** §4.11: presente ⇒ copia enriquecida vía copyRichText(buildHtml(), build()). */
  buildHtml?: () => string;
  /** Override del body del toast de éxito (§4.3); ausente ⇒ COPY_TOAST_SUCCESS. */
  successBody?: (method: CopySuccessMethod) => string;
}

export default function CopyAsButton({ options }: { options: CopyAsOption[] }): JSX.Element | null {
  const flagsQ = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
    staleTime: 60_000,
  });
  const [toast, setToast] = useState<ToastState | null>(null);
  const [busy, setBusy] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async (o: CopyAsOption) => {
    setBusy(true);
    try {
      const r = o.buildHtml ? await copyRichText(o.buildHtml(), o.build()) : await copyText(o.build());
      if (r.ok) {
        setToast({ variant: "success", body: o.successBody ? o.successBody(r.method) : COPY_TOAST_SUCCESS });
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setToast(null), 4000);
      } else if (r.reason !== "empty") {
        setToast({ variant: "error", body: COPY_TOAST_ERROR });
      }
      // reason === "empty" ⇒ sin toast (§4.3)
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  if (!resolveCopyExportEnabled(flagsQ.data?.flags)) return null;

  return (
    <span className={styles.group} role="group" aria-label="Copiar como">
      <span className={styles.prefix}>Copiar:</span>
      {options.map((o) => (
        <Button key={o.label} variant="ghost" size="sm" disabled={busy} onClick={() => void handleCopy(o)}>
          {o.label}
        </Button>
      ))}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </span>
  );
}
