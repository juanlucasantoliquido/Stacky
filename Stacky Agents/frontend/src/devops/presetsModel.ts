/**
 * presetsModel.ts — Plan 88 F4
 *
 * Lógica pura de edición de presets de publicación + merge seguro del
 * client_profile (C2) + preview de resolución (paridad con
 * services/publication_spec.py, backend). Sin React, sin I/O.
 */

export type PublishGroup = "batch" | "agenda";

export interface PublicationPreset {
  name: string;
  mode: "selection" | "todo";
  process_names?: string[];
  groups: PublishGroup[];
  target?: "ado" | "gitlab";
}

export interface PublicationSettings {
  step_templates?: Partial<Record<"entry" | "processing" | "output" | "default", string>>;
}

const ALLOWED_GROUPS: PublishGroup[] = ["batch", "agenda"];

export function emptyPreset(): PublicationPreset {
  return { name: "", mode: "todo", groups: [], target: "gitlab" };
}

export function upsertPreset(list: PublicationPreset[], preset: PublicationPreset): PublicationPreset[] {
  const idx = list.findIndex((p) => p.name === preset.name);
  if (idx === -1) {
    return [...list, preset];
  }
  const next = [...list];
  next[idx] = preset;
  return next;
}

export function removePreset(list: PublicationPreset[], name: string): PublicationPreset[] {
  return list.filter((p) => p.name !== name);
}

export function validatePresetLocal(preset: PublicationPreset): string[] {
  const errors: string[] = [];
  if (!preset.name || !preset.name.trim()) {
    errors.push("El nombre es obligatorio.");
  } else if (preset.name.length > 120) {
    errors.push("El nombre supera 120 caracteres.");
  }
  if (preset.mode !== "selection" && preset.mode !== "todo") {
    errors.push("El modo debe ser 'selection' o 'todo'.");
  }
  if (preset.mode === "selection" && !Array.isArray(preset.process_names)) {
    errors.push("process_names debe ser una lista en mode=selection.");
  }
  const groups = preset.groups ?? [];
  if (!Array.isArray(groups) || groups.some((g) => !ALLOWED_GROUPS.includes(g))) {
    errors.push(`groups: subset de ${JSON.stringify(ALLOWED_GROUPS)}.`);
  }
  return errors;
}

/**
 * mergeKeysIntoProfile (C2) — copia superficial NUEVA, no muta el input,
 * preserva TODAS las keys ajenas. ÚNICA vía por la que la UI construye el
 * body del PUT (riel §3.9 GET→merge→PUT).
 */
export function mergeKeysIntoProfile(profile: object | null, patch: object): object {
  return { ...(profile ?? {}), ...patch };
}

interface CatalogEntry {
  name?: string;
  kind?: string;
  publish_group?: string;
  [key: string]: unknown;
}

/**
 * resolvePreview — espejo de resolve_processes (services/publication_spec.py),
 * paridad verificada por el fixture compartido plan88_resolution_cases.json.
 * `excluded` es derivado UI-only (el backend no lo computa).
 */
export function resolvePreview(
  preset: { mode?: string; process_names?: string[]; groups?: string[] },
  catalog: unknown[],
): { resolved: string[]; excluded: string[]; unknown: string[] } {
  const validEntries: CatalogEntry[] = (catalog ?? []).filter(
    (e): e is CatalogEntry =>
      typeof e === "object" && e !== null && typeof (e as CatalogEntry).name === "string" && !!(e as CatalogEntry).name?.trim(),
  );

  const unknown: string[] = [];
  let candidates: CatalogEntry[];
  if (preset.mode === "selection") {
    const processNames = preset.process_names ?? [];
    const byName = new Map(validEntries.map((e) => [e.name as string, e]));
    const matched = new Set<CatalogEntry>();
    for (const pname of processNames) {
      const entry = byName.get(pname);
      if (entry) {
        matched.add(entry);
      } else {
        unknown.push(pname);
      }
    }
    candidates = validEntries.filter((e) => matched.has(e));
  } else {
    candidates = [...validEntries];
  }

  const groups = preset.groups ?? [];
  let excluded: string[] = [];
  let resolved: CatalogEntry[];
  if (groups.length > 0) {
    resolved = candidates.filter((e) => e.publish_group && groups.includes(e.publish_group));
    excluded = candidates.filter((e) => !(e.publish_group && groups.includes(e.publish_group))).map((e) => e.name as string);
  } else {
    resolved = candidates;
  }

  return {
    resolved: resolved.map((e) => e.name as string),
    excluded,
    unknown,
  };
}

/**
 * presetsEqual (C20) — igualdad profunda vía JSON.stringify. Alimenta el
 * badge "sin guardar".
 */
export function presetsEqual(a: PublicationPreset[], b: PublicationPreset[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * draftNameForPreset — nombre único para el puente preset→borrador (ADICIÓN v3).
 * Base "preset-" + presetName recortada a <=120 chars; si colisiona, prueba
 * -2, -3, ... hasta encontrar libre (el sufijo cuenta dentro del límite de 120).
 */
export function draftNameForPreset(existingNames: string[], presetName: string): string {
  const existing = new Set(existingNames);
  const base = `preset-${presetName}`.slice(0, 120);
  if (!existing.has(base)) {
    return base;
  }
  let suffix = 2;
  while (true) {
    const suffixStr = `-${suffix}`;
    const candidate = base.slice(0, 120 - suffixStr.length) + suffixStr;
    if (!existing.has(candidate)) {
      return candidate;
    }
    suffix += 1;
  }
}
