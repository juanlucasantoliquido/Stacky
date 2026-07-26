/** Plan 201 F9 — Modelo puro del Taller de Compilación. */
import { describe, expect, it } from "vitest";

import {
  buildStatusLabel,
  canCompile,
  compileMode,
  formatBuildDuration,
  formatBytes,
  projectTypeLabel,
  summarizeCatalog,
  trackedSlugs,
  type SolutionEntry,
  type Toolchain,
} from "./buildWorkshopModel";

const tc = (available: boolean): Toolchain => ({
  available,
  builder: available ? "dotnet" : null,
  version: available ? "8.0.404" : null,
  remediation: available
    ? null
    : { message: "Instalá el SDK", command: "winget ...", url: "https://x" },
});

const sol = (slug: string, tracked: boolean, tipos: SolutionEntry["projects"][number]["type"][]): SolutionEntry => ({
  slug,
  sln_path: `C:\\ws\\${slug}.sln`,
  sln_name: slug,
  friendly_name: slug,
  tracked,
  projects: tipos.map((t) => ({
    name: `p-${t}`,
    csproj_path: "x.csproj",
    type: t,
    target_framework: "net8.0",
  })),
});

describe("trackedSlugs", () => {
  it("devuelve solo los tildados", () => {
    expect(trackedSlugs([sol("a", true, ["web"]), sol("b", false, ["library"])])).toEqual(["a"]);
  });
  it("lista vacía", () => {
    expect(trackedSlugs([])).toEqual([]);
  });
});

describe("formatBytes", () => {
  it("cero", () => expect(formatBytes(0)).toBe("0 B"));
  it("KB", () => expect(formatBytes(1536)).toBe("1.5 KB"));
  it("MB", () => expect(formatBytes(1234567)).toBe("1.2 MB"));
  // Contrato del formateador canónico (services/format): un tamaño negativo no
  // es cero, es un dato inválido, y se muestra como tal.
  it("negativo se muestra como dato ausente", () => expect(formatBytes(-5)).toBe("—"));
});

describe("canCompile", () => {
  it("necesita toolchain Y selección", () => {
    expect(canCompile(tc(true), 1)).toBe(true);
    expect(canCompile(tc(true), 0)).toBe(false);
    expect(canCompile(tc(false), 5)).toBe(false);
  });
});

describe("compileMode", () => {
  it("varias sin unificado es inválido", () => {
    expect(compileMode(false, 2)).toBe("invalid");
  });
  it("una sola es single", () => expect(compileMode(false, 1)).toBe("single"));
  it("unificado es unified", () => expect(compileMode(true, 3)).toBe("unified"));
});

describe("buildStatusLabel", () => {
  it("traduce los estados", () => {
    expect(buildStatusLabel("running")).toBe("Compilando…");
    expect(buildStatusLabel("success")).toBe("Compilado");
    expect(buildStatusLabel("toolchain_missing")).toBe("Sin herramientas de compilación");
  });
});

describe("formatBuildDuration", () => {
  it("sin fin es 'en curso'", () => {
    expect(formatBuildDuration("2026-07-25T10:00:00Z", null)).toBe("en curso");
  });
  it("segundos", () => {
    expect(formatBuildDuration("2026-07-25T10:00:00Z", "2026-07-25T10:00:42Z")).toBe("42 s");
  });
  it("minutos", () => {
    expect(formatBuildDuration("2026-07-25T10:00:00Z", "2026-07-25T10:02:05Z")).toBe("2 min 5 s");
  });
  it("fechas rotas no rompen", () => {
    expect(formatBuildDuration("chau", "tampoco")).toBe("—");
  });
});

describe("projectTypeLabel", () => {
  it("mapea los tipos", () => {
    expect(projectTypeLabel("web")).toBe("Web");
    expect(projectTypeLabel("library")).toBe("Librería");
    expect(projectTypeLabel("unknown")).toBe("Desconocido");
  });
});

describe("summarizeCatalog", () => {
  it("cuenta total, tildadas y tipos", () => {
    const out = summarizeCatalog([
      sol("a", true, ["web", "library"]),
      sol("b", false, ["console"]),
    ]);
    expect(out).toEqual({ total: 2, tracked: 1, byType: { web: 1, library: 1, console: 1 } });
  });
  it("vacío", () => {
    expect(summarizeCatalog([])).toEqual({ total: 0, tracked: 0, byType: {} });
  });
});
