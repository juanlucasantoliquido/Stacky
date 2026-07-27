/**
 * Plan 215 F7 — tests del modelo PURO del Publicador de Soluciones.
 * Un `it` por función, con los bordes que nombra el plan.
 */
import { describe, it, expect } from "vitest";

import {
  canPublish,
  commandPreview,
  isValidExtraArg,
  needsAttention,
  parseSolutionPathsFromText,
  planReasonLabel,
  publishModeLabel,
  publishStatusLabel,
  type PublisherSolution,
} from "./solutionPublisherModel";

function sol(over: Partial<PublisherSolution> = {}): PublisherSolution {
  return {
    slug: "mi-solucion",
    sln_path: "C:\\repo\\Mi.sln",
    friendly_name: "Mi Solución",
    tracked: true,
    missing: false,
    origin: "scan",
    projects: [],
    config: {
      mode: "auto",
      configuration: "Release",
      project_csproj: null,
      publish_profile: null,
      extra_args: [],
      register_as_deploy_app: false,
      updated_at: null,
    },
    plan: {
      mode_effective: "dotnet_publish",
      supported: true,
      reason: "",
      target: "C:\\repo\\Web\\Web.csproj",
      argv_tail: ["publish", "C:\\repo\\Web\\Web.csproj"],
    },
    publish_profiles: [],
    ...over,
  };
}

describe("solutionPublisherModel (plan 215 F7)", () => {
  it("canPublish exige .sln presente, plan soportado y toolchain", () => {
    expect(canPublish(sol(), true)).toBe(true);
    // borde del plan: una solución cuyo .sln ya no está NUNCA se publica.
    expect(canPublish(sol({ missing: true }), true)).toBe(false);
    expect(
      canPublish(
        sol({ plan: { ...sol().plan, supported: false, reason: "requiere_msbuild" } }),
        true,
      ),
    ).toBe(false);
    expect(canPublish(sol(), false)).toBe(false);
  });

  it("publishStatusLabel traduce los 7 estados y no rompe con uno desconocido", () => {
    expect(publishStatusLabel("running")).toBe("Publicando…");
    expect(publishStatusLabel("success")).toBe("Publicado");
    expect(publishStatusLabel("failed")).toBe("Falló");
    expect(publishStatusLabel("cancelled")).toBe("Cancelado");
    expect(publishStatusLabel("toolchain_missing")).toBe("Falta toolchain .NET");
    expect(publishStatusLabel("unsupported")).toBe("No soportado");
    expect(publishStatusLabel("interrupted")).toBe("Interrumpido (backend reiniciado)");
    // @ts-expect-error — estado futuro del backend: se muestra crudo, no revienta.
    expect(publishStatusLabel("zarasa")).toBe("zarasa");
  });

  it("commandPreview entrecomilla SOLO los elementos con espacios", () => {
    expect(commandPreview(["msbuild", "C:\\con espacio\\a.csproj"])).toBe(
      'msbuild "C:\\con espacio\\a.csproj"',
    );
    expect(commandPreview(["dotnet", "publish", "-c", "Release"])).toBe(
      "dotnet publish -c Release",
    );
    expect(commandPreview([])).toBe("");
  });

  it("planReasonLabel mapea los códigos del backend y pasa crudo lo desconocido", () => {
    expect(planReasonLabel("requiere_dotnet_sdk")).toContain("SDK de .NET");
    expect(planReasonLabel("requiere_msbuild")).toContain("MSBuild");
    expect(planReasonLabel("sin_pubxml_filesystem")).toContain("carpeta local");
    expect(planReasonLabel("pubxml_remoto_no_soportado")).toContain("remoto");
    expect(planReasonLabel("pubxml_no_encontrado")).toContain("perfil");
    expect(planReasonLabel("toolchain_missing")).toContain("toolchain");
    expect(planReasonLabel("plan_no_resoluble")).toContain("plan de publicación");
    expect(planReasonLabel("")).toBe("");
    expect(planReasonLabel("codigo_nuevo")).toBe("codigo_nuevo");
  });

  it("parseSolutionPathsFromText limpia viñetas/comillas, ignora prosa y deduplica", () => {
    // Borde textual del plan: viñeta + comillas en la primera línea, prosa en la
    // segunda, ruta pelada en la tercera ⇒ 2 rutas.
    const rutas = parseSolutionPathsFromText('- "C:\\x\\A.sln"\ntexto\nC:\\y\\B.sln');
    expect(rutas).toEqual(["C:\\x\\A.sln", "C:\\y\\B.sln"]);
    // numeración + repetida con otra caja (Windows es case-insensitive) ⇒ 1 sola.
    expect(parseSolutionPathsFromText("1) C:\\x\\A.sln\nC:\\X\\a.SLN")).toEqual([
      "C:\\x\\A.sln",
    ]);
    expect(parseSolutionPathsFromText("")).toEqual([]);
    expect(parseSolutionPathsFromText("no hay nada acá")).toEqual([]);
  });

  it("needsAttention marca las soluciones sin .sln o con plan no soportado", () => {
    expect(needsAttention(sol())).toBe(false);
    expect(needsAttention(sol({ missing: true }))).toBe(true);
    expect(
      needsAttention(sol({ plan: { ...sol().plan, supported: false, reason: "requiere_msbuild" } })),
    ).toBe(true);
  });

  it("isValidExtraArg espeja el allowlist del backend (sin espacios ni metacaracteres)", () => {
    expect(isValidExtraArg("/p:Foo=Bar")).toBe(true);
    expect(isValidExtraArg("--no-restore")).toBe(true);
    expect(isValidExtraArg("con espacio")).toBe(false);
    expect(isValidExtraArg("rm;ls")).toBe(false);
    expect(isValidExtraArg("")).toBe(false);
  });

  it("publishModeLabel traduce los 4 modos al español", () => {
    expect(publishModeLabel("auto")).toBe("Automático");
    expect(publishModeLabel("dotnet_publish")).toContain("dotnet publish");
    expect(publishModeLabel("msbuild_pubxml")).toContain("MSBuild");
    expect(publishModeLabel("build_only")).toContain("Solo compilar");
    expect(publishModeLabel("otro")).toBe("otro");
  });
});
