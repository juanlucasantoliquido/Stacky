import { describe, it, expect } from "vitest";
import {
  partitionTreeByClass,
  defaultActiveClasses,
  normalizeDocClass,
  DOC_CLASSES,
  type DocClass,
} from "./docTreeModel";
import type { DocNode } from "../api/endpoints";

function hoja(label: string, doc_class?: string): DocNode {
  return {
    id: `doc:${label}`,
    kind: "file",
    label,
    path: label,
    size_bytes: 1,
    headings: [],
    children: [],
    ...(doc_class === undefined ? {} : { doc_class }),
  } as DocNode;
}

function carpeta(label: string, children: DocNode[]): DocNode {
  return {
    id: `folder:${label}`,
    kind: "folder",
    label,
    path: label,
    size_bytes: 0,
    headings: [],
    doc_class: "other",
    children,
  } as DocNode;
}

const TODAS = new Set<DocClass>(DOC_CLASSES);

describe("Plan 285 F4 — partitionTreeByClass", () => {
  it("(a) con 'plan' desactivado deja solo la doc del proyecto", () => {
    const arbol = [
      hoja("101_PLAN_A.md", "plan"),
      hoja("102_PLAN_B.md", "plan"),
      hoja("103_PLAN_C.md", "plan"),
      hoja("guia.md", "project"),
      hoja("overview.md", "system"),
    ];
    const r = partitionTreeByClass(arbol, defaultActiveClasses());
    expect(r.visible).toHaveLength(2);
    expect(r.hidden).toBe(3);
    // PRESENCIA: lo que queda es exactamente la doc del proyecto.
    expect(r.visible.map((n) => n.label).sort()).toEqual(["guia.md", "overview.md"]);
  });

  it("(b) una carpeta con solo planes se poda", () => {
    const arbol = [
      carpeta("planes", [hoja("101_PLAN_A.md", "plan"), hoja("102_PLAN_B.md", "plan")]),
      hoja("guia.md", "project"),
    ];
    const r = partitionTreeByClass(arbol, defaultActiveClasses());
    expect(r.visible.map((n) => n.label)).toEqual(["guia.md"]);
    // GEMELO: con los planes activos la carpeta vuelve entera.
    const todo = partitionTreeByClass(arbol, TODAS);
    expect(todo.visible.map((n) => n.label).sort()).toEqual(["guia.md", "planes"]);
  });

  it("(c) una carpeta mixta se conserva con un solo hijo", () => {
    const arbol = [
      carpeta("docs", [hoja("101_PLAN_A.md", "plan"), hoja("guia.md", "project")]),
    ];
    const r = partitionTreeByClass(arbol, defaultActiveClasses());
    expect(r.visible).toHaveLength(1);
    expect(r.visible[0].children).toHaveLength(1);
    expect(r.visible[0].children![0].label).toBe("guia.md");
    // El nodo original NO se mutó (el filtrado devuelve copias).
    expect(arbol[0].children).toHaveLength(2);
  });

  it("(d) sin doc_class y con doc_class vacio sobreviven a cualquier filtro", () => {
    const arbol = [
      hoja("sin_clase.md"),          // backend viejo: la clave no viene
      hoja("vacia.md", ""),          // taxonomia OFF: doc_indexer.py:99 devuelve ""
      hoja("rara.md", "clase_que_no_existe"),
      hoja("101_PLAN_A.md", "plan"),
    ];
    const r = partitionTreeByClass(arbol, defaultActiveClasses());
    const labels = r.visible.map((n) => n.label).sort();
    expect(labels).toEqual(["rara.md", "sin_clase.md", "vacia.md"]);
    expect(r.counts.other).toBe(3);
    // AUSENCIA GEMELA: el plan SI se filtró (o el test pasaría por no filtrar nada).
    expect(labels).not.toContain("101_PLAN_A.md");
  });

  it("(e) counts se calcula sobre el arbol COMPLETO aunque visible este filtrado", () => {
    const arbol = [
      carpeta("docs", [
        hoja("101_PLAN_A.md", "plan"),
        hoja("102_PLAN_B.md", "plan"),
        hoja("guia.md", "project"),
      ]),
      hoja("agente.agent.md", "agent"),
    ];
    const r = partitionTreeByClass(arbol, defaultActiveClasses());
    expect(r.counts.plan).toBe(2);      // se cuentan aunque esten ocultos
    expect(r.counts.project).toBe(1);
    expect(r.counts.agent).toBe(1);
    expect(r.hidden).toBe(2);
    // El chip "Planes" tiene que poder mostrar 2 para que el operador sepa que existen.
    expect(r.visible[0].children).toHaveLength(1);
  });

  it("(f) con TODAS las clases activas el arbol queda igual y hidden es 0", () => {
    const arbol = [
      carpeta("docs", [hoja("101_PLAN_A.md", "plan"), hoja("guia.md", "project")]),
      hoja("overview.md", "system"),
    ];
    const r = partitionTreeByClass(arbol, TODAS);
    expect(r.hidden).toBe(0);
    expect(r.visible).toHaveLength(2);
    expect(r.visible[0].children).toHaveLength(2);
  });

  it("degrada ante basura sin lanzar", () => {
    const r = partitionTreeByClass([], new Set<DocClass>());
    expect(r.visible).toEqual([]);
    expect(r.hidden).toBe(0);
    expect(normalizeDocClass(undefined)).toBe("other");
    expect(normalizeDocClass("PLAN")).toBe("plan");
  });
});
