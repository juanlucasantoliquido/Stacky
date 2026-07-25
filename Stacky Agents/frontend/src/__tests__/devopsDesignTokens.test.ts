/**
 * devopsDesignTokens.test.ts — Plan 239 F7a.
 *
 * El CSS del panel DevOps usa la escala semántica del plan 138 (⇒ hereda densidad
 * del 150 y tema claro del 141) y no tiene ni un color crudo.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '..');
const DEVOPS_CSS_DIR = path.join(SRC, 'components/devops');
const read = (p: string) => fs.readFileSync(p, 'utf-8');

/** Hex de color: #rgb, #rrggbb, #rrggbbaa. */
const HEX = /#[0-9a-fA-F]{3,8}\b/g;

function hexes(source: string): string[] {
  return source.match(HEX) ?? [];
}

describe('Plan 239 F7a — tokens y cero color crudo', () => {
  it('DevOpsPage.module.css y DevOpsCockpit.module.css tienen 0 hex de color', () => {
    expect(hexes(read(path.join(SRC, 'pages/DevOpsPage.module.css')))).toEqual([]);
    expect(hexes(read(path.join(SRC, 'pages/DevOpsCockpit.module.css')))).toEqual([]);
  });

  it('devops.module.css tiene 0 hex de color', () => {
    expect(hexes(read(path.join(DEVOPS_CSS_DIR, 'devops.module.css')))).toEqual([]);
  });

  it('PrReviewerSection.module.css tiene 0 hex de color', () => {
    expect(hexes(read(path.join(DEVOPS_CSS_DIR, 'PrReviewerSection.module.css')))).toEqual([]);
  });

  it('ningún .module.css bajo components/devops/ tiene hex (barrido por carpeta)', () => {
    // Barrido por CARPETA, no por lista: así un archivo nuevo con hex también se caza.
    const sucios: string[] = [];
    for (const f of fs.readdirSync(DEVOPS_CSS_DIR).filter((x) => x.endsWith('.module.css'))) {
      const encontrados = hexes(read(path.join(DEVOPS_CSS_DIR, f)));
      if (encontrados.length) sucios.push(`${f}: ${encontrados.join(', ')}`);
    }
    expect(sucios).toEqual([]);
  });

  it('DevOpsCockpit.module.css no usa px crudos en padding/margin/gap', () => {
    const css = read(path.join(SRC, 'pages/DevOpsCockpit.module.css'));
    const malos: string[] = [];
    for (const linea of css.split(/\r?\n/)) {
      // grid-template-columns y minmax() sí pueden llevar px (no son spacing).
      const limpia = linea.replace(/grid-template-columns:[^;]*;?/g, '')
        .replace(/minmax\([^)]*\)/g, '')
        .replace(/max-width:[^;]*;?/g, '')
        .replace(/@media[^{]*/g, '')
        .replace(/height:[^;]*;?/g, '');
      const m = limpia.match(/\b(padding|margin|gap)[^;:]*:\s*[^;]*\d+px/);
      if (m) malos.push(linea.trim());
    }
    expect(malos).toEqual([]);
  });

  it('DevOpsPage.module.css declara al menos un @media (max-width: 900px)', () => {
    expect(read(path.join(SRC, 'pages/DevOpsPage.module.css'))).toMatch(/@media\s*\(max-width:\s*900px\)/);
  });

  it('ningún .module.css de devops usa transition con duración literal', () => {
    const archivos = [
      path.join(SRC, 'pages/DevOpsPage.module.css'),
      path.join(SRC, 'pages/DevOpsCockpit.module.css'),
      ...fs.readdirSync(DEVOPS_CSS_DIR)
        .filter((x) => x.endsWith('.module.css'))
        .map((x) => path.join(DEVOPS_CSS_DIR, x)),
    ];
    const malos: string[] = [];
    for (const f of archivos) {
      for (const linea of read(f).split(/\r?\n/)) {
        if (/transition:[^;]*\d*\.?\d+m?s\b/.test(linea)) malos.push(`${path.basename(f)}: ${linea.trim()}`);
      }
    }
    expect(malos).toEqual([]);
  });
});
