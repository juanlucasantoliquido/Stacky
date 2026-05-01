import { useAutoFillBlocks } from "../hooks/useAutoFillBlocks";
import AgentSelector from "../components/AgentSelector";
import ExecutionHistory from "../components/ExecutionHistory";
import InputContextEditor from "../components/InputContextEditor";
import LogsPanel from "../components/LogsPanel";
import OutputPanel from "../components/OutputPanel";
import TicketSelector from "../components/TicketSelector";
import TopBar from "../components/TopBar";
import styles from "./Workbench.module.css";

export default function Workbench() {
  useAutoFillBlocks();

  return (
    <div className={styles.app}>
      <TopBar />
      <div className={styles.body}>
        <aside className={styles.left}>
          <TicketSelector />
          <AgentSelector />
        </aside>
        <main className={styles.center}>
          <InputContextEditor />
        </main>
        <aside className={styles.right}>
          <OutputPanel />
          <LogsPanel />
          <ExecutionHistory />
        </aside>
      </div>
    </div>
  );
}
