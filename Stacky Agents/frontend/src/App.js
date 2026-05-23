import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import SystemLogsPage from "./pages/SystemLogsPage";
import PMCommandCenter from "./pages/PMCommandCenter";
import SettingsPage from "./pages/SettingsPage";
import DocsPage from "./pages/DocsPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import TopBar from "./components/TopBar";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import styles from "./App.module.css";
const TAB_PATHS = {
    team: "/",
    tickets: "/tickets",
    pm: "/pm",
    logs: "/logs",
    settings: "/settings",
    docs: "/docs",
    diagnostics: "/diagnostics",
};
function tabFromPath(pathname) {
    const found = Object.entries(TAB_PATHS)
        .find(([, path]) => path !== "/" && pathname.startsWith(path));
    return found?.[0] ?? "team";
}
export default function App() {
    const [tab, setTab] = useState(() => tabFromPath(window.location.pathname));
    const sections = useUiSectionsStore((s) => s.sections);
    const selectTab = (next) => {
        setTab(next);
        const path = TAB_PATHS[next];
        if (window.location.pathname !== path) {
            window.history.pushState({}, "", path);
        }
    };
    useEffect(() => {
        initPreferences();
        initUiSections();
    }, []);
    useEffect(() => {
        const onPopState = () => setTab(tabFromPath(window.location.pathname));
        window.addEventListener("popstate", onPopState);
        return () => window.removeEventListener("popstate", onPopState);
    }, []);
    // Si el usuario tenía seleccionado un tab opcional que acaba de ocultarse,
    // fallback a "team" para no quedar en blanco.
    useEffect(() => {
        if (tab === "pm" && !sections.pm)
            selectTab("team");
        else if (tab === "logs" && !sections.logs)
            selectTab("team");
        else if (tab === "docs" && !sections.docs)
            selectTab("team");
    }, [tab, sections.pm, sections.logs, sections.docs]);
    return (_jsxs("div", { className: styles.appRoot, children: [_jsx(TopBar, { onGoToTeam: () => selectTab("team") }), _jsxs("nav", { className: styles.nav, children: [_jsx("button", { className: `${styles.navTab} ${tab === "team" ? styles.active : ""}`, onClick: () => selectTab("team"), children: "\u26A1 Mi Equipo" }), _jsx("button", { className: `${styles.navTab} ${tab === "tickets" ? styles.active : ""}`, onClick: () => selectTab("tickets"), children: "\uD83D\uDCCB Tickets ADO" }), sections.pm && (_jsx("button", { className: `${styles.navTab} ${tab === "pm" ? styles.active : ""}`, onClick: () => selectTab("pm"), children: "\uD83D\uDCCA PM" })), sections.logs && (_jsx("button", { className: `${styles.navTab} ${tab === "logs" ? styles.active : ""}`, onClick: () => selectTab("logs"), children: "\uD83D\uDD0D System Logs" })), _jsx("button", { className: `${styles.navTab} ${tab === "settings" ? styles.active : ""}`, onClick: () => selectTab("settings"), children: "\u2699\uFE0F Configuraci\u00F3n" }), sections.docs && (_jsx("button", { className: `${styles.navTab} ${tab === "docs" ? styles.active : ""}`, onClick: () => selectTab("docs"), children: "\uD83D\uDCC4 Docs" })), _jsx("button", { className: `${styles.navTab} ${tab === "diagnostics" ? styles.active : ""}`, onClick: () => selectTab("diagnostics"), children: "\uD83E\uDE7A Diagn\u00F3stico" })] }), tab === "team" && _jsx(TeamScreen, {}), tab === "tickets" && _jsx(TicketBoard, {}), tab === "pm" && sections.pm && _jsx(PMCommandCenter, {}), tab === "logs" && sections.logs && _jsx(SystemLogsPage, {}), tab === "settings" && _jsx(SettingsPage, {}), tab === "docs" && sections.docs && _jsx(DocsPage, {}), tab === "diagnostics" && _jsx(DiagnosticsPage, {})] }));
}
