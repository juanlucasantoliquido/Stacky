/**
 * copyFormats.test.ts — Plan 194 F2. 20 casos enumerados del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/copyFormats.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  csvEscapeCell,
  rowsToCsv,
  mdEscapeCell,
  rowsToMarkdownTable,
  htmlEscapeCell,
  rowsToHtmlTable,
  copiedRowsLabel,
  ticketToMarkdown,
  executionToMarkdown,
  executionToPlainText,
  incidentToMarkdown,
  executionHistoryToRows,
} from "../copyFormats";
import type { Ticket, AgentExecution } from "../../types";
import type { IncidentDTO } from "../../incidents/incidentModel";
import type { ExecutionHistoryItem } from "../../api/endpoints";

const baseExec = {
  id: 42,
  ticket_id: 7,
  agent_type: "dev",
  status: "completed",
  input_context: [],
  chain_from: [],
  started_by: "op",
  started_at: "2026-07-18T10:00:00Z",
} as unknown as AgentExecution;

function mkExec(over: Partial<AgentExecution>): AgentExecution {
  return { ...baseExec, ...over } as AgentExecution;
}

const baseHistItem = {
  id: 5,
  ticket_id: 9,
  ticket_title: "T9",
  agent_type: "dev",
  agent_name: "dev",
  runtime: "claude_code_cli",
  model: "opus",
  status: "completed",
  started_at: "2026-07-18T10:00:00Z",
  finished_at: null,
  duration_ms: 1500,
  cost_usd: 0.42,
  tokens_in: null,
  tokens_out: null,
  prompt_sha: null,
  prompt_len: null,
  has_prompt_text: false,
  produced_files_count: 3,
  error_message: null,
} as ExecutionHistoryItem;

describe("copyFormats — CSV (§4.1)", () => {
  it("1 — celda simple sin comillas", () => expect(csvEscapeCell("simple")).toBe("simple"));
  it("2 — coma ⇒ comillas", () => expect(csvEscapeCell("a,b")).toBe('"a,b"'));
  it("3 — comilla interna duplicada", () => expect(csvEscapeCell('di"jo')).toBe('"di""jo"'));
  it("4 — LF ⇒ envuelto", () => expect(csvEscapeCell("l1\nl2")).toBe('"l1\nl2"'));
  it("5 — CRLF ⇒ envuelto (cubre \\r)", () => expect(csvEscapeCell("l1\r\nl2")).toBe('"l1\r\nl2"'));
  it("6 — null/undefined ⇒ vacío", () => {
    expect(csvEscapeCell(null)).toBe("");
    expect(csvEscapeCell(undefined)).toBe("");
  });
  it("7 — número/booleano ⇒ String(v)", () => {
    expect(csvEscapeCell(0)).toBe("0");
    expect(csvEscapeCell(false)).toBe("false");
  });
  it("8 — rowsToCsv golden literal (CRLF, escapes)", () => {
    expect(rowsToCsv(["a", "b"], [["1", "x,y"], [null, 'q"q']])).toBe('a,b\r\n1,"x,y"\r\n,"q""q"');
  });
  it("9 — solo header, sin CRLF final", () => expect(rowsToCsv(["a"], [])).toBe("a"));
  it("10 — sin BOM", () => expect(rowsToCsv(["a"], []).startsWith("﻿")).toBe(false));
});

describe("copyFormats — Markdown (§4.2)", () => {
  it("11 — mdEscapeCell pipes y saltos", () => {
    expect(mdEscapeCell("a|b")).toBe("a\\|b");
    expect(mdEscapeCell("l1\nl2")).toBe("l1 l2");
    expect(mdEscapeCell(null)).toBe("");
  });
  it("12 — rowsToMarkdownTable golden", () => {
    expect(rowsToMarkdownTable(["h1", "h2"], [["a", "b"]])).toBe("| h1 | h2 |\n| --- | --- |\n| a | b |");
  });
});

describe("copyFormats — entidades", () => {
  it("13 — ticketToMarkdown: ado_url gana; fallback adoUrl; sin description sin cuerpo", () => {
    const withUrl = ticketToMarkdown({
      ado_id: 100,
      title: "T",
      ado_url: "https://custom/url/100",
    } as Ticket);
    expect(withUrl).toContain("- Enlace: https://custom/url/100");
    const noUrl = ticketToMarkdown({ ado_id: 100, title: "T" } as Ticket);
    expect(noUrl).toContain("dev.azure.com");
    expect(noUrl.endsWith("edit/100")).toBe(true); // trimEnd: sin cuerpo tras los bullets
  });

  it("14 — executionToMarkdown golden completo + opcionales null", () => {
    const full = executionToMarkdown(
      mkExec({
        ticket_title: "Fix bug",
        project: "RSPACIFICO",
        agent_filename: "dev.agent.md",
        completed_at: "2026-07-18T10:05:00Z",
        duration_ms: 1500,
        verdict: "approved" as AgentExecution["verdict"],
        error_message: null,
      }),
    );
    expect(full).toBe(
      "## Ejecución #42 — dev\n\n" +
        "| Campo | Valor |\n| --- | --- |\n" +
        "| Estado | completed |\n" +
        "| Ticket | #7 — Fix bug |\n" +
        "| Proyecto | RSPACIFICO |\n" +
        "| Agente | dev.agent.md |\n" +
        "| Inicio | 2026-07-18T10:00:00Z |\n" +
        "| Fin | 2026-07-18T10:05:00Z |\n" +
        "| Duración | 1.5s |\n" +
        "| Veredicto | approved |\n" +
        "| Error | — |",
    );
    const nulls = executionToMarkdown(
      mkExec({
        ticket_title: null,
        project: null,
        agent_filename: null,
        completed_at: null,
        duration_ms: null,
        verdict: undefined,
        error_message: null,
      }),
    );
    expect(nulls).toContain("| Ticket | #7 |");
    expect(nulls).toContain("| Proyecto | n/d |");
    expect(nulls).toContain("| Fin | n/d |");
    expect(nulls).toContain("| Duración | — |");
    expect(nulls).toContain("| Veredicto | n/d |");
    expect(nulls).toContain("| Error | — |");
  });

  it("14b — executionToPlainText una sola línea", () => {
    const line = executionToPlainText(mkExec({ ticket_title: "Fix bug", duration_ms: 1500 }));
    expect(line).toBe("Ejecución #42 · dev · completed · ticket #7 (Fix bug) · 1.5s");
    expect(line.includes("\n")).toBe(false);
  });

  it("15 — incidentToMarkdown golden; tracker_url null omite paréntesis; error agrega bullet", () => {
    const base = {
      id: "inc-1",
      created_at: "2026-07-18T09:00:00Z",
      text: "algo pasó",
      files: [],
      status: "open",
      execution_id: 42,
      tracker_id: "ADO-7",
      tracker_url: null,
      epic_id: null,
      doc_path: null,
      error: null,
    } as unknown as IncidentDTO;
    const md = incidentToMarkdown(base);
    expect(md).toBe(
      "## Incidencia inc-1\n\n" +
        "- Creada: 2026-07-18T09:00:00Z\n" +
        "- Estado: open\n" +
        "- Ejecución: #42\n" +
        "- Ticket: ADO-7\n" +
        "- Adjuntos: 0\n\n" +
        "algo pasó",
    );
    const withErr = incidentToMarkdown({ ...base, title: "Caída", tracker_url: "http://t/7", error: "boom" } as IncidentDTO);
    expect(withErr).toContain("## Incidencia inc-1 — Caída");
    expect(withErr).toContain("- Ticket: ADO-7 (http://t/7)");
    expect(withErr).toContain("- Error: boom");
  });

  it("16 — executionHistoryToRows: headers exactos, crudo vs formateado, guard 1000", () => {
    const r = executionHistoryToRows([baseHistItem]);
    expect(r.headers).toEqual([
      "id", "inicio", "agente", "runtime", "modelo", "estado", "duracion_ms", "costo_usd", "archivos", "ticket",
    ]);
    expect(r.csvRows[0]).toEqual([5, "2026-07-18T10:00:00Z", "dev", "claude_code_cli", "opus", "completed", 1500, 0.42, 3, "T9"]);
    expect(r.mdRows[0]).toEqual([5, "2026-07-18T10:00:00Z", "dev", "claude_code_cli", "opus", "completed", "1.5s", "$0.42", 3, "T9"]);
    const many = Array.from({ length: 1001 }, (_, i) => ({ ...baseHistItem, id: i }));
    expect(executionHistoryToRows(many).csvRows).toHaveLength(1000);
  });
});

describe("copyFormats — HTML (§4.11) y label (C3)", () => {
  it("17 — htmlEscapeCell escapa &<>\" en orden; null ⇒ vacío", () => {
    expect(htmlEscapeCell('<b>&"x"</b>')).toBe("&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;");
    expect(htmlEscapeCell(null)).toBe("");
  });
  it("18 — rowsToHtmlTable golden", () => {
    expect(rowsToHtmlTable(["h1", "h2"], [["a", "b"]])).toBe(
      "<table><thead><tr><th>h1</th><th>h2</th></tr></thead><tbody><tr><td>a</td><td>b</td></tr></tbody></table>",
    );
  });
  it("19 — rowsToHtmlTable escapa contenido (anti-inyección)", () => {
    const out = rowsToHtmlTable(["h"], [["<img>"]]);
    expect(out).toContain("&lt;img&gt;");
    expect(out).not.toContain("<td><img></td>");
  });
  it("20 — copiedRowsLabel singular/plural/truncado", () => {
    expect(copiedRowsLabel(1)).toBe("1 fila");
    expect(copiedRowsLabel(50)).toBe("50 filas");
    expect(copiedRowsLabel(1500)).toBe("1000 de 1500 filas; límite de copia");
  });
});
