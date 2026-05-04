import { useEffect } from "react";
import TeamScreen from "./pages/TeamScreen";
import { initPreferences } from "./services/preferences";

export default function App() {
  useEffect(() => {
    initPreferences();
  }, []);

  return <TeamScreen />;
}
