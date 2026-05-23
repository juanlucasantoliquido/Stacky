import { DEFAULT_SHORTCUTS } from "../hooks/useKeyboardShortcuts";
import styles from "./ShortcutsCheatsheet.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_LABEL = {
  global: "Global",
  execution: "Ejecución",
  navigation: "Navegación",
} as const;

export default function ShortcutsCheatsheet({ open, onClose }: Props) {
  if (!open) return null;

  const byCategory: Record<string, typeof DEFAULT_SHORTCUTS> = {};
  for (const sc of DEFAULT_SHORTCUTS) {
    (byCategory[sc.category] ||= [] as never).push(sc as never);
  }

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.modal}>
        <header className={styles.header}>
          <h2>Atajos de teclado</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </header>
        <div className={styles.body}>
          {Object.entries(byCategory).map(([cat, items]) => (
            <section key={cat} className={styles.section}>
              <h3 className={styles.sectionTitle}>
                {CATEGORY_LABEL[cat as keyof typeof CATEGORY_LABEL] ?? cat}
              </h3>
              <table className={styles.table}>
                <tbody>
                  {items.map((sc) => (
                    <tr key={sc.combo}>
                      <td className={styles.label}>{sc.label}</td>
                      <td className={styles.combo}>
                        {sc.combo.split("+").map((part, idx, arr) => (
                          <span key={idx}>
                            <kbd className={styles.kbd}>{part}</kbd>
                            {idx < arr.length - 1 && <span className={styles.plus}>+</span>}
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
