// Plan 199 F5/F6 — Matemática de los gráficos nuevos del Centro de Costos.
import { describe, it, expect } from "vitest";
import { formatUsd } from "../costCenter.logic";
import {
  WEEKDAY_LABELS,
  binHeight,
  binLabel,
  distributionHeadline,
  groupColorIndex,
  heatIntensity,
  heatmapGrid,
  heatmapTooltip,
  maxBinCount,
  maxTotalOf,
  stackSegments,
  type DistributionBin,
  type StackedPoint,
} from "../costCharts.logic";

// Se reusa el formateador canónico del repo (plan 161): escribir uno a mano acá
// sumaría deuda de formato y ademas probaria un formato que la UI no usa.
const usd = formatUsd;

function punto(groups: Record<string, number>): StackedPoint {
  return {
    bucket: "2026-07-01",
    groups,
    billable_usd: Object.values(groups).reduce((a, b) => a + b, 0),
  };
}

describe("stackSegments", () => {
  it("apila de abajo hacia arriba", () => {
    const segs = stackSegments(punto({ a: 2, b: 2 }), ["a", "b"], 4, 100);

    expect(segs[0]).toMatchObject({ group: "a", value: 2, height: 50, y: 50 });
    expect(segs[1]).toMatchObject({ group: "b", value: 2, height: 50, y: 0 });
  });

  it("un grupo ausente en el punto vale cero, no rompe", () => {
    const segs = stackSegments(punto({ a: 1 }), ["a", "b"], 1, 100);

    expect(segs[1].value).toBe(0);
    expect(segs[1].height).toBe(0);
  });

  it("sin máximo no divide por cero", () => {
    const segs = stackSegments(punto({ a: 0 }), ["a"], 0, 100);

    expect(segs[0].height).toBe(0);
    expect(segs[0].y).toBe(100);
  });
});

describe("maxTotalOf", () => {
  it("toma el pico de la serie", () => {
    expect(maxTotalOf([punto({ a: 1 }), punto({ a: 5 }), punto({ a: 3 })])).toBe(5);
  });

  it("serie vacía da cero", () => {
    expect(maxTotalOf(null)).toBe(0);
  });
});

describe("groupColorIndex", () => {
  it("el mismo grupo tiene siempre el mismo índice", () => {
    // Si el color bailara entre corridas, comparar dos gráficos sería imposible.
    const grupos = ["codex_cli", "claude_code_cli"];
    expect(groupColorIndex("claude_code_cli", grupos)).toBe(1);
    expect(groupColorIndex("claude_code_cli", grupos)).toBe(1);
  });

  it("un grupo desconocido cae al primero en vez de romper", () => {
    expect(groupColorIndex("otro", ["a"])).toBe(0);
  });
});

describe("heatmapGrid", () => {
  it("siempre devuelve 7×24, con ceros donde no hubo datos", () => {
    // Un hueco en la grilla se leería como "no hay datos todavía".
    const grid = heatmapGrid([
      { weekday: 2, hour: 10, billable_usd: 3, runs: 2 },
    ]);

    expect(grid).toHaveLength(7);
    expect(grid[0]).toHaveLength(24);
    expect(grid[2][10].billable_usd).toBe(3);
    expect(grid[0][0]).toEqual({ weekday: 0, hour: 0, billable_usd: 0, runs: 0 });
  });

  it("ignora celdas fuera de rango sin romper", () => {
    const grid = heatmapGrid([
      { weekday: 9, hour: 99, billable_usd: 1, runs: 1 },
    ]);

    expect(grid).toHaveLength(7);
  });

  it("sin celdas devuelve la grilla vacía completa", () => {
    expect(heatmapGrid(null)[6][23].runs).toBe(0);
  });
});

describe("heatIntensity", () => {
  it("escala relativo al máximo", () => {
    expect(heatIntensity(5, 10)).toBe(0.5);
    expect(heatIntensity(10, 10)).toBe(1);
  });

  it("sin máximo da 0, no 1 por dividir por cero", () => {
    expect(heatIntensity(5, 0)).toBe(0);
  });

  it("clampea fuera de rango", () => {
    expect(heatIntensity(20, 10)).toBe(1);
    expect(heatIntensity(-5, 10)).toBe(0);
  });
});

describe("heatmapTooltip", () => {
  it("dice día, hora, costo y corridas", () => {
    const texto = heatmapTooltip(
      { weekday: 2, hour: 9, billable_usd: 1.5, runs: 3 }, usd);

    expect(texto).toBe("Mié 09:00 · $1.50 · 3 corrida(s)");
  });

  it("los días arrancan en lunes", () => {
    expect(WEEKDAY_LABELS[0]).toBe("Lun");
    expect(WEEKDAY_LABELS).toHaveLength(7);
  });
});

describe("distribución", () => {
  const bins: DistributionBin[] = [
    { lo: 0, hi: 1, count: 10 },
    { lo: 1, hi: 2, count: 4 },
    { lo: 2, hi: 3, count: 1 },
  ];

  it("maxBinCount toma el pico", () => {
    expect(maxBinCount(bins)).toBe(10);
    expect(maxBinCount([])).toBe(0);
  });

  it("binHeight escala y no divide por cero", () => {
    expect(binHeight(5, 10, 100)).toBe(50);
    expect(binHeight(5, 0, 100)).toBe(0);
  });

  it("binLabel muestra el rango", () => {
    expect(binLabel({ lo: 0.5, hi: 1.5, count: 1 }, usd)).toBe("$0.50 – $1.50");
  });

  it("el titular señala la cola larga, que es lo accionable", () => {
    // 1 de 15 corridas en el tercio superior: eso es lo que un promedio esconde.
    expect(distributionHeadline(bins, 15)).toContain("concentran el costo más alto");
  });

  it("sin cola larga da el conteo simple", () => {
    const parejo: DistributionBin[] = [
      { lo: 0, hi: 1, count: 5 },
      { lo: 1, hi: 2, count: 5 },
      { lo: 2, hi: 3, count: 5 },
    ];

    expect(distributionHeadline(parejo, 15)).toBe("15 corridas con costo conocido.");
  });

  it("sin datos lo dice", () => {
    expect(distributionHeadline([], 0)).toContain("Sin corridas");
    expect(distributionHeadline(null, 5)).toContain("Sin corridas");
  });
});
