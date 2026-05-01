import styles from "./TopBar.module.css";

export default function TopBar() {
  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <span className={styles.logo}>⬡</span>
        Stacky Agents
      </div>
      <div className={styles.project}>
        Project <strong>Strategist_Pacifico</strong>
      </div>
      <div className={styles.actions}>
        <span>dev@local</span>
      </div>
    </header>
  );
}
