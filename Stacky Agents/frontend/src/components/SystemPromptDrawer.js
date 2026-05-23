import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
/*
 * FA-50 — Agent forking inline.
 * Permite ver el system prompt default y editarlo SOLO para este Run.
 * No modifica la definición global del agente. Persiste en metadata como
 * system_prompt_source = "override".
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./SystemPromptDrawer.module.css";
export default function SystemPromptDrawer({ agentType }) {
    const { systemPromptOverride, setSystemPromptOverride } = useWorkbench();
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState("");
    const { data } = useQuery({
        queryKey: ["agent-system-prompt", agentType],
        queryFn: () => Agents.systemPrompt(agentType),
        staleTime: 5 * 60_000,
    });
    useEffect(() => {
        if (!systemPromptOverride && data) {
            setDraft(data.system_prompt);
        }
    }, [data, systemPromptOverride]);
    const isOverridden = systemPromptOverride != null;
    return (_jsxs("div", { className: styles.wrapper, children: [_jsxs("button", { className: styles.toggle, onClick: () => setOpen((v) => !v), title: "Ver / forkear el system prompt para este Run (no modifica el default)", children: ["\u2699 ", isOverridden ? "system prompt: forked" : "system prompt", open ? " ▾" : " ▸"] }), open && (_jsxs("div", { className: styles.panel, children: [_jsx("textarea", { className: styles.editor, value: isOverridden ? systemPromptOverride : draft, onChange: (e) => {
                            setDraft(e.target.value);
                            setSystemPromptOverride(e.target.value);
                        }, rows: 10 }), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.reset, onClick: () => {
                                    setSystemPromptOverride(null);
                                    if (data)
                                        setDraft(data.system_prompt);
                                }, disabled: !isOverridden, children: "Volver al default" }), _jsx("span", { className: styles.hint, children: isOverridden
                                    ? "Override activo. Solo aplica a este Run."
                                    : "Editando = forkear. Sólo afecta este Run." })] })] }))] }));
}
