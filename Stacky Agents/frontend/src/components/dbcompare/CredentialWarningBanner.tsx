// Plan 157 F3/F4 (punto d) — banner fijo de advertencia al manejar credenciales.
import styles from "./dbcompare.module.css";

/** Texto EXACTO del plan (§3.2.d / F4). No editar sin actualizar el plan. */
export function CredentialWarningBanner() {
  return (
    <div className={styles.credentialBanner} role="note">
      ⚠️ Estás manejando credenciales de base de datos. Stacky las guarda cifradas en el
      Administrador de credenciales de Windows y nunca las escribe en logs ni en disco en
      texto plano. El archivo se lee localmente; nada se envía a servicios externos.
    </div>
  );
}

export default CredentialWarningBanner;
