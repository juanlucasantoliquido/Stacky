// Plan 267 F4 — El COMO. Cada binding llama al MISMO endpoint que ya usa el
// boton manual de su seccion. PROHIBIDO agregar endpoints nuevos aca (§7.4).
//
// ---------------------------------------------------------------------------
// TRES CLASES DE BINDING, y el test 7 congela exactamente quien es quien.
//
//  (a) EJECUTA   — llama a la funcion de api/endpoints.ts que ya usa el boton
//                  manual de esa seccion. Son 13.
//  (b) NAVEGA    — la accion ES "abrir la pantalla": /logs y /incidencias. La
//                  valvula esta escrita en el plan 267 F4 ("Regla de
//                  implementacion de los bindings"). Son 2.
//  (c) DELEGA    — MEDIDO: la operacion NO tiene un endpoint propio que se
//                  pueda llamar con los params que el catalogo declara. O no
//                  existe (listar publicaciones), o el "preview" en realidad
//                  CREA el artefacto (paquete de entrega), o necesita estado
//                  que solo tiene la seccion abierta (el YAML y su sha previo,
//                  el appId, la cadena de pasos del publicador). El binding
//                  lleva al operador a la seccion CON LOS PARAMETROS CARGADOS
//                  y lo dice en el recibo: no finge haber hecho algo. Son 8.
//
// Por que importa que (c) exista y este congelada: el plan asumia que las 23
// tenian endpoint. No lo tienen. La alternativa era inventar 8 endpoints —
// justo lo que §7.4 prohibe — o aproximar la llamada con params equivocados,
// que es peor: parece funcionar y hace otra cosa.
// ---------------------------------------------------------------------------
import {
  CIPipeline,
  DevOps,
  DevOpsBuildWorkshop,
  DevOpsDeployments,
  DevOpsRemoteConsole,
  DevOpsServers,
  DevOpsSolutionPublisher,
  DevOpsVariables,
  PipelineInventory,
  PrReview,
} from '../api/endpoints';
import type { DevOpsActionBinding, DevOpsActionRunContext } from './devopsActionRunner';
import { navPathWithParams } from './devopsActionRunner';
import type { DevOpsActionMeta } from './devopsActionTypes';

type Params = Record<string, string>;

const val = (p: Params, k: string): string => String(p?.[k] ?? '').trim();

/** (b)/(c) — lleva a la seccion con los parametros cargados y lo declara. */
function goToPanel(
  id: string,
  navPath: string,
  motivo: string
): DevOpsActionBinding {
  return {
    id,
    run: async (params: Params, ctx: DevOpsActionRunContext) => {
      const meta = { nav_path: navPath } as DevOpsActionMeta;
      const destino = navPathWithParams(meta, params);
      ctx.navigate(destino);
      return { ok: true, summary: `Abierto en ${destino}`, detail: motivo };
    },
  };
}

/** (a) — envuelve una llamada real y normaliza el resultado a recibo. */
function callEndpoint(
  id: string,
  summary: string,
  fn: (params: Params, ctx: DevOpsActionRunContext) => Promise<unknown>
): DevOpsActionBinding {
  return {
    id,
    run: async (params: Params, ctx: DevOpsActionRunContext) => {
      await fn(params, ctx);
      return { ok: true, summary };
    },
  };
}

/** Ids que DELEGAN en la seccion (clase c). Congelado por el test 7: si alguien
 *  agrega un id aca sin medir que su endpoint no existe, el test lo caza. */
export const DELEGATED_ACTION_IDS = [
  'devops.deployments.history',
  'devops.handoff.preview',
  'devops.pipeline_edit.commit',
  'devops.pipeline_edit.preview',
  'devops.pipelines.audit',
  'devops.pipelines.env_matrix',
  'devops.publication.run',
  'devops.publications.list',
] as const;

/** Ids cuya accion ES abrir una pantalla de fuera del panel (clase b). */
export const NAVIGATE_ONLY_ACTION_IDS = [
  'devops.incidents.list',
  'devops.logs.tail',
] as const;

export const DEVOPS_ACTION_BINDINGS: Record<string, DevOpsActionBinding> = {
  // ------------------------- (a) EJECUTAN — 13 -------------------------
  'devops.overview.refresh': callEndpoint(
    'devops.overview.refresh',
    'Resumen actualizado',
    (p) => DevOps.overview({ project: val(p, 'project') || null })
  ),
  'devops.servers.list': callEndpoint(
    'devops.servers.list',
    'Servidores listados',
    () => DevOpsServers.list()
  ),
  'devops.servers.doctor': callEndpoint(
    'devops.servers.doctor',
    'Chequeo de conexiones ejecutado',
    () => DevOps.connectionsCheck()
  ),
  'devops.environments.list': callEndpoint(
    'devops.environments.list',
    'Ambientes listados',
    (p) => DevOps.environmentPlan(val(p, 'project'))
  ),
  'devops.variables.list': callEndpoint(
    'devops.variables.list',
    'Variables listadas',
    (p) => DevOpsVariables.list(val(p, 'project'))
  ),
  'devops.pipelines.inventory': callEndpoint(
    'devops.pipelines.inventory',
    'Inventario de pipelines listado',
    (p) => PipelineInventory.list(val(p, 'project') || null)
  ),
  'devops.pr.list': callEndpoint(
    'devops.pr.list',
    'Pull requests listados',
    (p) => PrReview.list(val(p, 'project'))
  ),
  'devops.build.status': callEndpoint(
    'devops.build.status',
    'Estado de compilación leído',
    () => DevOpsBuildWorkshop.catalog()
  ),
  // El endpoint identifica la pipeline por su REF (rama): CIPipeline.preview
  // devuelve "ref resuelto + ultimo pipeline". Es la MISMA llamada que hace
  // TriggerPipelineSection.handleTrigger hoy: trigger(project, ref, '', '', true).
  'devops.pipeline.trigger': callEndpoint(
    'devops.pipeline.trigger',
    'Pipeline disparada',
    (p) => CIPipeline.trigger(val(p, 'project'), val(p, 'pipeline_id'), '', '', true)
  ),
  // `deployment_id` es el app_id; `targets` son los destinos (uno o varios,
  // separados por coma, como los junta la seccion). `confirm_text` es un extra
  // operativo que la seccion ya tiene: NO lo declara el catalogo porque no se
  // le pide al operador desde el asistente, y NO se pierde la guarda
  // type-to-confirm de los destinos protegidos.
  //
  // F7: antes leia `environment`, un enum ('dev'|'qa'|'uat'|'prod') que el
  // catalogo declaraba required. Los destinos REALES son '__local__' o el alias
  // de un servidor registrado (deploymentsModel.ts:90-96), asi que ningun valor
  // valido del enum era un destino valido: la llamada no podia funcionar, y el
  // required volvia el boton inejecutable. Ahora el param se llama como el dato
  // que el endpoint consume.
  'devops.deployment.execute': callEndpoint(
    'devops.deployment.execute',
    'Despliegue ejecutado',
    (p) =>
      DevOpsDeployments.execute(
        val(p, 'deployment_id'),
        val(p, 'targets').split(',').map((s) => s.trim()).filter(Boolean),
        true,
        val(p, 'confirm_text') || undefined
      )
  ),
  'devops.solution.publish': callEndpoint(
    'devops.solution.publish',
    'Publicación de la solución iniciada',
    (p) => DevOpsSolutionPublisher.run(val(p, 'solution_path'))
  ),
  'devops.remote_console.run': callEndpoint(
    'devops.remote_console.run',
    'Comando remoto ejecutado',
    (p) => {
      const conv = Number(val(p, 'conversation_id'));
      return DevOpsRemoteConsole.exec(
        val(p, 'server_alias'),
        val(p, 'command'),
        Number.isFinite(conv) && conv > 0 ? conv : undefined
      );
    }
  ),
  'devops.build.run': callEndpoint(
    'devops.build.run',
    'Compilación iniciada',
    (p) =>
      DevOpsBuildWorkshop.compile(
        val(p, 'solution_path').split(',').map((s) => s.trim()).filter(Boolean),
        val(p, 'unified') === 'true'
      )
  ),

  // -------------------------- (b) NAVEGAN — 2 --------------------------
  'devops.logs.tail': goToPanel(
    'devops.logs.tail',
    '/logs',
    'Esta acción es abrir la pantalla de registros con el filtro puesto.'
  ),
  'devops.incidents.list': goToPanel(
    'devops.incidents.list',
    '/incidencias',
    'Esta acción es abrir la bandeja de incidencias.'
  ),

  // -------------------------- (c) DELEGAN — 8 --------------------------
  'devops.publications.list': goToPanel(
    'devops.publications.list',
    '/devops/publicaciones',
    'Las publicaciones se leen del perfil del proyecto en esta pantalla; no hay una consulta suelta que las liste.'
  ),
  'devops.pipelines.audit': goToPanel(
    'devops.pipelines.audit',
    '/devops/pipeline-audit',
    'La auditoría necesita el contenido de la pipeline abierta en esta pantalla.'
  ),
  'devops.pipelines.env_matrix': goToPanel(
    'devops.pipelines.env_matrix',
    '/devops/matriz-entornos',
    'La comparación necesita el contenido de la pipeline abierta en esta pantalla.'
  ),
  'devops.pipeline_edit.preview': goToPanel(
    'devops.pipeline_edit.preview',
    '/devops/editar-pipeline',
    'La vista previa del cambio necesita la pipeline abierta en esta pantalla.'
  ),
  'devops.deployments.history': goToPanel(
    'devops.deployments.history',
    '/devops/despliegues',
    'El historial se pide por aplicación y destino, que se eligen en esta pantalla.'
  ),
  'devops.handoff.preview': goToPanel(
    'devops.handoff.preview',
    '/devops/paquete-entrega',
    'Armar el paquete deja un archivo en el servidor, así que la vista previa se hace desde esta pantalla.'
  ),
  'devops.pipeline_edit.commit': goToPanel(
    'devops.pipeline_edit.commit',
    '/devops/editar-pipeline',
    'Guardar el cambio necesita la versión previa exacta del archivo, que solo tiene esta pantalla.'
  ),
  'devops.publication.run': goToPanel(
    'devops.publication.run',
    '/devops/publicaciones',
    'La publicación es una secuencia de pasos que se sigue y se confirma desde esta pantalla.'
  ),
};

export function bindingFor(id: string): DevOpsActionBinding | undefined {
  return DEVOPS_ACTION_BINDINGS[id];
}

/** Plan 267 F4 — Copia EMBEBIDA de los metadatos de las acciones que algun
 *  archivo RECABLEA en F7, mas devops.build.status (que BuildWorkshopSection
 *  tambien consume para pintar el estado). Existe para que apagar
 *  STACKY_DEVOPS_ACTION_CATALOG_ENABLED (=> GET /catalog da 404) NUNCA rompa un
 *  boton que hoy funciona: runDevOpsAction cae a este mapa y sigue confirmando
 *  igual. NO es el catalogo completo: son EXACTAMENTE los 7 ids de abajo, ni uno
 *  mas ni uno menos.
 *
 *  v4 [C37]: la regla NO es "uno por seccion de F7". Es "los ids que F7
 *  recablea" + build.status. */
export const FALLBACK_META: Record<string, DevOpsActionMeta> = {
  'devops.remote_console.run': {
    id: 'devops.remote_console.run',
    label: 'Correr comando remoto',
    summary: 'Ejecuta un comando en el servidor elegido.',
    section_id: 'remote-console',
    nav_path: '/devops/remote-console',
    effect: 'write',
    impact: 'high',
    targets_environment: false,
    health_key: 'remote_console_enabled',
    flag_key: 'STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: false, enum_values: [], default: '' },
      { name: 'server_alias', type: 'string', label: 'Servidor', required: true, enum_values: [], default: '' },
      { name: 'command', type: 'string', label: 'Comando', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.build.run': {
    id: 'devops.build.run',
    label: 'Compilar solucion',
    summary: 'Compila la solucion indicada y reporta el resultado.',
    section_id: 'taller-compilacion',
    nav_path: '/devops/taller-compilacion',
    effect: 'write',
    impact: 'low',
    targets_environment: false,
    health_key: 'build_workshop_enabled',
    flag_key: 'STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: false, enum_values: [], default: '' },
      { name: 'solution_path', type: 'string', label: 'Solucion', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.build.status': {
    id: 'devops.build.status',
    label: 'Estado de compilacion',
    summary: 'Muestra como termino la ultima compilacion.',
    section_id: 'taller-compilacion',
    nav_path: '/devops/taller-compilacion',
    effect: 'read',
    impact: 'none',
    targets_environment: false,
    health_key: 'build_workshop_enabled',
    flag_key: 'STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED',
    reach: ['button', 'palette-run', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.pipeline.trigger': {
    id: 'devops.pipeline.trigger',
    label: 'Disparar pipeline',
    summary: 'Lanza una corrida de la pipeline en la rama elegida.',
    section_id: 'pipelines',
    nav_path: '/devops/pipelines',
    effect: 'write',
    impact: 'high',
    targets_environment: false,
    health_key: 'trigger_enabled',
    flag_key: 'STACKY_PIPELINE_TRIGGER_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: true, enum_values: [], default: '' },
      { name: 'pipeline_id', type: 'string', label: 'Rama o pipeline', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.deployment.execute': {
    id: 'devops.deployment.execute',
    label: 'Ejecutar despliegue',
    summary: 'Corre el despliegue elegido en los destinos elegidos.',
    section_id: 'despliegues',
    nav_path: '/devops/despliegues',
    effect: 'write',
    impact: 'high',
    targets_environment: false,
    health_key: 'deployments_execute_enabled',
    flag_key: 'STACKY_DEPLOYMENTS_EXECUTE_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: false, enum_values: [], default: '' },
      { name: 'deployment_id', type: 'string', label: 'Aplicacion', required: true, enum_values: [], default: '' },
      { name: 'targets', type: 'string', label: 'Destinos', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.publication.run': {
    id: 'devops.publication.run',
    label: 'Correr publicacion',
    summary: 'Ejecuta la publicacion elegida del proyecto activo.',
    section_id: 'publicaciones',
    nav_path: '/devops/publicaciones',
    effect: 'write',
    impact: 'high',
    targets_environment: false,
    health_key: 'one_click_publish_enabled',
    flag_key: 'STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: true, enum_values: [], default: '' },
      { name: 'publication_id', type: 'string', label: 'Publicacion', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
  'devops.solution.publish': {
    id: 'devops.solution.publish',
    label: 'Publicar solucion',
    summary: 'Compila y publica la solucion elegida.',
    section_id: 'publicador-soluciones',
    nav_path: '/devops/publicador-soluciones',
    effect: 'write',
    impact: 'high',
    targets_environment: false,
    health_key: 'solution_publisher_enabled',
    flag_key: 'STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [
      { name: 'project', type: 'string', label: 'Proyecto', required: false, enum_values: [], default: '' },
      { name: 'solution_path', type: 'string', label: 'Solucion', required: true, enum_values: [], default: '' },
    ],
    phrases: [],
  },
};

/** Metadatos de una accion, con el catalogo servido si esta, y el fallback
 *  embebido si el GET /catalog no llego (flag OFF => 404). Devuelve undefined
 *  si no hay ninguno de los dos: runDevOpsAction NO puede correr a ciegas. */
export function actionMetaFrom(
  catalogo: DevOpsActionMeta[] | null | undefined,
  id: string
): DevOpsActionMeta | undefined {
  const servido = (catalogo ?? []).find((a) => a.id === id);
  return servido ?? FALLBACK_META[id];
}

/** Metadatos de una de las 7 acciones que los botones manuales recablean (F7).
 *  Sale del fallback EMBEBIDO a proposito: asi el boton sigue confirmando con la
 *  misma severidad aunque el catalogo no se haya podido pedir (flag OFF => 404).
 *  El test 5 de devopsActionBindings.test.ts compara ese fallback campo a campo
 *  contra el .py del backend, asi que no puede aflojarse en silencio. */
export function actionMeta(id: string): DevOpsActionMeta {
  const meta = FALLBACK_META[id];
  if (!meta) {
    throw new Error(
      `plan 267 F7: ${id} no esta en FALLBACK_META; agregalo antes de recablear su boton`
    );
  }
  return meta;
}
