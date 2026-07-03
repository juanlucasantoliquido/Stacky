import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  HarnessFlags,
  type HarnessFlagView,
  type HarnessFlagCategory,
} from "../api/endpoints";
import { visualFor, partitionSectionsByTier, isModifiedFromDefault } from "./harnessVisuals";
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
  onLocate: (key: string) => void;
  saving: boolean;
}

function FlagRow({ flag, allFlags, onUpdate, onLocate, saving }: FlagRowProps) {
  const [localText, setLocalText] = useState(String(flag.value ?? ""));
  useEffect(() => { setLocalText(String(flag.value ?? "")); }, [flag.value]);

  const pairFlag = flag.pair ? allFlags.find((f) => f.key === flag.pair) : null;
  const [localPair, setLocalPair] = useState(String(pairFlag?.value ?? ""));
  useEffect(() => { setLocalPair(String(pairFlag?.value ?? "")); }, [pairFlag?.value]);

  // Si este flag es el par (csv) de otro bool, se renderiza junto al bool → no duplicar
  const isManagedAsPair = allFlags.some((f) => f.pair === flag.key);
  if (isManagedAsPair) return null;

  const isActive = flag.active;
  // Plan 82 F2/C1v3 — hija CONFIGURADA (active) con master OFF = flag muerta real.
  // Una hija en default con master OFF no genera ruido (no se muestra nada).
  const requiresMaster = flag.requires ? allFlags.find((f) => f.key === flag.requires) : null;
  const isInert = Boolean(flag.requires) && !flag.requires_met && isActive;
  // Plan 83 [C1-v3] — el backend ya resuelve el anti-ruido (in_bounds=true para
  // env_only sin configurar); la UI consume in_bounds a secas, sin gatear por active
  // (un 0 explícito bajo min_value=1 es inactivo pero SÍ debe avisar).
  const isOutOfBounds = flag.in_bounds === false;

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
          min={flag.min_value ?? undefined}
          max={flag.max_value ?? undefined}
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
          min={flag.min_value ?? undefined}
          max={flag.max_value ?? undefined}
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
    if (flag.type === "str") {
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
    <div className={`${styles.flagRow} ${isActive ? styles.activeRow : ""} ${isInert ? styles.inertRow : ""}`}>
      <div className={styles.flagLabel}>
        <div className={styles.flagMeta}>
          <span className={styles.flagName}>{flag.label}</span>
          {defLabel !== null && (
            <span className={styles.defaultBadge}>def: {defLabel}</span>
          )}
          {isModifiedFromDefault(flag) && (
            <span className={styles.modifiedBadge}>modificada</span>
          )}
          {flag.env_only === true && (
            <span
              className={styles.envBadge}
              title="Vive solo en .env/os.environ (se aplica en caliente); no es atributo de Config"
            >
              env
            </span>
          )}
          {flag.restart_required === true && (
            <span
              className={styles.restartBadge}
              title="Esta flag se lee al arrancar el backend; los cambios aplican tras reiniciar"
            >
              reinicio
            </span>
          )}
        </div>
        <p className={styles.flagDesc}>{flag.description}</p>
        {flag.pending_restart === true && (
          <p className={styles.pendingRestartNote}>
            Cambio pendiente de reinicio del backend
            {flag.boot_value !== null && flag.boot_value !== undefined
              ? ` — el proceso corre con ${String(flag.boot_value)}`
              : ""}
          </p>
        )}
        {isOutOfBounds && (
          <p className={styles.outOfBoundsNote}>Valor actual fuera de rango válido</p>
        )}
        <code
          className={styles.flagKey}
          title="Click para copiar la key"
          onClick={() => { void navigator.clipboard?.writeText(flag.key); }}
        >
          {flag.key}
        </code>
        {isInert && (
          <p className={styles.requiresNote}>
            Sin efecto: requiere &ldquo;{requiresMaster?.label ?? flag.requires}&rdquo; activada
            {" "}
            <button
              type="button"
              className={styles.locateMasterBtn}
              onClick={() => onLocate(flag.requires!)}
            >
              ver master
            </button>
          </p>
        )}
      </div>
      <div className={styles.flagControl}>
        {control()}
        {(flag.min_value !== null || flag.max_value !== null) && (
          <span className={styles.boundsHint}>
            {flag.min_value !== null && flag.max_value !== null
              ? `${flag.min_value}–${flag.max_value}`
              : flag.min_value !== null
                ? `≥ ${flag.min_value}`
                : `≤ ${flag.max_value}`}
          </span>
        )}
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
  const [onlyModified, setOnlyModified] = useState(false);
  // Plan 83 [ADICIÓN ARQUITECTO v2] — chip de triage "N fuera de rango" en el hero.
  const [onlyOutOfBounds, setOnlyOutOfBounds] = useState(false);
  // Plan 84 — chip de triage "N pendientes de reinicio" en el hero.
  const [onlyPendingRestart, setOnlyPendingRestart] = useState(false);

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
  const profileDeltas = data?.profile_deltas;
  const saving = update.isPending || applyProfile.isPending;

  // Plan 82 F4 — cuando el perfil es "personalizado", el perfil más cercano (menor delta).
  const nearestProfile = useMemo(() => {
    if (activeProfile || !profileDeltas) return null;
    const entries = Object.entries(profileDeltas);
    if (entries.length === 0) return null;
    return entries.sort((a, b) => a[1] - b[1])[0];
  }, [activeProfile, profileDeltas]);

  // Filtro de búsqueda
  const qLower = q.trim().toLowerCase();
  const matches = (f: HarnessFlagView): boolean => {
    if (onlyOutOfBounds && f.in_bounds !== false) return false;
    if (onlyPendingRestart && f.pending_restart !== true) return false;
    if (onlyModified && !isModifiedFromDefault(f)) return false;
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

        if (!qLower && !onlyActive && !onlyModified && !onlyOutOfBounds && !onlyPendingRestart) {
          // Sin búsqueda ni filtros: incluir todas las categorías con flags
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
            const filtered = allCatFlags.filter(
              (f) => (!onlyActive || f.active) && (!onlyModified || isModifiedFromDefault(f)),
            );
            if (filtered.length > 0) return { cat, catFlags: filtered };
          }
        }

        return null;
      })
      .filter((s): s is { cat: HarnessFlagCategory; catFlags: HarnessFlagView[] } => s !== null);
  }, [categories, flagsByCat, qLower, onlyActive, onlyModified, onlyOutOfBounds, onlyPendingRestart]);

  // Stats globales
  const totalFlags = flags.length;
  const totalActive = flags.filter((f) => f.active).length;
  const totalKnown = flags.filter((f) => f.default_known).length;
  const totalModified = flags.filter(isModifiedFromDefault).length;
  // Plan 83 [ADICIÓN ARQUITECTO v2] — cuenta de flags con valor configurado fuera de rango.
  const outOfBoundsCount = flags.filter((f) => f.in_bounds === false).length;
  // Plan 84 — cuenta de flags con cambios pendientes de reinicio.
  const pendingRestartCount = flags.filter((f) => f.pending_restart === true).length;

  // Si el operador corrigió todo, no dejar el filtro fantasma activo.
  useEffect(() => {
    if (outOfBoundsCount === 0 && onlyOutOfBounds) setOnlyOutOfBounds(false);
  }, [outOfBoundsCount, onlyOutOfBounds]);
  useEffect(() => {
    if (pendingRestartCount === 0 && onlyPendingRestart) setOnlyPendingRestart(false);
  }, [pendingRestartCount, onlyPendingRestart]);

  const handleUpdate = (key: string, value: boolean | number | string) => {
    update.mutate({ [key]: value }, {
      onSuccess: (data) => {
        // Plan 84 F3.4 — aviso post-PUT si hay keys que requieren reinicio
        if (data.restart_required_keys && data.restart_required_keys.length > 0) {
          const keys = data.restart_required_keys.join(", ");
          setApiError(`Guardado. Requiere reiniciar el backend: ${keys}`);
        }
      },
    });
  };

  // Plan 78 F5 — renderSection extrae el bloque <details> para reusar en simple/experto/catch-all
  const renderSection = (cat: HarnessFlagCategory, catFlags: HarnessFlagView[]) => {
    const { color, icon: Icon } = visualFor(cat.id);
    const sectionActive = catFlags.some((f) => f.active);
    const visibleActive = catFlags.filter((f) => f.active).length;
    // [C4 v3] Cuenta sobre TODAS las flags del payload de la categoría, incluidas
    // las gestionadas como `pair` que no renderizan fila propia — comportamiento
    // esperado, no se "corrige" contra las filas visibles.
    const modified = catFlags.filter(isModifiedFromDefault).length;

    return (
      <details
        key={cat.id}
        className={styles.section}
        style={{ borderLeft: `4px solid ${color}` }}
        open={!!qLower || onlyActive || onlyModified || onlyOutOfBounds || onlyPendingRestart || sectionActive}
      >
        <summary className={styles.sectionSummary}>
          <span className={styles.sectionLabel}>
            <Icon size={16} color={color} className={styles.sectionIcon} aria-hidden="true" />
            {cat.label}
          </span>
          <span className={styles.sectionMeta}>
            {catFlags.length} flags · {visibleActive} activas{modified > 0 ? ` · ${modified} modificadas` : ""}
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
            onLocate={setQ}
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
          <span className={styles.heroProfile}>
            Perfil: <strong>{activeProfile ?? "personalizado"}</strong>
            {!activeProfile && nearestProfile && (
              <span className={styles.nearestProfile}>
                {" "}(más cercano: {nearestProfile[0]}, {nearestProfile[1]} diferencia{nearestProfile[1] === 1 ? "" : "s"})
              </span>
            )}
          </span>
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
          <div className={styles.heroStat}>
            <span className={styles.heroStatValue}>{totalModified}</span>
            <span className={styles.heroStatLabel}>fuera de default</span>
          </div>
          {outOfBoundsCount > 0 && (
            <button
              type="button"
              className={`${styles.outOfBoundsChip} ${onlyOutOfBounds ? styles.outOfBoundsChipActive : ""}`}
              onClick={() => setOnlyOutOfBounds((v) => !v)}
            >
              {outOfBoundsCount} fuera de rango
            </button>
          )}
          {pendingRestartCount > 0 && (
            <button
              type="button"
              className={`${styles.pendingRestartChip} ${onlyPendingRestart ? styles.pendingRestartChipActive : ""}`}
              onClick={() => setOnlyPendingRestart((v) => !v)}
            >
              {pendingRestartCount} pendientes de reinicio
            </button>
          )}
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
        <label className={styles.onlyActiveLabel}>
          <input
            type="checkbox"
            checked={onlyModified}
            onChange={(e) => setOnlyModified(e.target.checked)}
          />
          Solo modificadas
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
