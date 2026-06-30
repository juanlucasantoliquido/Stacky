import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  HarnessFlags,
  type HarnessFlagView,
  type HarnessFlagCategory,
} from "../api/endpoints";
import { visualFor, partitionSectionsByTier } from "./harnessVisuals";
import { useHarnessUiPrefs } from "./useHarnessUiPrefs";
import styles from "./HarnessFlagsPanel.module.css";

// Plan 63 F3 — Panel de flags por categorías colapsables.
// Plan 33 F1.1 — Lee el registry dinámicamente: cualquier flag nuevo en el backend
// aparece aquí sin tocar este archivo.
// Plan 78 — Hero, identidad visual, modo Simple/Experto, catch-all, navegación por intención.

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

  // Plan 78 F2 — preferencia de modo (Simple/Experto) persistida en localStorage
  const { mode, setMode } = useHarnessUiPrefs();

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

  // Secciones en el orden del backend.
  // [C9+C14] Retener una categoría cuando qLower matchea un flag O cuando
  // matchea cat.label/cat.intent (navegación por intención real).
  // Si la categoría matchea por label/intent, mostrar TODOS sus flags (sin filtrar por matches()).
  const orderedSections = useMemo(() => {
    return categories
      .map((cat) => {
        const allCatFlags = flagsByCat.get(cat.id) ?? [];
        if (allCatFlags.length === 0) return null;

        if (!qLower && !onlyActive) {
          // Sin búsqueda: incluir todas las categorías con flags
          return { cat, catFlags: allCatFlags };
        }

        // Con búsqueda: primero filtrar flags individuales
        const flagMatches = allCatFlags.filter(matches);

        if (flagMatches.length > 0) {
          // Hay flags que matchean individualmente → incluir solo esos
          return { cat, catFlags: flagMatches };
        }

        // Sin flag que matchee: ver si la categoría matchea por label o intent [C9/C14]
        if (qLower) {
          const catMatchesByLabel = cat.label.toLowerCase().includes(qLower);
          const catMatchesByIntent = (cat.intent ?? "").toLowerCase().includes(qLower);
          if (catMatchesByLabel || catMatchesByIntent) {
            // Mostrar TODAS las flags de la categoría (navegación por intención)
            const filtered = onlyActive ? allCatFlags.filter((f) => f.active) : allCatFlags;
            if (filtered.length > 0) return { cat, catFlags: filtered };
          }
        }

        return null;
      })
      .filter((s): s is { cat: HarnessFlagCategory; catFlags: HarnessFlagView[] } => s !== null);
  }, [categories, flagsByCat, qLower, onlyActive]);

  // Stats globales
  const totalFlags = flags.length;
  const totalActive = flags.filter((f) => f.active).length;
  const totalKnown = flags.filter((f) => f.default_known).length;

  const handleUpdate = (key: string, value: boolean | number | string) => {
    update.mutate({ [key]: value });
  };

  // Plan 78 F5 — renderSection extrae el bloque <details> para reusar en simple/experto/catch-all
  const renderSection = (cat: HarnessFlagCategory, catFlags: HarnessFlagView[]) => {
    const { color, icon: Icon } = visualFor(cat.id);
    const sectionActive = catFlags.some((f) => f.active);
    const visibleActive = catFlags.filter((f) => f.active).length;

    return (
      <details
        key={cat.id}
        className={styles.section}
        style={{ borderLeft: `4px solid ${color}` }}
        open={!!qLower || onlyActive || sectionActive}
      >
        <summary className={styles.sectionSummary}>
          <span className={styles.sectionLabel}>
            <Icon size={16} color={color} className={styles.sectionIcon} aria-hidden="true" />
            {cat.label}
          </span>
          <span className={styles.sectionMeta}>
            {catFlags.length} flags · {visibleActive} activas
          </span>
        </summary>
        {cat.intent && <p className={styles.sectionIntent}>{cat.intent}</p>}
        {cat.description && (
          <p className={styles.sectionDesc}>{cat.description}</p>
        )}
        {catFlags.map((flag) => (
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
  };

  // Plan 78 F4 — partición Simple/Experto usando función pura importada
  const { simpleSections, restSections } = partitionSectionsByTier(orderedSections);

  if (isLoading) return <div className={styles.status}>Cargando flags...</div>;
  if (isError) return <div className={styles.errorText}>Error al cargar flags: {String((error as Error)?.message ?? error)}</div>;

  return (
    <div className={styles.root}>
      {/* Plan 78 F3 — Hero "Arnés — Configuración activa".
          REEMPLAZA los bloques <div className={styles.profileBar}> y <div className={styles.summary}>
          que se eliminaron del JSX. Reutiliza los mismos datos y la misma lógica.
          [C8] El título y la barra son presentación, NO indicadores de salud operativa.
          Ver Plan 46 (OperationalHealthCard) para salud real de runs. */}
      <div className={styles.hero}>
        <div className={styles.heroTitle}>
          Arnés — Configuración activa
          <span className={styles.heroProfile}>Perfil: <strong>{activeProfile ?? "personalizado"}</strong></span>
        </div>
        <div className={styles.heroStats}>
          <div className={styles.heroStat}>
            <span className={styles.heroStatValue}>{totalActive}</span>
            <span className={styles.heroStatLabel}>flags activas</span>
          </div>
          <div className={styles.heroStat}>
            <span className={styles.heroStatValue}>{totalFlags}</span>
            <span className={styles.heroStatLabel}>flags totales</span>
          </div>
          <div className={styles.heroStat}>
            <span className={styles.heroStatValue}>{totalKnown}</span>
            <span className={styles.heroStatLabel}>con default</span>
          </div>
        </div>
        {/* % de flags activas — NO es indicador de salud. Ver Plan 46 para salud real de runs. */}
        <div className={styles.heroActivityBar}>
          <div
            className={styles.heroActivityFill}
            style={{ width: `${totalFlags ? Math.round((totalActive / totalFlags) * 100) : 0}%` }}
          />
        </div>
        {/* Los botones de perfil off/safe/full — misma lógica que el profileBar eliminado. */}
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

      {saving && <div className={styles.status}>Guardando...</div>}
      {apiError && <div className={styles.errorText}>{apiError}</div>}

      {/* Plan 78 F4 — Toggle Simple ↔ Experto.
          [C12] role="group" + aria-label comunican selección mutuamente excluyente. */}
      <div role="group" aria-label="Nivel de configuración" className={styles.modeToggle}>
        <button
          className={`${styles.modeBtn} ${mode === "simple" ? styles.modeBtnActive : ""}`}
          aria-pressed={mode === "simple"}
          onClick={() => setMode("simple")}
        >
          Simple
        </button>
        <button
          className={`${styles.modeBtn} ${mode === "experto" ? styles.modeBtnActive : ""}`}
          aria-pressed={mode === "experto"}
          onClick={() => setMode("experto")}
        >
          Experto
        </button>
      </div>

      {/* Secciones colapsables por categoría — Plan 78 F4 modo Simple/Experto */}
      {mode === "experto"
        ? orderedSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))
        : <>
            {simpleSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))}
            {restSections.length > 0 && (
              <details className={styles.catchAll} open={!!qLower || onlyActive}>
                <summary className={styles.sectionSummary}>
                  <span className={styles.sectionLabel}>Todo lo demás</span>
                  <span className={styles.sectionMeta}>
                    {restSections.length} categorías · {restSections.reduce((n, s) => n + s.catFlags.length, 0)} flags
                  </span>
                </summary>
                {restSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))}
              </details>
            )}
          </>
      }
    </div>
  );
}
