import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * FA-22 + FA-23 — Output tools.
 * Botonera con: traducir output (en/es/pt) + export multi-formato (md/html/slack/email).
 * Aparece en el footer del OutputPanel.
 */
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Exporter, Translator } from "../api/endpoints";
import styles from "./OutputTools.module.css";
export default function OutputTools({ executionId, agentType, output }) {
    const [translatedTo, setTranslatedTo] = useState(null);
    const [translatedText, setTranslatedText] = useState(null);
    const translate = useMutation({
        mutationFn: (target) => Translator.translate({ target_lang: target, execution_id: executionId }),
        onSuccess: (d) => {
            setTranslatedTo(d.target_lang);
            setTranslatedText(d.output);
        },
    });
    const exportMut = useMutation({
        mutationFn: (fmt) => Exporter.export({ format: fmt, execution_id: executionId, agent_type: agentType }),
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
    return (_jsxs("div", { className: styles.box, children: [_jsxs("div", { className: styles.group, children: [_jsx("span", { className: styles.label, children: "traducir:" }), ["es", "en", "pt"].map((l) => (_jsxs("button", { className: styles.btn, disabled: translate.isPending, onClick: () => translate.mutate(l), title: `Traducir a ${l.toUpperCase()}`, children: [l.toUpperCase(), translate.isPending && translate.variables === l ? "…" : ""] }, l)))] }), _jsxs("div", { className: styles.group, children: [_jsx("span", { className: styles.label, children: "exportar:" }), ["md", "html", "slack", "email"].map((f) => (_jsx("button", { className: styles.btn, disabled: exportMut.isPending, onClick: () => exportMut.mutate(f), title: `Descargar como ${f.toUpperCase()}`, children: f }, f)))] }), translatedTo && translatedText && (_jsxs("div", { className: styles.translation, children: [_jsxs("header", { children: [_jsxs("strong", { children: ["Traducci\u00F3n \u2192 ", translatedTo.toUpperCase()] }), _jsx("button", { onClick: () => {
                                    setTranslatedTo(null);
                                    setTranslatedText(null);
                                }, className: styles.close, children: "\u00D7" })] }), _jsx("pre", { children: translatedText })] }))] }));
}
