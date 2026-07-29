// Plan 267 F4 — Espejo TIPADO del catalogo backend. Sin React, sin DOM.
//
// La fuente de verdad es backend/services/devops_action_catalog.py; esto es solo
// la forma que viaja por HTTP en GET /api/devops/actions/catalog. El ratchet
// devopsActionCatalogRatchet.test.ts exige igualdad de conjuntos entre los ids
// del .py y las claves de DEVOPS_ACTION_BINDINGS.
export type DevOpsActionEffect = 'read' | 'write';
export type DevOpsActionImpact = 'none' | 'low' | 'high';

export interface DevOpsActionParamMeta {
  name: string;
  type: 'string' | 'int' | 'bool' | 'enum';
  label: string;
  required: boolean;
  enum_values: string[];
  default: string;
}

export interface DevOpsActionMeta {
  id: string;
  label: string;
  summary: string;
  section_id: string | null;
  nav_path: string;
  effect: DevOpsActionEffect;
  impact: DevOpsActionImpact;
  targets_environment: boolean;
  health_key: string;
  flag_key: string;
  /** v2 [C5] — subconjunto de 'button'|'palette-run'|'palette-nav'|'assistant'.
   *  Llega POR HTTP, asi que NO se le confia: paletteMode() mira `effect` primero. */
  reach: string[];
  params: DevOpsActionParamMeta[];
  phrases: string[];
}
