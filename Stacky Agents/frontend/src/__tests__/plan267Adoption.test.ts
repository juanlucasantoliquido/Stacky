// Plan 267 F7 — Adopcion del ejecutor unico y censo de severidad congelado.
//
// =========================================================================
// ESTADO REAL (actualizado tras terminar F7) — leer antes de agregarle un test.
//
// F7 quedo bloqueada una noche por un motivo de DISENO: el catalogo declaraba
// `environment` como param REQUERIDO uniforme de las 7 escrituras, y era
// vocabulario inventado (ningun endpoint lo recibia). Ese bloqueo se resolvio
// en devops_action_catalog.py declarando los params POR ACCION (`targets`
// reemplaza a `environment` donde el endpoint lo consume; `project` pasa a
// no-required donde el endpoint no lo recibe) — ver el comentario "CORRECCION
// F7" en ese archivo. Con eso resuelto, los 6 archivos SI se recablearon,
// exactamente per la tabla sitio-por-sitio de §4.11 del plan (medida el
// 2026-07-28): 2 sitios que YA confirmaban una accion del catalogo
// (`BuildWorkshopSection.tsx` "Compilar en Release", `SolutionPublisherSection.tsx`
// "Publicar <sol>") pasaron a usar `runDevOpsAction`, y 4 sitios que NO
// confirmaban nada (`RemoteConsoleSection.tsx` exec, `TriggerPipelineSection.tsx`
// disparo, `DeploymentsSection.tsx` ejecucion, `PublicationsSection.tsx` "Publicar
// en un paso...") ganaron la confirmacion derivada del catalogo que no tenian —
// una mejora de seguridad, no una regresion (R15 del plan).
//
// Los otros 16 `askConfirm({` de `components/devops/*.tsx` (Quitar contraseña,
// Eliminar servidor, Cancelar build, Eliminar borrador, Crear variable segura,
// Reemplazar pipeline x2, Crear MR/PR, Crear pipeline definition, Activar
// escritura, Agregar soluciones al catalogo, Cancelar publicacion, Registrar
// como app de despliegue, Abrir conversacion, Guardar variable, Borrar
// variable) quedan FUERA DE ALCANCE a proposito: no corresponden a ninguna de
// las 23 acciones del catalogo, y varias son `write` sin `flag_key` en
// FLAG_REGISTRY (F8 t5/t7 lo exigen). Se declaran en un plan posterior (§7.9).
//
// PublicationsSection es un caso particular: `devops.publication.run` es una
// accion DELEGADA (ver devopsActionBindings.ts DELEGATED_ACTION_IDS) porque la
// publicacion real es la cadena materializar -> commit -> trigger de
// OneClickPublishModal.tsx, no una llamada unica. F7 NO reemplaza esa cadena
// (seria aproximar con params equivocados, prohibido) sino que agrega la
// confirmacion derivada del catalogo ANTES de abrir el modal de siempre.
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

// Los 6 archivos de la lista corregida en v4 del plan (§ F7).
const RECABLEADOS = [
  'BuildWorkshopSection.tsx',
  'SolutionPublisherSection.tsx',
  'RemoteConsoleSection.tsx',
  'TriggerPipelineSection.tsx',
  'DeploymentsSection.tsx',
  'PublicationsSection.tsx',
];

describe('Plan 267 F7 — test 1: los 6 archivos adoptan runDevOpsAction', () => {
  it('1. los 6 archivos de la lista corregida importan y usan runDevOpsAction', () => {
    for (const nombre of RECABLEADOS) {
      const src = fs.readFileSync(path.join(DEVOPS_DIR, nombre), 'utf8');
      expect(src, `${nombre} no importa runDevOpsAction`).toMatch(
        /import\s*\{[^}]*\brunDevOpsAction\b[^}]*\}\s*from\s*['"]\.\.\/\.\.\/services\/devopsActionRunner['"]/,
      );
      // Import solo no alcanza: tiene que invocarse de verdad (no un import muerto).
      const invocaciones = cuenta(src, /runDevOpsAction\(/g);
      expect(invocaciones, `${nombre} importa runDevOpsAction pero no la invoca`).toBeGreaterThan(0);
    }
  });
});

describe('Plan 267 F7 — test 2 [C34]: alcance por sitio, residual exacto', () => {
  it('2a. los 2 sitios RECABLEAR de la tabla de F7 ya no existen', () => {
    const build = fs.readFileSync(path.join(DEVOPS_DIR, 'BuildWorkshopSection.tsx'), 'utf8');
    const pub = fs.readFileSync(path.join(DEVOPS_DIR, 'SolutionPublisherSection.tsx'), 'utf8');
    // sitio 1: title: "Compilar en Release" dentro de un askConfirm({ propio.
    expect(build).not.toContain('Compilar en Release');
    // sitio 2: title: `Publicar ${sol.friendly_name}` armado a mano.
    expect(pub).not.toMatch(/title:\s*`Publicar \$\{/);
  });

  it('2b. el residual de askConfirm({ es EXACTAMENTE el declarado (16 en 7 archivos)', () => {
    const RESIDUAL_ESPERADO: Record<string, number> = {
      'BuildWorkshopSection.tsx': 1,
      'SolutionPublisherSection.tsx': 4,
      'PipelineBuilderSection.tsx': 4,
      'ProductionFlow.tsx': 2,
      'RemoteConsoleSection.tsx': 1,
      'ServersSection.tsx': 2,
      'VariablesSection.tsx': 2,
    };
    const actual: Record<string, number> = {};
    for (const [archivo] of Object.entries(RESIDUAL_ESPERADO)) {
      actual[archivo] = cuenta(fs.readFileSync(path.join(DEVOPS_DIR, archivo), 'utf8'), ASK_CONFIRM);
    }
    expect(actual).toEqual(RESIDUAL_ESPERADO);
    expect(Object.values(actual).reduce((a, v) => a + v, 0)).toBe(16);
  });
});

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

  it('4/5b. test_ninguna_severidad_se_afloja — ningun archivo perdio una confirmacion danger sin recablearla', () => {
    const b = baseline();
    const actual = censoActual();
    const perdidas: string[] = [];
    for (const [archivo, congelado] of Object.entries(b)) {
      const hoy = actual[archivo];
      if (!hoy) continue; // lo caza 5a
      // Medido tras terminar F7 (no un placeholder): de los 7 sitios `danger`
      // de la tabla de §4.11, NINGUNO fue recableado — los 2 sitios que F7
      // recablea (BuildWorkshopSection "Compilar en Release",
      // SolutionPublisherSection "Publicar <sol>") tenian `danger: no`. Por
      // construccion, `recableadoAHigh` es 0 para los 7 archivos de este censo;
      // si un plan futuro recablea alguno de los 7 sitios danger, tiene que
      // sumar aca su aporte y seguir cumpliendo la igualdad.
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
