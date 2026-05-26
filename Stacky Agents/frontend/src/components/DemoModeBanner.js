import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { isDemoMode, setDemoMode, subscribeDemoMode } from "../store/demoMode";
import styles from "./DemoModeBanner.module.css";
export default function DemoModeBanner() {
    const [enabled, setEnabled] = useState(isDemoMode());
    useEffect(() => {
        return subscribeDemoMode(setEnabled);
    }, []);
    if (!enabled)
        return null;
    return (_jsxs("div", { className: styles.banner, role: "status", children: [_jsx("span", { className: styles.dots, "aria-hidden": "true", children: "D E M O" }), _jsx("span", { className: styles.label, children: "MODO DEMO \u2014 outputs cacheados, sin riesgo de filtrar data real" }), _jsx("button", { className: styles.exitBtn, onClick: () => setDemoMode(false), title: "Salir del modo demo", children: "Salir" })] }));
}
export function DemoModeToggle() {
    const [enabled, setEnabled] = useState(isDemoMode());
    useEffect(() => subscribeDemoMode(setEnabled), []);
    return (_jsxs("label", { className: styles.toggle, children: [_jsx("input", { type: "checkbox", checked: enabled, onChange: (e) => setDemoMode(e.target.checked) }), _jsx("span", { children: "Modo Demo" })] }));
}
