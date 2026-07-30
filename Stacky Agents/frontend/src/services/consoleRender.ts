/**
 * Plan 265 F2 — Render rico: agrupa el stream de la consola en bloques de
 * texto/código, detecta comandos copiables y limpia secuencias ANSI.
 * Lógica pura, sin React.
 */
import type { LogLine } from "../types";

export interface RenderedChunk {
  kind: "text" | "code" | "command";
  lang: string | null; // del fence ```lang
  content: string;
  copyable: boolean; // true para "code" y "command"
}

// SGR ANSI (colores/estilos): ESC [ ...params... m
const ANSI_SGR_RE = /\x1b\[[0-9;]*m/g;

const FENCE_RE = /^```([\w-]*)\s*$/;

const COMMAND_LANGS = new Set(["bash", "sh", "powershell", "ps1", "cmd"]);
const COMMAND_PREFIXES = ["git", "npm", "npx", "python", "pytest", "dotnet", "docker"];

/** Quita secuencias de escape ANSI (colores) antes de renderizar. Los 3 runtimes
 *  pueden emitir color; en markdown se verían como basura literal. Nunca lanza. */
export function stripAnsi(text: string): string {
  if (typeof text !== "string") return "";
  return text.replace(ANSI_SGR_RE, "");
}

function makeChunk(kind: "text" | "code", lang: string | null, lines: string[]): RenderedChunk {
  return {
    kind,
    lang,
    content: lines.join("\n"),
    copyable: kind === "code",
  };
}

/** Agrupa líneas consecutivas del stream en bloques renderizables.
 *  Detecta fences ``` abiertos/cerrados. Un fence sin cerrar al final del
 *  stream se emite igual como "code" (la corrida sigue viva). Nunca lanza. */
export function groupLinesIntoChunks(lines: LogLine[]): RenderedChunk[] {
  if (!Array.isArray(lines) || lines.length === 0) return [];

  const chunks: RenderedChunk[] = [];
  let textBuf: string[] = [];
  let codeBuf: string[] = [];
  let inFence = false;
  let fenceLang: string | null = null;

  const flushText = () => {
    if (textBuf.length > 0) {
      chunks.push(makeChunk("text", null, textBuf));
      textBuf = [];
    }
  };
  const flushCode = () => {
    chunks.push(makeChunk("code", fenceLang, codeBuf));
    codeBuf = [];
    fenceLang = null;
  };

  for (const line of lines) {
    const raw = stripAnsi(typeof line?.message === "string" ? line.message : "");
    const fenceMatch = FENCE_RE.exec(raw.trim());
    if (fenceMatch) {
      if (!inFence) {
        flushText();
        inFence = true;
        fenceLang = fenceMatch[1] || null;
      } else {
        flushCode();
        inFence = false;
      }
      continue;
    }
    if (inFence) {
      codeBuf.push(raw);
    } else {
      textBuf.push(raw);
    }
  }

  if (inFence) {
    // Fence sin cerrar: la corrida sigue viva. Se emite igual, no se traga el contenido.
    flushCode();
  } else {
    flushText();
  }

  return chunks;
}

/** ¿Este bloque es un comando de shell copiable? Heurística conservadora:
 *  lang ∈ {"bash","sh","powershell","ps1","cmd"} O una sola línea que empieza
 *  con un prefijo conocido (git, npm, npx, python, pytest, dotnet, docker). */
export function isCommandChunk(chunk: RenderedChunk): boolean {
  if (!chunk) return false;
  if (chunk.lang && COMMAND_LANGS.has(chunk.lang.toLowerCase())) return true;
  const contentLines = (chunk.content || "").split("\n").filter((l) => l.trim().length > 0);
  if (contentLines.length !== 1) return false;
  const trimmed = contentLines[0].trim();
  return COMMAND_PREFIXES.some((p) => trimmed === p || trimmed.startsWith(`${p} `));
}
