/**
 * plan275ButtonPaddingRatchet.test.ts — Plan 275 F3 (paga deuda de H-15 POR
 * CONCENTRACIÓN: el literal `style={{ padding: '10px 20px' }}` se repite 7
 * veces IDÉNTICO en los dos archivos más deudores con tráfico real de
 * components/devops/ — PipelineBuilderSection.tsx (H-15, 53 inline) y
 * PublicationsSection.tsx (H-15, 34 inline). Se extrae a `.btnLg` en
 * devops.module.css. NO es una migración masiva (H-15 la prohíbe
 * explícitamente): solo el duplicado EXACTO, mecánico, sin cambio visual.
 * Se corre CONTRA el defecto: HOY da ROJO (4 y 3 ocurrencias).
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const DEVOPS_DIR = path.join(process.cwd(), 'src', 'components', 'devops');
const LITERAL_RE = /style=\{\{ padding: '10px 20px' \}\}/g;

function count(file: string): number {
  const p = path.join(DEVOPS_DIR, file);
  const m = fs.readFileSync(p, 'utf-8').match(LITERAL_RE);
  return m ? m.length : 0;
}

describe('plan 275 F3 — dedup del literal de padding de botón', () => {
  it('PipelineBuilderSection.tsx y PublicationsSection.tsx no contienen el literal (extraído a .btnLg)', () => {
    expect(count('PipelineBuilderSection.tsx')).toBe(0);
    expect(count('PublicationsSection.tsx')).toBe(0);
  });

  it('devops.module.css declara .btnLg con el mismo padding que reemplaza', () => {
    const css = fs.readFileSync(path.join(DEVOPS_DIR, 'devops.module.css'), 'utf-8');
    expect(css).toMatch(/\.btnLg\s*\{[^}]*padding:\s*10px 20px/);
  });
});
