// Plan 174 F5 — Adopción verificada.
//
// Un módulo perfecto sin call site es un falso verde perfecto: los tests de
// virtualWindow/prefetchPolicy pasarían igual aunque NADIE los usara. Este test
// lee los archivos y exige que el cableado exista de verdad.
import fs from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";

const SRC = path.resolve(__dirname, "..");

function leer(rel: string): string {
  return fs.readFileSync(path.join(SRC, rel), "utf-8");
}

describe("Plan 174 — adopción cableada", () => {
  it("LogsPanel virtualiza de verdad", () => {
    const s = leer("components/LogsPanel.tsx");

    expect(s).toContain("useVirtualList(");
    expect(s).toContain("virt.start");
    expect(s).toContain("virt.end");
  });

  it("DiffList virtualiza y CONSERVA el camino de flag OFF", () => {
    // Si se perdiera el paginado, apagar la flag dejaría la lista sin forma de
    // ver más de 100 objetos.
    const s = leer("components/dbcompare/DiffList.tsx");

    expect(s).toContain("useVirtualList(");
    expect(s).toContain("PAGE_SIZE");
  });

  it("el historial tiene prefetch, sin parpadeo y con su gate", () => {
    const s = leer("pages/ExecutionHistoryPage.tsx");

    expect(s).toContain("getPrefetchProps(");
    expect(s).toContain("keepPreviousData");
    // Sin el gate, la mejora no se podría apagar.
    expect(s).toContain("instantNav");
  });

  it("los logs del sistema no parpadean y respetan su gate", () => {
    const s = leer("pages/SystemLogsPage.tsx");

    expect(s).toContain("keepPreviousData");
    expect(s).toContain("instantNav");
  });

  it("la bandeja de revisión también precarga", () => {
    expect(leer("pages/ReviewInboxPage.tsx")).toContain("getPrefetchProps(");
  });

  it("el hook throttlea y aplica el umbral en UN solo lugar", () => {
    const s = leer("hooks/useVirtualList.ts");

    expect(s).toContain("requestAnimationFrame");
    // Si el umbral se aplicara en los call sites, alguno se lo saltearía.
    expect(s).toContain("deriveIsVirtualized");
  });

  it("el presupuesto de prefetch no se afloja sin querer", () => {
    // Estos dos números son el contrato con el plan 156: cambiarlos exige tocar
    // este test a conciencia, no de pasada.
    const s = leer("services/prefetchPolicy.ts");

    expect(s).toContain("PREFETCH_MAX_CONCURRENT = 1");
    expect(s).toContain("PREFETCH_HOVER_DELAY_MS = 150");
  });

  it("roving y prefetch se COMPONEN, no se pisan", () => {
    // Un spread crudo mataría el onFocus del roving en silencio.
    for (const p of ["pages/ExecutionHistoryPage.tsx", "pages/ReviewInboxPage.tsx"]) {
      expect(leer(p)).toContain("combinarProps(");
    }
  });
});
