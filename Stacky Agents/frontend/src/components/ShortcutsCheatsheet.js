import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { DEFAULT_SHORTCUTS } from "../hooks/useKeyboardShortcuts";
import styles from "./ShortcutsCheatsheet.module.css";
const CATEGORY_LABEL = {
    global: "Global",
    execution: "Ejecución",
    navigation: "Navegación",
};
export default function ShortcutsCheatsheet({ open, onClose }) {
    if (!open)
        return null;
    const byCategory = {};
    for (const sc of DEFAULT_SHORTCUTS) {
        (byCategory[sc.category] ||= []).push(sc);
    }
    return (_jsx("div", { className: styles.backdrop, role: "dialog", "aria-modal": "true", onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, children: _jsxs("div", { className: styles.modal, children: [_jsxs("header", { className: styles.header, children: [_jsx("h2", { children: "Atajos de teclado" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, "aria-label": "Cerrar", children: "\u00D7" })] }), _jsx("div", { className: styles.body, children: Object.entries(byCategory).map(([cat, items]) => (_jsxs("section", { className: styles.section, children: [_jsx("h3", { className: styles.sectionTitle, children: CATEGORY_LABEL[cat] ?? cat }), _jsx("table", { className: styles.table, children: _jsx("tbody", { children: items.map((sc) => (_jsxs("tr", { children: [_jsx("td", { className: styles.label, children: sc.label }), _jsx("td", { className: styles.combo, children: sc.combo.split("+").map((part, idx, arr) => (_jsxs("span", { children: [_jsx("kbd", { className: styles.kbd, children: part }), idx < arr.length - 1 && _jsx("span", { className: styles.plus, children: "+" })] }, idx))) })] }, sc.combo))) }) })] }, cat))) })] }) }));
}
