import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import { initPreferences } from "./services/preferences";
import styles from "./App.module.css";
export default function App() {
    const [tab, setTab] = useState("team");
    useEffect(() => {
        initPreferences();
    }, []);
    return (_jsxs("div", { className: styles.appRoot, children: [_jsxs("nav", { className: styles.nav, children: [_jsx("button", { className: `${styles.navTab} ${tab === "team" ? styles.active : ""}`, onClick: () => setTab("team"), children: "\u26A1 Mi Equipo" }), _jsx("button", { className: `${styles.navTab} ${tab === "tickets" ? styles.active : ""}`, onClick: () => setTab("tickets"), children: "\uD83D\uDCCB Tickets ADO" })] }), tab === "team" && _jsx(TeamScreen, {}), tab === "tickets" && _jsx(TicketBoard, {})] }));
}
