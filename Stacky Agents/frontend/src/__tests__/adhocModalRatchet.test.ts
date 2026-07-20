/**
 * Plan 164 F3 — Ratchet de modales ad-hoc (only-decrease).
 *
 * Congela, con allowlist explícita, los archivos .tsx que renderizan un modal
 * "a mano" (semántica de diálogo o portal propio) SIN pasar por la primitiva
 * canónica `Dialog` del barrel `ui`. La deuda solo puede BAJAR:
 *  - un .tsx NUEVO con semántica de diálogo fuera de la allowlist => FALLA
 *    (hay que migrarlo a `<Dialog>` o, si es un drawer/popover legítimo,
 *    agregarlo a la allowlist con su razón — pero eso sube el conteo y topa
 *    contra FROZEN_MAX);
 *  - migrar un modal => hay que SACARLO de la allowlist (si no, queda "stale").
 *
 * Detector CONGELADO EN EL PLAN (C7): un archivo cuenta como modal ad-hoc si:
 *  (a) es un .tsx bajo src (recursivo), NO bajo components/ui, NO en __tests__,
 *      NO con sufijo de test; y
 *  (b) su contenido matchea role="dialog" | aria-modal | createPortal( ; y
 *  (c) NO importa el símbolo `Dialog` desde el barrel `ui`.
 * Falsos positivos ACEPTADOS (drawers/paleta/popovers/tour con foco propio) van
 * a la allowlist como excepciones permanentes documentadas (§8 del plan 164).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd();
const SRC = path.join(FRONTEND_ROOT, "src");
const ALLOWLIST_PATH = path.join(SRC, "__tests__", "adhocModalAllowlist.json");

// Tope only-decrease: la allowlist NUNCA crece por encima de este valor. Al
// migrar modales, bajar este número junto con las entradas removidas.
// 22 inicial - 2 (AgentConfigModal, DataReadinessModal) - 9 migrados en la ola
// F3/F4 (AgentHistoryModal, ClaudeCliConfigModal, DailyStandupModal,
// EpicFromBriefModal, FileSelectorModal, IncidentResolverModal, QaBrowserRunModal,
// devops/DeploymentsSection, pages/TicketBoard) = 11 (solo excepciones §8).
const FROZEN_MAX = 11;

const DETECT_RE = /role="dialog"|aria-modal|createPortal\(/;
const UI_DIALOG_IMPORT_RE =
  /import\s+\{[^}]*\bDialog\b[^}]*\}\s+from\s+["'][^"']*ui["']/;

interface AllowlistEntry {
  file: string;
  reason: string;
}

function listTsx(root: string): string[] {
  const entries = fs.readdirSync(root, { recursive: true }) as string[];
  return entries
    .map((p) => p.split(path.sep).join("/"))
    .filter((p) => {
      const abs = path.join(root, p);
      return fs.existsSync(abs) && fs.statSync(abs).isFile();
    })
    .filter(
      (p) =>
        p.endsWith(".tsx") &&
        !p.startsWith("components/ui/") &&
        !p.includes("__tests__/") &&
        !p.includes(".test."),
    );
}

function detectAdhocModals(): string[] {
  const detected: string[] = [];
  for (const rel of listTsx(SRC)) {
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    if (DETECT_RE.test(content) && !UI_DIALOG_IMPORT_RE.test(content)) {
      detected.push(rel);
    }
  }
  return detected.sort();
}

function readAllowlist(): AllowlistEntry[] {
  return JSON.parse(fs.readFileSync(ALLOWLIST_PATH, "utf-8")) as AllowlistEntry[];
}

describe("adhocModalRatchet (plan 164 F3)", () => {
  it("existe la allowlist congelada", () => {
    expect(fs.existsSync(ALLOWLIST_PATH)).toBe(true);
  });

  it("todo modal ad-hoc detectado está en la allowlist (no aparecen nuevos)", () => {
    const detected = detectAdhocModals();
    const allowed = new Set(readAllowlist().map((e) => e.file));
    const notAllowed = detected.filter((f) => !allowed.has(f));
    expect(
      notAllowed,
      "Modal ad-hoc NUEVO fuera de la allowlist. Migralo a <Dialog> del barrel ui " +
        "(plan 164) o, si es un drawer/popover legítimo, documentalo en la allowlist:\n" +
        notAllowed.join("\n"),
    ).toEqual([]);
  });

  it("ninguna entrada de la allowlist quedó stale (migrada => sacarla)", () => {
    const detected = new Set(detectAdhocModals());
    const stale = readAllowlist()
      .map((e) => e.file)
      .filter((f) => !detected.has(f));
    expect(
      stale,
      "Entradas de la allowlist que ya NO son modales ad-hoc (¿migradas?). " +
        "Sacalas de la allowlist y bajá FROZEN_MAX:\n" + stale.join("\n"),
    ).toEqual([]);
  });

  it("la allowlist no crece por encima del tope only-decrease", () => {
    const allowlist = readAllowlist();
    expect(allowlist.length).toBeLessThanOrEqual(FROZEN_MAX);
    // No duplicados.
    const files = allowlist.map((e) => e.file);
    expect(new Set(files).size).toBe(files.length);
    // Toda entrada tiene una razón no vacía.
    expect(allowlist.every((e) => typeof e.reason === "string" && e.reason.length > 0)).toBe(true);
  });
});
