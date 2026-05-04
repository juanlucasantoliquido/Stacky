import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import styles from "./TokenCounter.module.css";
export default function TokenCounter({ current, max }) {
    const pct = Math.min(1, current / max);
    const color = pct < 0.6 ? "muted" : pct < 0.85 ? "warn" : "danger";
    return (_jsxs("div", { className: styles.box, children: [_jsxs("span", { className: `${styles.text} ${styles[color]}`, children: [format(current), " / ", format(max), " tokens"] }), _jsx("div", { className: styles.bar, children: _jsx("div", { className: `${styles.fill} ${styles[color]}`, style: { width: `${pct * 100}%` } }) })] }));
}
function format(n) {
    if (n >= 1000)
        return `${(n / 1000).toFixed(1)}k`;
    return String(n);
}
