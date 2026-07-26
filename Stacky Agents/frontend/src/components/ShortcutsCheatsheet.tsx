import {
  groupForOverlay,
  isUiShortcutsEnabled,
  LIST_NAV_DISPLAY_DEFS,
  shortcutRegistry,
  visibleShortcuts,
} from "../services/shortcuts";
import { Dialog } from "./ui";
import styles from "./ShortcutsCheatsheet.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Plan 172 F3 — La ayuda de atajos se AUTOGENERA del registro.
 *
 * Antes esto renderizaba una lista hardcodeada de 8 atajos de los cuales 5 no
 * existían en ninguna parte del código: el operador probaba Ctrl+R "re-ejecutar
 * último agente" y no pasaba nada. Una ayuda que miente es peor que no tener
 * ayuda, porque hace dudar de todo lo demás que dice la app.
 *
 * Ahora sale de lo que está REGISTRADO, así que no puede volver a mentir: si un
 * atajo no está en el registro, no se muestra; si está, funciona.
 *
 * Con la flag apagada se listan solo los 3 core — que es exactamente todo lo que
 * anda en ese estado. Veracidad en los dos estados, no solo en el bueno.
 */
export default function ShortcutsCheatsheet({ open, onClose }: Props) {
  if (!open) return null;

  const enabled = isUiShortcutsEnabled();
  const defs = visibleShortcuts(
    [...shortcutRegistry.getAll(), ...(enabled ? LIST_NAV_DISPLAY_DEFS : [])],
    enabled,
  );
  const groups = groupForOverlay(defs);

  // El Dialog del plan 164 ya trae Escape, focus-trap y restauración de foco:
  // repetirlo acá a mano duplicaría (y desincronizaría) ese comportamiento.
  return (
    <Dialog open={open} onClose={onClose} title="Atajos de teclado" ariaLabel="Atajos de teclado">
      <div className={styles.body}>
        {groups.length === 0 && (
          <p className={styles.label}>No hay atajos disponibles en este momento.</p>
        )}
        {groups.map((g) => (
          <section key={g.category} className={styles.section}>
            <h3 className={styles.sectionTitle}>{g.label}</h3>
            <table className={styles.table}>
              <tbody>
                {g.items.map((item) => (
                  <tr key={`${g.category}-${item.comboLabel}-${item.description}`}>
                    <td className={styles.label}>{item.description}</td>
                    <td className={styles.combo}>
                      {item.comboLabel.split("+").map((part, idx, arr) => (
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
    </Dialog>
  );
}
