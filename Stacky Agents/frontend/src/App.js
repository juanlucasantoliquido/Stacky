import { jsx as _jsx } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import TeamScreen from "./pages/TeamScreen";
import Workbench from "./pages/Workbench";
import { initPreferences } from "./services/preferences";
export default function App() {
    const [view, setView] = useState("team");
    useEffect(() => {
        initPreferences();
    }, []);
    if (view === "workbench") {
        return _jsx(Workbench, { onGoToTeam: () => setView("team") });
    }
    return _jsx(TeamScreen, { onGoToWorkbench: () => setView("workbench") });
}
