import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/*
 * Onboarding tour guiado.
 * 4 pasos con spotlight (outline) sobre los componentes clave.
 * Se muestra una sola vez (flag en localStorage).
 */
import { useEffect, useState } from "react";
import styles from "./OnboardingTour.module.css";
const STORAGE_KEY = "stacky-agents-tour-done";
const STEPS = [
    {
        target: '[data-tour="tickets"]',
        title: "1 / 4 — Tickets",
        body: "Elegí el ticket sobre el que vas a trabajar. Podés buscar por ID o por texto.",
        position: "right",
    },
    {
        target: '[data-tour="agents"]',
        title: "2 / 4 — Agentes",
        body: "Elegí qué agente querés correr. Podés hacerlo en cualquier orden — no hay pipeline obligatorio.",
        position: "right",
    },
    {
        target: '[data-tour="editor"]',
        title: "3 / 4 — Editor de contexto",
        body: "Esto es lo que el agente va a recibir. Podés editar, agregar bloques o sacar los que no necesitás.",
        position: "bottom",
    },
    {
        target: '[data-tour="run"]',
        title: "4 / 4 — Run",
        body: "Cuando el contexto está listo, hacé click. El output aparece a la derecha. ¡Eso es todo!",
        position: "left",
    },
];
export default function OnboardingTour() {
    const [step, setStep] = useState(null);
    useEffect(() => {
        const done = localStorage.getItem(STORAGE_KEY);
        if (!done)
            setStep(0);
    }, []);
    if (step === null)
        return null;
    const current = STEPS[step];
    const isLast = step === STEPS.length - 1;
    const next = () => {
        if (isLast) {
            localStorage.setItem(STORAGE_KEY, "1");
            setStep(null);
        }
        else {
            setStep((s) => (s ?? 0) + 1);
        }
    };
    const skip = () => {
        localStorage.setItem(STORAGE_KEY, "1");
        setStep(null);
    };
    return (_jsxs(_Fragment, { children: [_jsx("div", { className: styles.overlay, onClick: skip }), _jsxs("div", { className: `${styles.card} ${styles[current.position]}`, children: [_jsx("h3", { className: styles.title, children: current.title }), _jsx("p", { className: styles.body, children: current.body }), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.skip, onClick: skip, children: "Skip" }), _jsx("button", { className: styles.next, onClick: next, children: isLast ? "Empezar →" : "Siguiente →" })] }), _jsx("div", { className: styles.dots, children: STEPS.map((_, i) => (_jsx("span", { className: `${styles.dot} ${i === step ? styles.active : ""}` }, i))) })] })] }));
}
