// Plan 122-126 — sección "Configuración" del Comparador de BD: reúne el master
// (STACKY_DB_COMPARE_ENABLED), el timeout de conexión, el toggle de paridad de
// datos y el cap de filas — todo lo que hoy vive disperso en el panel genérico
// de flags del arnés — para que el operador configure el feature completo sin
// salir de este tab. Reusa GET/PUT /api/harness-flags (HarnessFlags de
// api/endpoints.ts): NO hay almacenamiento propio, esta sección es un
// subconjunto filtrado + editable del mismo registry (services/harness_flags.py).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HarnessFlags, type HarnessFlagView } from "../../api/endpoints";
import { pickDbCompareSettings, validateIntSetting } from "./dbCompareSettingsLogic";
import styles from "./dbcompare.module.css";

function IntSetting({
  flag,
  onSave,
  saving,
}: {
  flag: HarnessFlagView;
  onSave: (key: string, value: number) => void;
  saving: boolean;
}) {
  const [text, setText] = useState(String(flag.value));
  const [error, setError] = useState<string | null>(null);

  const commit = () => {
    const r = validateIntSetting(text, flag.min_value, flag.max_value);
    if (!r.ok || r.value === undefined) {
      setError(r.error ?? "Valor inválido.");
      return;
    }
    setError(null);
    if (r.value !== flag.value) onSave(flag.key, r.value);
  };

  return (
    <label>
      {flag.label}
      <input
        type="number"
        value={text}
        disabled={saving}
        min={flag.min_value ?? undefined}
        max={flag.max_value ?? undefined}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
      />
      {error && <span className={styles.fieldError}>{error}</span>}
      <span className={styles.readonlyNote}>{flag.description}</span>
    </label>
  );
}

function BoolSetting({
  flag,
  onSave,
  saving,
}: {
  flag: HarnessFlagView;
  onSave: (key: string, value: boolean) => void;
  saving: boolean;
}) {
  return (
    <label>
      <input
        type="checkbox"
        checked={Boolean(flag.value)}
        disabled={saving}
        onChange={(e) => onSave(flag.key, e.target.checked)}
      />
      {" "}{flag.label}
      <span className={styles.readonlyNote}>{flag.description}</span>
    </label>
  );
}

export function DbCompareSettingsSection() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
  });
  const [apiError, setApiError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (updates: Record<string, boolean | number | string>) =>
      HarnessFlags.update(updates),
    onSuccess: () => {
      setApiError(null);
      qc.invalidateQueries({ queryKey: ["harness-flags"] });
    },
    onError: (err: unknown) => {
      setApiError(err instanceof Error ? err.message : "No se pudo guardar la configuración.");
    },
  });

  if (isLoading) return null;
  if (isError || !data?.flags) return null;

  const settings = pickDbCompareSettings(data.flags);
  if (settings.length === 0) return null;

  return (
    <section className={styles.scriptsSection}>
      <h2>Configuración</h2>
      <p className={styles.subtitle}>
        Ajustá acá el feature completo (visibilidad, timeouts, paridad de datos)
        sin ir al panel genérico de flags del arnés.
      </p>
      {apiError && <div className={styles.errorBanner}>{apiError}</div>}
      <div className={styles.formGrid}>
        {settings.map((flag) =>
          flag.type === "bool" ? (
            <BoolSetting
              key={flag.key}
              flag={flag}
              saving={update.isPending}
              onSave={(key, value) => update.mutate({ [key]: value })}
            />
          ) : (
            <IntSetting
              key={flag.key}
              flag={flag}
              saving={update.isPending}
              onSave={(key, value) => update.mutate({ [key]: value })}
            />
          ),
        )}
      </div>
    </section>
  );
}

export default DbCompareSettingsSection;
