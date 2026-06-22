import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  HarnessFlags,
  type HarnessFlagView,
  type HarnessFlagCategory,
} from "../api/endpoints";
import styles from "./HarnessFlagsPanel.module.css";

// Plan 63 F3 — Panel de flags por categorías colapsables.
// Plan 33 F1.1 — Lee el registry dinámicamente: cualquier flag nuevo en el backend
// aparece aquí sin tocar este archivo.

const PROFILE_LABELS: Record<string, string> = {
  off:  "off",
  safe: "safe",
  full: "full",
};

function JsonInput({
  value,
  onChange,
  onBlur,
}: {
  value: string;
  onChange: (v: string) => void;
  onBlur: (v: string, valid: boolean) => void;
}) {
  const [local, setLocal] = useState(value);
  useEffect(() => { setLocal(value); }, [value]);

  const valid = useMemo(() => {
    if (!local.trim()) return true;
    try { JSON.parse(local); return true; } catch { return false; }
  }, [local]);

  return (
    <div>
      <textarea
        className={`${styles.jsonArea} ${!valid ? styles.errorBorder : ""}`}
        rows={3}
        value={local}
        onChange={(e) => { setLocal(e.target.value); onChange(e.target.value); }}
        onBlur={() => onBlur(local, valid)}
      />
      {!valid && <span className={styles.errorText}>JSON inválido</span>}
    </div>
  );
}

interface FlagRowProps {
  flag: HarnessFlagView;
  allFlags: HarnessFlagView[];
  onUpdate: (key: string, value: boolean | number | string) => void;
  saving: boolean;
}

function FlagRow({ flag, allFlags, onUpdate, saving }: FlagRowProps) {
  const [localText, setLocalText] = useState(String(flag.value ?? ""));
  useEffect(() => { setLocalText(String(flag.value ?? "")); }, [flag.value]);

  const pairFlag = flag.pair ? allFlags.find((f) => f.key === flag.pair) : null;
  const [localPair, setLocalPair] = useState(String(pairFlag?.value ?? ""));
  useEffect(() => { setLocalPair(String(pairFlag?.value ?? "")); }, [pairFlag?.value]);

  // Si este flag es el par (csv) de otro bool, se renderiza junto al bool → no duplicar
  const isManagedAsPair = allFlags.some((f) => f.pair === flag.key);
  if (isManagedAsPair) return null;

  const isActive = flag.active;

  const control = () => {
    if (flag.type === "bool") {
      return (
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={Boolean(flag.value)}
            disabled={saving}
            onChange={(e) => onUpdate(flag.key, e.target.checked)}
          />
          <span className={styles.toggleSlider} />
        </label>
      );
    }
    if (flag.type === "int") {
      return (
        <input
          type="number"
          step="1"
          className={styles.numInput}
          value={localText}
          disabled={saving}
          onChange={(e) => setLocalText(e.target.value)}
          onBlur={() => onUpdate(flag.key, Number(localText))}
        />
      );
    }
    if (flag.type === "float") {
      return (
        <input
          type="number"
          step="0.01"
          className={styles.numInput}
          value={localText}
          disabled={saving}
          onChange={(e) => setLocalText(e.target.value)}
          onBlur={() => onUpdate(flag.key, parseFloat(localText))}
        />
      );
    }
    if (flag.type === "csv") {
      return (
        <input
          type="text"
          className={styles.textInput}
          value={localText}
          disabled={saving}
          onChange={(e) => setLocalText(e.target.value)}
          onBlur={() => onUpdate(flag.key, localText)}
        />
      );
    }
    if (flag.type === "json") {
      return (
        <JsonInput
          value={localText}
          onChange={setLocalText}
          onBlur={(v, valid) => { if (valid) onUpdate(flag.key, v); }}
        />
      );
    }
    return null;
  };

  // Normalizar el valor de default para mostrarlo
  const defLabel = (() => {
    if (!flag.default_known) return null;
    if (flag.default === true) return "ON";
    if (flag.default === false) return "OFF";
    const s = String(flag.default);
    return s || "vacío";
  })();

  return (
    <div className={`${styles.flagRow} ${isActive ? styles.activeRow : ""}`}>
      <div className={styles.flagLabel}>
        <div className={styles.flagMeta}>
          <span className={styles.flagName}>{flag.label}</span>
          {defLabel !== null && (
            <span className={styles.defaultBadge}>def: {defLabel}</span>
          )}
        </div>
        <p className={styles.flagDesc}>{flag.description}</p>
      </div>
      <div className={styles.flagControl}>
        {control()}
        {/* Par CSV inmediatamente debajo del bool master */}
        {flag.type === "bool" && pairFlag && (
          <div className={styles.pairRow}>
            <span className={styles.pairLabel}>{pairFlag.label}</span>
            <input
              type="text"
              className={styles.textInput}
              value={localPair}
              disabled={saving || !flag.value}
              placeholder="vacío = todos los proyectos"
              onChange={(e) => setLocalPair(e.target.value)}
              onBlur={() => onUpdate(pairFlag.key, localPair)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default function HarnessFlagsPanel() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
  });

  const [apiError, setApiError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);

  const update = useMutation({
    mutationFn: (updates: Record<string, boolean | number | string>) =>
      HarnessFlags.update(updates),
    onSuccess: () => {
      setApiError(null);
      qc.invalidateQueries({ queryKey: ["harness-flags"] });
    },
    onError: (err: unknown) => {
      setApiError(err instanceof Error ? err.message : "Error al guardar flag.");
    },
  });

  const applyProfile = useMutation({
    mutationFn: (name: string) =>
      fetch("/api/harness-flags/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then(async (r) => {
        const json = await r.json();
        if (!r.ok || !json.ok) throw new Error(json.error ?? `HTTP ${r.status}`);
        return json;
      }),
    onSuccess: () => {
      setApiError(null);
      qc.invalidateQueries({ queryKey: ["harness-flags"] });
    },
    onError: (err: unknown) => {
      setApiError(err instanceof Error ? err.message : "Error al aplicar perfil.");
    },
  });

  const flags = data?.flags ?? [];
  const categories: HarnessFlagCategory[] = data?.categories ?? [];
  const activeProfile = data?.active_profile;
  const saving = update.isPending || applyProfile.isPending;

  // Filtro de búsqueda
  const qLower = q.trim().toLowerCase();
  const matches = (f: HarnessFlagView): boolean => {
    if (onlyActive && !f.active) return false;
    if (!qLower) return true;
    return (
      f.label.toLowerCase().includes(qLower) ||
      f.description.toLowerCase().includes(qLower) ||
      f.key.toLowerCase().includes(qLower)
    );
  };

  // Agrupar por categoría según el orden del backend
  const flagsByCat = useMemo(() => {
    const map = new Map<string, HarnessFlagView[]>();
    for (const f of flags) {
      const cat = f.category ?? "otros";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(f);
    }
    return map;
  }, [flags]);

  // Secciones en el orden del backend
  const orderedSections = useMemo(() => {
    return categories
      .map((cat) => ({ cat, catFlags: flagsByCat.get(cat.id) ?? [] }))
      .filter(({ catFlags }) => catFlags.length > 0);
  }, [categories, flagsByCat]);

  // Stats globales
  const totalFlags = flags.length;
  const totalActive = flags.filter((f) => f.active).length;
  const totalKnown = flags.filter((f) => f.default_known).length;

  const handleUpdate = (key: string, value: boolean | number | string) => {
    update.mutate({ [key]: value });
  };

  if (isLoading) return <div className={styles.status}>Cargando flags...</div>;
  if (isError) return <div className={styles.errorText}>Error al cargar flags: {String((error as Error)?.message ?? error)}</div>;

  return (
    <div className={styles.root}>
      {/* Perfil activo */}
      <div className={styles.profileBar}>
        <span className={styles.profileLabel}>
          Perfil activo: <strong>{activeProfile ?? "personalizado"}</strong>
        </span>
        <div className={styles.profileButtons}>
          {Object.entries(PROFILE_LABELS).map(([name, label]) => (
            <button
              key={name}
              className={`${styles.profileBtn} ${activeProfile === name ? styles.profileBtnActive : ""}`}
              disabled={saving}
              onClick={() => applyProfile.mutate(name)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Búsqueda + filtro */}
      <div className={styles.search}>
        <input
          type="search"
          placeholder="Buscar flag..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className={styles.searchInput}
        />
        <label className={styles.onlyActiveLabel}>
          <input
            type="checkbox"
            checked={onlyActive}
            onChange={(e) => setOnlyActive(e.target.checked)}
          />
          Solo activas / con valor
        </label>
      </div>

      {/* Resumen global */}
      <div className={styles.summary}>
        {totalFlags} flags · {totalActive} activas/con valor · {totalKnown} con default conocido
      </div>

      {saving && <div className={styles.status}>Guardando...</div>}
      {apiError && <div className={styles.errorText}>{apiError}</div>}

      {/* Secciones colapsables por categoría */}
      {orderedSections.map(({ cat, catFlags }) => {
        const visibleFlags = catFlags.filter(matches);
        if (visibleFlags.length === 0) return null;

        const sectionActive = catFlags.some((f) => f.active);
        const visibleActive = visibleFlags.filter((f) => f.active).length;

        return (
          <details
            key={cat.id}
            className={styles.section}
            open={!!qLower || onlyActive || sectionActive}
          >
            <summary className={styles.sectionSummary}>
              <span className={styles.sectionLabel}>{cat.label}</span>
              <span className={styles.sectionMeta}>
                {visibleFlags.length} flags · {visibleActive} activas
              </span>
            </summary>
            {cat.description && (
              <p className={styles.sectionDesc}>{cat.description}</p>
            )}
            {visibleFlags.map((flag) => (
              <FlagRow
                key={flag.key}
                flag={flag}
                allFlags={flags}
                onUpdate={handleUpdate}
                saving={saving}
              />
            ))}
          </details>
        );
      })}
    </div>
  );
}
