// Plan 267 F7 — Adopcion del ejecutor unico y censo de severidad congelado.
//
// =========================================================================
// ALCANCE HONESTO DE ESTE ARCHIVO — leer antes de agregarle un test.
//
// El plan pedia 5 tests. Estan escritos 4. Los tests 1, 2 y 4 del plan
// (`los 6 archivos importan runDevOpsAction`, `los 2 sitios RECABLEAR ya no
// existen`, `ninguna severidad se afloja en un sitio recableado`) NO estan
// escritos A PROPOSITO: el recableado de F7 quedo BLOQUEADO, medido, y escribir
// esos tests como si hubiera pasado seria exactamente el falso verde que el plan
// prohibe.
//
// POR QUE quedo bloqueado, medido archivo por archivo: el catalogo declara
// `project` y `environment` como params REQUERIDOS de las acciones de escritura,
// y `runDevOpsAction` corta con ok:false ANTES de confirmar cuando falta un
// requerido (es su guarda 2, verificada por el test 11 de F4). Pero NINGUNO de
// los 6 botones manuales tiene un `environment` en alcance, y 2 no tienen ni
// `project`:
//   - BuildWorkshopSection  : 0 fuentes de project; compile(slugs, unified) no
//                             recibe proyecto ni entorno.
//   - RemoteConsoleSection  : 0 fuentes de project; exec(alias, command) opera
//                             sobre un SERVIDOR, no sobre un entorno.
//   - TriggerPipelineSection: tiene project (prop), pero lo que elige el
//                             operador es una RAMA, no un entorno.
//   - SolutionPublisherSection: tiene project; run(slug) no recibe entorno.
//   - PublicationsSection   : la publicacion es una cadena de pasos con su
//                             propio modal, no una llamada.
//   - DeploymentsSection    : tiene project y app.id, pero sus destinos son
//                             claves de tarjeta, no los valores del entorno
//                             declarados en el catalogo.
// Recablear igual dejaria los 6 botones MUERTOS ("Faltan datos obligatorios")
// en vez de hacer lo que hacen hoy. Las tres salidas posibles eran aproximar
// (pasar un entorno inventado en una accion de impacto alto), debilitar la
// guarda de requeridos, o volver `environment` opcional y romper el ratchet que
// exige que sea obligatorio. Las tres estan prohibidas, y F7 tiene su propia
// regla para este caso: "si un binding no puede reproducir exactamente el
// comportamiento del boton, se detiene la fase y se reporta; no se aproxima".
//
// Lo que SI se hizo, y es lo que protege el riesgo R1: congelar el censo de
// severidad ANTES de cualquier recableado, con un barrido del directorio, para
// que cuando F7 se descongele no pueda aflojar una severidad en silencio.
// =========================================================================
import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

const SRC = path.resolve(__dirname, '..');
const DEVOPS_DIR = path.join(SRC, 'components', 'devops');
const BASELINE = path.join(SRC, '__tests__', 'toneBaseline.json');

const ASK_CONFIRM = /askConfirm\(\{/g;
const DANGER = /tone:\s*['"]danger['"]/g;

function cuenta(texto: string, re: RegExp): number {
  const m = texto.match(re);
  return m ? m.length : 0;
}

/** Barrido del directorio, NUNCA una lista hardcodeada [C35]. */
function censoActual(): Record<string, { askConfirm: number; danger: number }> {
  const out: Record<string, { askConfirm: number; danger: number }> = {};
  for (const nombre of fs.readdirSync(DEVOPS_DIR).sort()) {
    if (!nombre.endsWith('.tsx')) continue;
    const src = fs.readFileSync(path.join(DEVOPS_DIR, nombre), 'utf8');
    const ac = cuenta(src, ASK_CONFIRM);
    if (ac === 0) continue;
    out[nombre] = { askConfirm: ac, danger: cuenta(src, DANGER) };
  }
  return out;
}

function baseline(): Record<string, { askConfirm: number; danger: number }> {
  return JSON.parse(fs.readFileSync(BASELINE, 'utf8'));
}

describe('Plan 267 F7 — un solo lugar declara la confirmacion', () => {
  it('3. devopsActionRunner.ts es el UNICO que exporta confirmRequestFor', () => {
    // Se busca la cadena LITERAL de la declaracion, no `confirmRequestFor` a
    // secas, para no cazar a los que la importan.
    const AGUJA = 'export function confirmRequestFor';
    const ofensores: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const abs = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (e.name === '__tests__' || e.name === 'node_modules') continue;
          walk(abs);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(e.name) || e.name.endsWith('.test.ts')) continue;
        if (fs.readFileSync(abs, 'utf8').includes(AGUJA)) {
          ofensores.push(path.relative(SRC, abs).split(path.sep).join('/'));
        }
      }
    };
    walk(SRC);
    expect(ofensores).toEqual(['services/devopsActionRunner.ts']);
  });
});

describe('Plan 267 §4.11 — el censo de severidad no puede encogerse ni perder un archivo', () => {
  it('5a. las claves del baseline son EXACTAMENTE los .tsx con >=1 askConfirm({', () => {
    // Es el test que impide que un octavo VariablesSection vuelva a ser
    // invisible, como le paso en las pasadas v2 y v3 de la critica.
    expect(Object.keys(baseline()).sort()).toEqual(Object.keys(censoActual()).sort());
  });

  it('5b. ningun archivo perdio una confirmacion danger sin recablearla', () => {
    const b = baseline();
    const actual = censoActual();
    const perdidas: string[] = [];
    for (const [archivo, congelado] of Object.entries(b)) {
      const hoy = actual[archivo];
      if (!hoy) continue; // lo caza 5a
      // Mientras F7 este bloqueado, `recableado_a_high` es 0 por definicion:
      // ningun sitio se recableo. Cuando F7 se descongele, este test hay que
      // extenderlo con los sitios recableados a una accion de impacto alto, y
      // la igualdad tiene que seguir valiendo.
      const recableadoAHigh = 0;
      if (hoy.danger + recableadoAHigh !== congelado.danger) {
        perdidas.push(
          `${archivo}: danger congelado=${congelado.danger}, hoy=${hoy.danger}, recableado a impacto alto=${recableadoAHigh}`
        );
      }
    }
    expect(perdidas).toEqual([]);
  });

  it('5c. el censo coincide con la tabla literal del plan (7 archivos, 18 y 7)', () => {
    const b = baseline();
    expect(Object.keys(b)).toHaveLength(7);
    expect(Object.values(b).reduce((a, v) => a + v.askConfirm, 0)).toBe(18);
    expect(Object.values(b).reduce((a, v) => a + v.danger, 0)).toBe(7);
    // El patron tiene que ser AGNOSTICO DE COMILLAS: con la comilla simple sola
    // se pierden 2 de 7, incluido SolutionPublisherSection, que es el que publica
    // en el tracker real del operador [C32].
    const soloSimple = /tone:\s*'danger'/g;
    const conAmbas = Object.keys(b).reduce(
      (acc, f) => acc + cuenta(fs.readFileSync(path.join(DEVOPS_DIR, f), 'utf8'), DANGER),
      0
    );
    const conSimple = Object.keys(b).reduce(
      (acc, f) => acc + cuenta(fs.readFileSync(path.join(DEVOPS_DIR, f), 'utf8'), soloSimple),
      0
    );
    expect(conAmbas).toBe(7);
    expect(conSimple).toBe(5); // la prueba de que el patron del v3 era ciego
  });
});
