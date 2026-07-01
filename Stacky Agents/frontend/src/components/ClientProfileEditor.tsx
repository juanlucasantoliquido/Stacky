import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ClientProfileApi,
  DbReadonlyAuth,
  type ClientProfile,
  type ClientProfilePathCheck,
  type ClientProfileStateWarning,
} from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./ClientProfileEditor.module.css";

// ── Helpers de acceso inmutable (round-trip seguro) ──────────────────────────
// El estado fuente de verdad es `baseProfile` (objeto completo, incluidas claves
// que el formulario no expone — p. ej. `extensions.*`). Los campos parchean
// rutas conocidas sin tocar el resto, así nada se pierde al guardar.

type Json = Record<string, unknown>;

function asObj(v: unknown): Json {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Json) : {};
}
function asStr(v: unknown): string {
  if (v == null) return "";
  return typeof v === "string" ? v : String(v);
}
function asArr(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x)) : [];
}
function asStrMap(v: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(asObj(v))) out[k] = asStr(val);
  return out;
}

type KvRow = { id: number; k: string; v: string };
function rowsToMap(rows: KvRow[]): Record<string, string> {
  // Pliega filas a objeto; ignora claves vacías. En colisión gana la última (un
  // mapa no puede tener claves repetidas), pero las filas quedan visibles en la
  // UI para que el operador resuelva el conflicto — no se pierden silenciosamente.
  const out: Record<string, string> = {};
  for (const r of rows) {
    const k = r.k.trim();
    if (k) out[k] = r.v;
  }
  return out;
}
function mapsEqual(a: Record<string, string>, b: Record<string, string>): boolean {
  const ak = Object.keys(a);
  const bk = Object.keys(b);
  return ak.length === bk.length && ak.every((k) => b[k] === a[k]);
}
function getPath(obj: Json, path: string[]): unknown {
  let cur: unknown = obj;
  for (const k of path) cur = asObj(cur)[k];
  return cur;
}
function setPath(obj: Json, path: string[], value: unknown): Json {
  if (path.length === 0) return obj;
  const [head, ...rest] = path;
  const clone: Json = { ...obj };
  clone[head] = rest.length === 0 ? value : setPath(asObj(clone[head]), rest, value);
  return clone;
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

// ── Sub-componentes de formulario ────────────────────────────────────────────

type ProcessCatalogItem = {
  name?: string;
  kind?: string;
  purpose?: string;
};

function ProcessCatalogField({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (next: ProcessCatalogItem[]) => void;
}) {
  const items = Array.isArray(value)
    ? (value as ProcessCatalogItem[])
    : [];

  const updateItem = (index: number, patch: Partial<ProcessCatalogItem>) => {
    const next = [...items];
    next[index] = { ...items[index], ...patch };
    onChange(next);
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  const addItem = () => {
    onChange([...items, { name: "", kind: "processing", purpose: "" }]);
  };

  return (
    <div className={`${styles.field} ${styles.fieldFull}`}>
      <div className={styles.kvList}>
        {items.length === 0 && (
          <p className={styles.hint} style={{ marginBottom: 10 }}>
            No hay procesos en el catálogo.
          </p>
        )}
        {items.map((item, idx) => (
          <div key={idx} className={styles.kvRow}>
            <input
              className={`${styles.input} ${styles.kvKey}`}
              placeholder="Nombre del proceso"
              value={item.name ?? ""}
              onChange={(e) => updateItem(idx, { name: e.target.value })}
              spellCheck={false}
            />
            <select
              className={styles.input}
              value={item.kind ?? "processing"}
              onChange={(e) => updateItem(idx, { kind: e.target.value })}
            >
              <option value="entry">entry</option>
              <option value="processing">processing</option>
              <option value="output">output</option>
            </select>
            <input
              className={`${styles.input} ${styles.kvVal}`}
              placeholder="Propósito"
              value={item.purpose ?? ""}
              onChange={(e) => updateItem(idx, { purpose: e.target.value })}
              spellCheck={false}
            />
            <button
              type="button"
              className={styles.iconBtn}
              title="Quitar"
              onClick={() => removeItem(idx)}
            >
              ×
            </button>
          </div>
        ))}
        <button type="button" className={styles.addBtn} onClick={addItem}>
          + Agregar proceso
        </button>
      </div>
    </div>
  );
}

function Section({
  title,
  required,
  children,
}: {
  title: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <h4 className={styles.cardTitle}>{title}</h4>
        {required && <span className={styles.requiredTag}>requerido</span>}
      </div>
      {children}
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  full,
  type = "text",
  readOnly = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  full?: boolean;
  type?: "text" | "number";
  readOnly?: boolean;
}) {
  return (
    <div className={full ? `${styles.field} ${styles.fieldFull}` : styles.field}>
      <label className={styles.label}>{label}</label>
      <input
        className={styles.input}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        spellCheck={false}
      />
    </div>
  );
}

function StringArrayField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const v = draft.trim();
    if (!v) {
      setDraft("");
      return;
    }
    if (!value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
  };
  return (
    <div className={`${styles.field} ${styles.fieldFull}`}>
      <label className={styles.label}>{label}</label>
      <div className={styles.chips}>
        {value.map((item) => (
          <span key={item} className={styles.chip}>
            {item}
            <button
              type="button"
              className={styles.chipRemove}
              title="Quitar"
              onClick={() => onChange(value.filter((x) => x !== item))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          className={styles.chipInput}
          value={draft}
          placeholder={placeholder ?? "Añadir…"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          spellCheck={false}
        />
      </div>
    </div>
  );
}

function KeyValueField({
  label,
  value,
  onChange,
  fixedKeys,
  keyPlaceholder,
  valuePlaceholder,
}: {
  label: string;
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  fixedKeys?: string[];
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}) {
  // Hooks SIEMPRE antes de cualquier return (rules of hooks) — el modo fixedKeys
  // no usa `rows`, pero los hooks deben llamarse incondicionalmente.
  const seqRef = useRef(0);
  const [rows, setRows] = useState<KvRow[]>(() =>
    Object.entries(value).map(([k, v]) => ({ id: seqRef.current++, k, v }))
  );
  // Re-sincroniza desde `value` SOLO cuando cambia por fuera (p.ej. "Aplicar
  // template default"); si el cambio lo originamos nosotros (rows producen el
  // mismo mapa) conservamos las filas y sus ids para no perder foco ni filas.
  useEffect(() => {
    setRows((prev) =>
      mapsEqual(rowsToMap(prev), value)
        ? prev
        : Object.entries(value).map(([k, v]) => ({ id: seqRef.current++, k, v }))
    );
  }, [value]);

  if (fixedKeys) {
    return (
      <div className={`${styles.field} ${styles.fieldFull}`}>
        <label className={styles.label}>{label}</label>
        <div className={styles.kvList}>
          {fixedKeys.map((k) => (
            <div key={k} className={styles.kvRow}>
              <input className={`${styles.input} ${styles.kvKey}`} value={k} disabled />
              <input
                className={`${styles.input} ${styles.kvVal}`}
                value={value[k] ?? ""}
                placeholder={valuePlaceholder}
                onChange={(e) => onChange({ ...value, [k]: e.target.value })}
                spellCheck={false}
              />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const emit = (next: KvRow[]) => {
    setRows(next);
    onChange(rowsToMap(next));
  };
  const updateRow = (id: number, patch: Partial<KvRow>) =>
    emit(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const removeRow = (id: number) => emit(rows.filter((r) => r.id !== id));
  const addRow = () => setRows([...rows, { id: seqRef.current++, k: "", v: "" }]);

  const seen = new Set<string>();
  const dupRows = new Set<number>();
  for (const r of rows) {
    const k = r.k.trim();
    if (!k) continue;
    if (seen.has(k)) dupRows.add(r.id);
    seen.add(k);
  }

  return (
    <div className={`${styles.field} ${styles.fieldFull}`}>
      <label className={styles.label}>{label}</label>
      <div className={styles.kvList}>
        {rows.map((r) => (
          <div key={r.id} className={styles.kvRow}>
            <input
              className={`${styles.input} ${styles.kvKey}`}
              value={r.k}
              placeholder={keyPlaceholder ?? "clave"}
              onChange={(e) => updateRow(r.id, { k: e.target.value })}
              style={dupRows.has(r.id) ? { borderColor: "var(--danger)" } : undefined}
              spellCheck={false}
            />
            <input
              className={`${styles.input} ${styles.kvVal}`}
              value={r.v}
              placeholder={valuePlaceholder ?? "valor"}
              onChange={(e) => updateRow(r.id, { v: e.target.value })}
              spellCheck={false}
            />
            <button
              type="button"
              className={styles.iconBtn}
              title="Quitar"
              onClick={() => removeRow(r.id)}
            >
              ×
            </button>
          </div>
        ))}
        <button type="button" className={styles.addBtn} onClick={addRow}>
          + fila
        </button>
        {dupRows.size > 0 && (
          <p className={styles.hint} style={{ color: "var(--danger)" }}>
            Hay claves duplicadas — solo se guardará la última de cada una.
          </p>
        )}
      </div>
    </div>
  );
}

function TrackerRoleField({
  role,
  value,
  onChange,
}: {
  role: string;
  value: Json;
  onChange: (next: Json) => void;
}) {
  return (
    <div className={styles.roleCard}>
      <h5 className={styles.roleName}>{role}</h5>
      <StringArrayField
        label="Estados de entrada"
        value={asArr(value.input_states)}
        onChange={(a) => onChange({ ...value, input_states: a })}
        placeholder="Añadir estado…"
      />
      <TextField
        label="En progreso"
        value={asStr(value.in_progress)}
        onChange={(v) => onChange({ ...value, in_progress: v })}
      />
      <TextField
        label="Estado bloqueado"
        value={asStr(value.blocked_state)}
        onChange={(v) => onChange({ ...value, blocked_state: v })}
      />
      <TextField
        label="Próximo estado (OK)"
        value={asStr(value.next_state_ok)}
        onChange={(v) => onChange({ ...value, next_state_ok: v })}
      />
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────

export default function ClientProfileEditor() {
  const qc = useQueryClient();
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name ?? null;

  const profileQuery = useQuery({
    queryKey: ["client-profile", projectName],
    queryFn: () => ClientProfileApi.get(projectName!),
    enabled: !!projectName,
  });

  const dbAuthQuery = useQuery({
    queryKey: ["client-profile", "db-auth", projectName],
    queryFn: () => DbReadonlyAuth.meta(projectName!),
    enabled: !!projectName,
  });

  // baseProfile = fuente de verdad (objeto completo). advancedJson != null → vista JSON.
  const [baseProfile, setBaseProfile] = useState<ClientProfile>({} as ClientProfile);
  const [advancedJson, setAdvancedJson] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [stateWarnings, setStateWarnings] = useState<ClientProfileStateWarning[]>([]);

  const [dbServer, setDbServer] = useState("");
  const [dbDatabase, setDbDatabase] = useState("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbBusy, setDbBusy] = useState(false);
  const [dbNotice, setDbNotice] = useState<string | null>(null);
  const [dbError, setDbError] = useState<string | null>(null);

  useEffect(() => {
    if (!profileQuery.data) return;
    // Arranca SIEMPRE completo (salvo BD). Si el backend no manda prefilled
    // (versión vieja), cae al comportamiento previo.
    const initial =
      profileQuery.data.prefilled_profile ??
      (profileQuery.data.has_profile
        ? profileQuery.data.profile
        : profileQuery.data.default_template);
    setBaseProfile((initial ?? {}) as ClientProfile);
    setWarnings(profileQuery.data.validation?.warnings ?? []);
    setAdvancedJson(null); // al (re)cargar, volver a la vista de formulario
  }, [profileQuery.data]);

  useEffect(() => {
    if (!dbAuthQuery.data) return;
    setDbServer(dbAuthQuery.data.server ?? "");
    setDbDatabase(dbAuthQuery.data.database ?? "");
    setDbUser(dbAuthQuery.data.user ?? "");
  }, [dbAuthQuery.data]);

  const view: "form" | "json" = advancedJson === null ? "form" : "json";

  const jsonParseError = useMemo<string | null>(() => {
    if (advancedJson === null) return null;
    if (!advancedJson.trim()) return "El JSON está vacío.";
    try {
      const obj = JSON.parse(advancedJson);
      if (typeof obj !== "object" || obj === null || Array.isArray(obj))
        return "El JSON raíz debe ser un objeto.";
      return null;
    } catch (err) {
      return err instanceof Error ? err.message : "JSON inválido";
    }
  }, [advancedJson]);

  if (!projectName) {
    return (
      <div className={styles.card}>
        <p className={styles.intro}>
          Seleccioná un proyecto activo para editar su perfil de cliente.
        </p>
      </div>
    );
  }

  if (profileQuery.isLoading) {
    return (
      <div className={styles.card}>
        <p className={styles.intro}>Cargando perfil del cliente…</p>
      </div>
    );
  }

  if (profileQuery.error) {
    return (
      <div className={styles.card}>
        <p className={styles.error}>Error: {String(profileQuery.error)}</p>
      </div>
    );
  }

  const trackerType = profileQuery.data?.tracker_type ?? "azure_devops";
  const hasProfile = !!profileQuery.data?.has_profile;
  const isPrefilled = !hasProfile && !!profileQuery.data?.prefilled_profile;
  const defaultTemplate = (profileQuery.data?.default_template ?? {}) as Json;
  const pathCheck: ClientProfilePathCheck[] = profileQuery.data?.path_check ?? [];

  // Lectura/escritura sobre baseProfile.
  const g = (path: string[]) => getPath(baseProfile as Json, path);
  const gs = (path: string[]) => asStr(g(path));
  const set = (path: string[], value: unknown) =>
    setBaseProfile((prev) => setPath(prev as Json, path, value) as ClientProfile);
  // Placeholder = valor del template default del tracker.
  const ph = (path: string[]) => asStr(getPath(defaultTemplate, path));
  const hasDbCredential = !!dbAuthQuery.data?.has_credentials;
  const derivedDbServer = hasDbCredential || dbServer ? dbServer : gs(["database", "server"]);
  const derivedDbReadonlyUser =
    hasDbCredential || dbUser ? dbUser : gs(["database", "readonly_user_hint"]);

  const switchToJson = () => {
    setAdvancedJson(safeStringify(baseProfile));
    setSaveError(null);
    setSaveNotice(null);
  };
  const switchToForm = () => {
    if (advancedJson === null) return;
    if (jsonParseError) {
      setSaveError("Corregí el JSON antes de volver al formulario: " + jsonParseError);
      return;
    }
    try {
      const obj = JSON.parse(advancedJson) as ClientProfile;
      setBaseProfile(obj);
      setAdvancedJson(null);
      setSaveError(null);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "JSON inválido");
    }
  };

  const onApplyDefault = () => {
    const tmpl = profileQuery.data?.default_template;
    if (!tmpl) return;
    setBaseProfile(tmpl as ClientProfile);
    setWarnings([]);
    if (advancedJson !== null) setAdvancedJson(safeStringify(tmpl));
    setSaveNotice(
      `Template default del tracker '${trackerType}' aplicado al editor (todavía no se guardó).`
    );
    setSaveError(null);
  };

  // Perfil efectivo según la vista activa: en formulario es `baseProfile`; en
  // JSON es el parse de `advancedJson` (null si el JSON es inválido). Evita
  // persistir estado de formulario obsoleto cuando hay ediciones JSON sin aplicar.
  const resolveCurrentProfile = (): ClientProfile | null => {
    if (view !== "json") return baseProfile;
    if (jsonParseError) return null;
    try {
      return JSON.parse(advancedJson!) as ClientProfile;
    } catch {
      return null;
    }
  };

  const onSave = async () => {
    const profileToSave = resolveCurrentProfile();
    if (!profileToSave) {
      setSaveError(
        "Corregí el JSON antes de guardar" + (jsonParseError ? ": " + jsonParseError : ".")
      );
      return;
    }
    if (view === "json") setBaseProfile(profileToSave);
    setBusy(true);
    setSaveError(null);
    setSaveNotice(null);
    try {
      const res = await ClientProfileApi.save(projectName, profileToSave);
      if (!res.ok) {
        setSaveError(res.error ?? "Error desconocido al guardar.");
      } else {
        setSaveNotice("Perfil guardado correctamente.");
        setWarnings(res.warnings ?? []);
        setStateWarnings(res.state_warnings ?? []);
        await qc.invalidateQueries({ queryKey: ["client-profile", projectName] });
        await qc.invalidateQueries({ queryKey: ["projects"] });
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error al guardar.");
    } finally {
      setBusy(false);
    }
  };

  const onClear = async () => {
    if (
      !confirm(
        "¿Eliminar el client_profile guardado? El agente seguirá recibiendo los defaults del tracker (marcados como 'sin configurar'), pero perderás los valores que ajustaste."
      )
    ) {
      return;
    }
    setBusy(true);
    setSaveError(null);
    setSaveNotice(null);
    try {
      const res = await ClientProfileApi.clear(projectName);
      if (res.ok) {
        setSaveNotice("Perfil eliminado. Volvés a los defaults del tracker.");
        await qc.invalidateQueries({ queryKey: ["client-profile", projectName] });
        await qc.invalidateQueries({ queryKey: ["projects"] });
      } else {
        setSaveError(res.error ?? "No se pudo eliminar.");
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error al eliminar.");
    } finally {
      setBusy(false);
    }
  };

  const onSaveDbAuth = async () => {
    if (!dbPassword.trim() && !dbAuthQuery.data?.has_credentials) {
      setDbError("Password requerido.");
      return;
    }
    setDbBusy(true);
    setDbError(null);
    setDbNotice(null);
    try {
      const res = await DbReadonlyAuth.save(projectName, {
        server: dbServer.trim() || undefined,
        database: dbDatabase.trim() || undefined,
        user: dbUser.trim() || undefined,
        password: dbPassword,
      });
      if (res.ok) {
        const current = resolveCurrentProfile();
        if (!current) {
          setDbNotice(
            "Credencial BD readonly guardada. (No se pudo sincronizar el perfil: corregí el JSON en 'Avanzado' y guardalo manualmente.)"
          );
        } else {
          try {
            const seeded = setPath(
              setPath(
                current as Json,
                ["database", "server"],
                dbServer.trim()
              ),
              ["database", "readonly_user_hint"],
              dbUser.trim()
            ) as ClientProfile;
            const saveRes = await ClientProfileApi.save(projectName, seeded);
            if (saveRes.ok) {
              setBaseProfile(seeded);
              if (view === "json") setAdvancedJson(safeStringify(seeded));
              setWarnings(saveRes.warnings ?? []);
              await qc.invalidateQueries({ queryKey: ["client-profile", projectName] });
              await qc.invalidateQueries({ queryKey: ["projects"] });
              setDbNotice(
                hasProfile
                  ? "Credencial BD readonly guardada. El perfil quedó sincronizado con la credencial."
                  : "Credencial BD guardada. Se creó el perfil del cliente con el template default — revisá y completá las secciones en el formulario de arriba."
              );
            } else {
              setDbNotice(
                "Credencial BD readonly guardada. (No se pudo sincronizar el perfil: " +
                  (saveRes.error ?? "error desconocido") +
                  " — guardalo manualmente con el formulario de arriba.)"
              );
            }
          } catch {
            setDbNotice(
              "Credencial BD readonly guardada. (Error al sincronizar el perfil — guardalo manualmente con el formulario de arriba.)"
            );
          }
        }
        setDbPassword("");
        await qc.invalidateQueries({ queryKey: ["client-profile", "db-auth", projectName] });
      } else {
        setDbError(res.error ?? "Error al guardar la credencial.");
      }
    } catch (err) {
      setDbError(err instanceof Error ? err.message : "Error al guardar.");
    } finally {
      setDbBusy(false);
    }
  };

  const saveDisabled = busy || (view === "json" && !!jsonParseError);

  return (
    <div className={styles.root}>
      {/* ── Header ── */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h4 className={styles.cardTitle}>Perfil del cliente — {projectName}</h4>
        </div>
        <p className={styles.intro}>
          Datos específicos del cliente que los agentes genéricos consumen sin
          hardcodearlos. El bloque <code>client-profile</code> se inyecta como
          context block en <strong>cada ejecución de agente</strong> (sin secretos):
          si no configurás nada, los agentes reciben los defaults del tracker.
        </p>
        <div className={styles.metaRow}>
          <span className={styles.metaItem}>
            Tracker: <strong>{trackerType}</strong>
          </span>
          <span
            className={`${styles.badge} ${
              hasProfile
                ? styles.badgeOk
                : isPrefilled
                  ? styles.badgePrefilled
                  : styles.badgeDefault
            }`}
          >
            {hasProfile
              ? "Configurado"
              : isPrefilled
                ? "Pre-llenado — guardá para fijarlo"
                : "Usando defaults"}
          </span>
          <span className={styles.spacer} />
          <div className={styles.viewToggle}>
            <button
              type="button"
              className={view === "form" ? styles.toggleBtnActive : styles.toggleBtn}
              onClick={switchToForm}
            >
              Formulario
            </button>
            <button
              type="button"
              className={view === "json" ? styles.toggleBtnActive : styles.toggleBtn}
              onClick={switchToJson}
            >
              Avanzado (JSON)
            </button>
          </div>
        </div>
      </div>

      {/* ── Vista JSON ── */}
      {view === "json" ? (
        <div className={styles.card}>
          <p className={styles.intro}>
            Edición cruda del perfil completo (incluye <code>extensions</code> y
            cualquier clave no contemplada por el formulario). Volvé a “Formulario”
            para seguir editando por campos.
          </p>
          <textarea
            className={styles.jsonArea}
            value={advancedJson ?? ""}
            onChange={(e) => setAdvancedJson(e.target.value)}
            spellCheck={false}
            aria-label="Editor JSON del client_profile"
          />
          {jsonParseError && <div className={styles.error}>JSON: {jsonParseError}</div>}
        </div>
      ) : (
        <>
          {/* ── Identidad ── */}
          <Section title="Identidad y terminología">
            <div className={styles.grid2}>
              <TextField
                label="Nombre del producto"
                value={gs(["terminology", "product_name"])}
                onChange={(v) => set(["terminology", "product_name"], v)}
                placeholder="Ej: UCollect Strategy"
              />
              <TextField
                label="Cliente"
                value={gs(["terminology", "client_label"])}
                onChange={(v) => set(["terminology", "client_label"], v)}
                placeholder="Ej: RS Pacífico"
              />
              <TextField
                label="Glosario de dominio (ruta)"
                value={gs(["terminology", "domain_glossary_ref"])}
                onChange={(v) => set(["terminology", "domain_glossary_ref"], v)}
                placeholder="trunk/docs/glossary.md"
                full
              />
            </div>
          </Section>

          {/* ── Estructura de código ── */}
          <Section title="Estructura de código" required>
            <p className={styles.hint} style={{ marginBottom: 10 }}>
              Rutas estándar de <code>trunk/</code> — iguales en todos los proyectos.
              Editá solo si este repo difiere.
            </p>
            <div className={styles.grid2}>
              <TextField label="Online" value={gs(["code_layout", "online_path"])} onChange={(v) => set(["code_layout", "online_path"], v)} placeholder={ph(["code_layout", "online_path"])} />
              <TextField label="Batch" value={gs(["code_layout", "batch_path"])} onChange={(v) => set(["code_layout", "batch_path"], v)} placeholder={ph(["code_layout", "batch_path"])} />
              <TextField label="Scripts BD" value={gs(["code_layout", "db_scripts_path"])} onChange={(v) => set(["code_layout", "db_scripts_path"], v)} placeholder={ph(["code_layout", "db_scripts_path"])} />
              <TextField label="Librerías" value={gs(["code_layout", "lib_path"])} onChange={(v) => set(["code_layout", "lib_path"], v)} placeholder={ph(["code_layout", "lib_path"])} />
              <TextField label="Tests" value={gs(["code_layout", "test_path"])} onChange={(v) => set(["code_layout", "test_path"], v)} placeholder={ph(["code_layout", "test_path"])} />
            </div>
            {pathCheck.length > 0 && (
              <div className={styles.pathCheckList}>
                {pathCheck
                  .filter((p) => p.section === "code_layout")
                  .map((p) => (
                    <div
                      key={`${p.section}.${p.key}`}
                      className={`${styles.pathCheckRow} ${p.exists ? styles.pathCheckOk : styles.pathCheckWarn}`}
                    >
                      <span className={styles.pathCheckIcon}>{p.exists ? "✓" : "⚠"}</span>
                      <span className={styles.pathCheckRel}>{p.rel}</span>
                      <span className={styles.pathCheckAbs}>{p.abs || "(sin workspace_root)"}</span>
                    </div>
                  ))}
              </div>
            )}
            <div style={{ height: 12 }} />
            <KeyValueField
              label="Extensiones de archivo"
              value={asStrMap(g(["code_layout", "file_extensions"]))}
              onChange={(m) => set(["code_layout", "file_extensions"], m)}
              fixedKeys={["ui", "ui_code_behind", "code"]}
              valuePlaceholder=".cs"
            />
            <StringArrayField
              label="Capas de arquitectura"
              value={asArr(g(["code_layout", "architecture_layers"]))}
              onChange={(a) => set(["code_layout", "architecture_layers"], a)}
              placeholder="Ej: RSBus (BLL)"
            />
          </Section>

          {/* ── Lenguaje ── */}
          <Section title="Lenguaje" required>
            <div className={styles.grid2}>
              <TextField label="Lenguaje primario" value={gs(["language", "primary"])} onChange={(v) => set(["language", "primary"], v)} placeholder={ph(["language", "primary"])} />
              <TextField label="Patrón de token del ticket" value={gs(["language", "ticket_token_pattern"])} onChange={(v) => set(["language", "ticket_token_pattern"], v)} placeholder={ph(["language", "ticket_token_pattern"])} />
              <TextField label="Plantilla de trazabilidad en comentarios" value={gs(["language", "comment_traceability"])} onChange={(v) => set(["language", "comment_traceability"], v)} placeholder={ph(["language", "comment_traceability"])} full />
            </div>
            <StringArrayField
              label="Idiomas en RIDIOMA"
              value={asArr(g(["language", "languages_in_ridioma"]))}
              onChange={(a) => set(["language", "languages_in_ridioma"], a)}
              placeholder="Ej: ESP"
            />
          </Section>

          {/* ── Base de datos ── */}
          <Section title="Base de datos">
            <div className={styles.grid2}>
              <TextField label="Tipo" value={gs(["database", "type"])} onChange={(v) => set(["database", "type"], v)} placeholder={ph(["database", "type"])} />
              <TextField label="Server" value={derivedDbServer} onChange={() => {}} placeholder="Se completa desde Credencial BD readonly" readOnly />
              <TextField label="Usuario readonly (hint)" value={derivedDbReadonlyUser} onChange={() => {}} placeholder="Se completa desde Credencial BD readonly" readOnly />
              <TextField label="Tipo de conexión" value={gs(["database", "connection_kind"])} onChange={(v) => set(["database", "connection_kind"], v)} placeholder={ph(["database", "connection_kind"])} />
              <TextField label="Política DML" value={gs(["database", "dml_policy"])} onChange={(v) => set(["database", "dml_policy"], v)} placeholder={ph(["database", "dml_policy"])} />
              <TextField label="Ref. auth readonly" value={gs(["database", "readonly_auth_ref"])} onChange={(v) => set(["database", "readonly_auth_ref"], v)} placeholder="auth/db_readonly.json" />
              <TextField label="Prefijo de tabla" value={gs(["database", "naming_conventions", "table_prefix"])} onChange={(v) => set(["database", "naming_conventions", "table_prefix"], v)} placeholder="R" />
              <TextField
                label="Largo prefijo de columna"
                type="number"
                value={gs(["database", "naming_conventions", "column_prefix_len"])}
                placeholder={ph(["database", "naming_conventions", "column_prefix_len"])}
                onChange={(v) => {
                  const t = v.trim();
                  // Vacío → quitar la clave (cae al default del tracker, no a un 0 engañoso).
                  if (t === "") {
                    set(["database", "naming_conventions", "column_prefix_len"], undefined);
                    return;
                  }
                  // Solo enteros no negativos; ignorar floats/junk.
                  const n = Number(t);
                  if (!Number.isInteger(n) || n < 0) return;
                  set(["database", "naming_conventions", "column_prefix_len"], n);
                }}
              />
            </div>
            <div style={{ height: 12 }} />
            <KeyValueField
              label="Archivos maestros de catálogo (RIDIOMA, RTABL, …)"
              value={asStrMap(g(["database", "catalog_master_files"]))}
              onChange={(m) => set(["database", "catalog_master_files"], m)}
              keyPlaceholder="RIDIOMA"
              valuePlaceholder="trunk/BD/… - Inserts RIDIOMA.sql"
            />
            <p className={styles.hint}>
              El password de la BD nunca se guarda acá — usá la sección “Credencial BD
              readonly” más abajo (cifrada con DPAPI).
            </p>
          </Section>

          {/* ── Build ── */}
          <Section title="Build">
            <div className={styles.grid2}>
              <TextField label="Herramienta" value={gs(["build", "tool"])} onChange={(v) => set(["build", "tool"], v)} placeholder={ph(["build", "tool"])} />
              <TextField label="Configuración" value={gs(["build", "configuration"])} onChange={(v) => set(["build", "configuration"], v)} placeholder={ph(["build", "configuration"])} />
              <TextField label="Ruta MSBuild" value={gs(["build", "msbuild_path"])} onChange={(v) => set(["build", "msbuild_path"], v)} placeholder={ph(["build", "msbuild_path"])} full />
              <TextField label="Comando de build" value={gs(["build", "command"])} onChange={(v) => set(["build", "command"], v)} placeholder="mvn clean verify" full />
              <TextField label="Glob de proyectos batch" value={gs(["build", "batch_proj_glob"])} onChange={(v) => set(["build", "batch_proj_glob"], v)} placeholder={ph(["build", "batch_proj_glob"])} />
            </div>
            <StringArrayField
              label="Soluciones online (.sln)"
              value={asArr(g(["build", "online_solutions"]))}
              onChange={(a) => set(["build", "online_solutions"], a)}
              placeholder="Ej: AgendaWeb.sln"
            />
          </Section>

          {/* ── Convenciones ── */}
          <Section title="Convenciones">
            <div className={styles.grid2}>
              <TextField label="Helper RIDIOMA" value={gs(["conventions", "ridioma_helper"])} onChange={(v) => set(["conventions", "ridioma_helper"], v)} placeholder={ph(["conventions", "ridioma_helper"])} />
              <TextField label="Constante de mensaje" value={gs(["conventions", "ridioma_message_const"])} onChange={(v) => set(["conventions", "ridioma_message_const"], v)} placeholder={ph(["conventions", "ridioma_message_const"])} />
              <TextField label="Sanitizer de strings" value={gs(["conventions", "string_sanitizer"])} onChange={(v) => set(["conventions", "string_sanitizer"], v)} placeholder={ph(["conventions", "string_sanitizer"])} />
            </div>
            <StringArrayField
              label="Helpers de error"
              value={asArr(g(["conventions", "error_helpers"]))}
              onChange={(a) => set(["conventions", "error_helpers"], a)}
              placeholder="Ej: Error.Agregar"
            />
          </Section>

          {/* ── Índices de docs ── */}
          <Section title="Índices de documentación">
            <div className={styles.grid2}>
              <TextField label="Índice técnico maestro" value={gs(["docs_indexes", "technical_master"])} onChange={(v) => set(["docs_indexes", "technical_master"], v)} placeholder={ph(["docs_indexes", "technical_master"])} full />
              <TextField label="Índice funcional Online" value={gs(["docs_indexes", "functional_online"])} onChange={(v) => set(["docs_indexes", "functional_online"], v)} placeholder={ph(["docs_indexes", "functional_online"])} full />
              <TextField label="Índice funcional Batch" value={gs(["docs_indexes", "functional_batch"])} onChange={(v) => set(["docs_indexes", "functional_batch"], v)} placeholder={ph(["docs_indexes", "functional_batch"])} full />
            </div>
            {pathCheck.filter((p) => p.section === "docs_indexes").length > 0 && (
              <div className={styles.pathCheckList}>
                {pathCheck
                  .filter((p) => p.section === "docs_indexes")
                  .map((p) => (
                    <div
                      key={`${p.section}.${p.key}`}
                      className={`${styles.pathCheckRow} ${p.exists ? styles.pathCheckOk : styles.pathCheckWarn}`}
                    >
                      <span className={styles.pathCheckIcon}>{p.exists ? "✓" : "⚠"}</span>
                      <span className={styles.pathCheckRel}>{p.rel}</span>
                      <span className={styles.pathCheckAbs}>{p.abs || "(sin workspace_root)"}</span>
                    </div>
                  ))}
              </div>
            )}
          </Section>

          {/* ── Máquina de estados ── */}
          <Section title="Máquina de estados del tracker" required>
            <div className={styles.roleGrid}>
              {(["functional", "technical", "developer"] as const).map((role) => (
                <TrackerRoleField
                  key={role}
                  role={role}
                  value={asObj(g(["tracker_state_machine", role]))}
                  onChange={(next) => set(["tracker_state_machine", role], next)}
                />
              ))}
            </div>
          </Section>

          {/* ── Catálogo de procesos ── */}
          <Section title="Catálogo de procesos">
            <ProcessCatalogField
              value={asArr(g(["process_catalog"]))}
              onChange={(next) => set(["process_catalog"], next)}
            />
          </Section>
        </>
      )}

      {/* ── Acciones + mensajes ── */}
      <div className={styles.card}>
        {warnings.length > 0 && (
          <div className={styles.warningsBox}>
            <strong className={styles.warningsTitle}>Advertencias del validador:</strong>
            <ul className={styles.warningsList}>
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        {stateWarnings.length > 0 && (
          <div className={styles.warningsBox}>
            <strong className={styles.warningsTitle}>
              Estados de tarea no reconocidos por el tracker:
            </strong>
            <ul className={styles.warningsList}>
              {stateWarnings.map((w, i) => (
                <li key={i}>
                  {w.agent_type}.{w.field}: "{w.value}" no existe en el tracker
                </li>
              ))}
            </ul>
          </div>
        )}
        {saveError && <div className={styles.error}>{saveError}</div>}
        {saveNotice && <div className={styles.notice}>{saveNotice}</div>}
        <div className={styles.actions} style={{ marginTop: 12 }}>
          <button className={styles.btnPrimary} onClick={onSave} disabled={saveDisabled}>
            {busy ? "Guardando…" : "Guardar perfil"}
          </button>
          <button className={styles.btnGhost} onClick={onApplyDefault} disabled={busy}>
            Aplicar template default ({trackerType})
          </button>
          {hasProfile && (
            <button className={styles.btnDanger} onClick={onClear} disabled={busy}>
              Eliminar perfil
            </button>
          )}
        </div>
      </div>

      {/* ── Credencial BD readonly ── */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h4 className={styles.cardTitle}>Credencial BD readonly</h4>
        </div>
        <p className={styles.intro}>
          La credencial se cifra con DPAPI y se guarda en{" "}
          <code>backend/projects/{projectName}/auth/db_readonly.json</code>. El
          password nunca viaja al LLM ni queda en el client_profile.
        </p>
        <div className={styles.grid2}>
          <TextField label="Server" value={dbServer} onChange={setDbServer} placeholder="aisbddev02.cloud.ais-int.net" />
          <TextField label="Base de datos (opcional)" value={dbDatabase} onChange={setDbDatabase} placeholder="Pacifico" />
          <TextField label="Usuario readonly" value={dbUser} onChange={setDbUser} placeholder="RSPACIFICOREAD" />
          <div className={styles.field}>
            <label className={styles.label}>Password</label>
            <input
              className={styles.input}
              type="password"
              value={dbPassword}
              onChange={(e) => setDbPassword(e.target.value)}
              placeholder={
                dbAuthQuery.data?.has_credentials
                  ? "(ya guardado — dejar vacío si no querés cambiarlo)"
                  : ""
              }
            />
          </div>
        </div>
        {dbError && <div className={styles.error}>{dbError}</div>}
        {dbNotice && <div className={styles.notice}>{dbNotice}</div>}
        <div className={styles.actions} style={{ marginTop: 12 }}>
          <button className={styles.btnPrimary} onClick={onSaveDbAuth} disabled={dbBusy}>
            {dbBusy
              ? "Guardando…"
              : dbAuthQuery.data?.has_credentials
                ? "Actualizar credencial"
                : "Guardar credencial"}
          </button>
        </div>
      </div>
    </div>
  );
}
