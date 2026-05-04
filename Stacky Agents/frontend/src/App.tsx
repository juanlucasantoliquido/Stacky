import { useState, useEffect } from "react";
import TeamScreen from "./pages/TeamScreen";
import Workbench from "./pages/Workbench";
import { initPreferences } from "./services/preferences";

type View = "team" | "workbench";

export default function App() {
  const [view, setView] = useState<View>("team");

  useEffect(() => {
    initPreferences();
  }, []);

  if (view === "workbench") {
    return <Workbench onGoToTeam={() => setView("team")} />;
  }

  return <TeamScreen onGoToWorkbench={() => setView("workbench")} />;
}
