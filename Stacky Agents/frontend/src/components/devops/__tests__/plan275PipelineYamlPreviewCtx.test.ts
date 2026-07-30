/**
 * plan275PipelineYamlPreviewCtx.test.ts — Plan 275 F2 (cierra H-11/B-08 de la
 * auditoría 2026-07-29: PublicationsSection.tsx:539-543 pasaba un ctx.health
 * INVENTADO a PipelineYamlPreview en vez del ctx real ya disponible en scope,
 * usado 6 líneas más abajo en PreflightPanel). Gate de grep sobre el FUENTE
 * (no hay RTL/jsdom en este repo): ningún archivo de producción bajo
 * components/devops/ puede pasar un objeto `health` literal dentro de una
 * prop `ctx=`. Se corre CONTRA el defecto: HOY da ROJO con 1 ofensor.
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const DEVOPS_DIR = path.join(process.cwd(), 'src', 'components', 'devops');
const CTX_LITERAL_RE = /ctx=\{\{\s*health:\s*\{/;

function listProdTsxFiles(dir: string): string[] {
  return (fs.readdirSync(dir, { recursive: true } as any) as string[])
    .filter((p) => p.endsWith('.tsx') && !p.includes('__tests__') && !p.includes('.test.'))
    .map((p) => path.join(dir, p));
}

describe('plan 275 F2 — ctx real en PipelineYamlPreview', () => {
  it('ningún archivo de producción de components/devops/ pasa un ctx.health inventado', () => {
    const ofensores: string[] = [];
    for (const file of listProdTsxFiles(DEVOPS_DIR)) {
      const content = fs.readFileSync(file, 'utf-8');
      if (CTX_LITERAL_RE.test(content)) ofensores.push(path.relative(DEVOPS_DIR, file));
    }
    expect(ofensores, `Objetos ctx.health literales (fabricados) en: ${ofensores.join(', ')}`).toEqual([]);
  });
});
