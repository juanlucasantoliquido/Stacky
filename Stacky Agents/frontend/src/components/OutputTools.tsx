/*
 * FA-22 + FA-23 — Output tools.
 * Botonera con: traducir output (en/es/pt) + export multi-formato (md/html/slack/email).
 * Aparece en el footer del OutputPanel.
 */
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Exporter, Translator } from "../api/endpoints";
import styles from "./OutputTools.module.css";

interface Props {
  executionId: number;
  agentType: string;
  output: string;
}

export default function OutputTools({ executionId, agentType, output }: Props) {
  const [translatedTo, setTranslatedTo] = useState<string | null>(null);
  const [translatedText, setTranslatedText] = useState<string | null>(null);

  const translate = useMutation({
    mutationFn: (target: "en" | "es" | "pt") =>
      Translator.translate({ target_lang: target, execution_id: executionId }),
    onSuccess: (d) => {
      setTranslatedTo(d.target_lang);
      setTranslatedText(d.output);
    },
  });

  const exportMut = useMutation({
    mutationFn: (fmt: "md" | "html" | "slack" | "email") =>
      Exporter.export({ format: fmt, execution_id: executionId, agent_type: agentType }),
    onSuccess: (r) => {
      const blob = new Blob([r.content], { type: r.mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = r.filename;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  return (
    <div className={styles.box}>
      <div className={styles.group}>
        <span className={styles.label}>traducir:</span>
        {(["es", "en", "pt"] as const).map((l) => (
          <button
            key={l}
            className={styles.btn}
            disabled={translate.isPending}
            onClick={() => translate.mutate(l)}
            title={`Traducir a ${l.toUpperCase()}`}
          >
            {l.toUpperCase()}
            {translate.isPending && translate.variables === l ? "…" : ""}
          </button>
        ))}
      </div>
      <div className={styles.group}>
        <span className={styles.label}>exportar:</span>
        {(["md", "html", "slack", "email"] as const).map((f) => (
          <button
            key={f}
            className={styles.btn}
            disabled={exportMut.isPending}
            onClick={() => exportMut.mutate(f)}
            title={`Descargar como ${f.toUpperCase()}`}
          >
            {f}
          </button>
        ))}
      </div>

      {translatedTo && translatedText && (
        <div className={styles.translation}>
          <header>
            <strong>Traducción → {translatedTo.toUpperCase()}</strong>
            <button
              onClick={() => {
                setTranslatedTo(null);
                setTranslatedText(null);
              }}
              className={styles.close}
            >
              ×
            </button>
          </header>
          <pre>{translatedText}</pre>
        </div>
      )}
    </div>
  );
}
