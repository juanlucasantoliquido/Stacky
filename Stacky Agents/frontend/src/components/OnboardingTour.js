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
        target: "body",
        title: "1 / 6 — Bienvenido a Stacky Agents",
        body: "Tu equipo de agentes IA para cerrar tickets más rápido. Te muestro los puntos clave en 6 pasos.",
        position: "bottom",
    },
    {
        target: '[data-tour="agents"]',
        title: "2 / 6 — Tu Equipo",
        body: "Estos son tus agentes — pensálos como empleados. Cada uno hace una cosa: Business, Functional, Technical, Developer, QA.",
        position: "right",
    },
    {
        target: '[data-tour="tickets"]',
        title: "3 / 6 — Tickets",
        body: "Elegí el ticket sobre el que vas a trabajar. Podés buscar por ID o por texto.",
        position: "right",
    },
    {
        target: '[data-tour="editor"]',
        title: "4 / 6 — Editor de contexto",
        body: "Esto es lo que el agente va a recibir. Podés editar, agregar bloques o sacar los que no necesitás.",
        position: "bottom",
    },
    {
        target: '[data-tour="run"]',
        title: "5 / 6 — Run",
        body: "Cuando el contexto está listo, hacé click. El output aparece a la derecha.",
        position: "left",
    },
    {
        target: "body",
        title: "6 / 6 — Ctrl+K es tu amigo",
        body: "Apretá Ctrl+K en cualquier momento para buscar tickets, agentes, packs o saltar entre pantallas con el teclado. Probá ahora.",
        position: "bottom",
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
