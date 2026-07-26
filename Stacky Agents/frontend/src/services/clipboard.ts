// Plan 175 F1 — El único punto de copiado de este plan.
//
// Delega en el copyService del plan 194: reimplementar el copiado acá rompería
// su ratchet (que prohíbe llamadas crudas nuevas a writeText) y además duplicaría
// el fallback para contextos sin portapapeles asíncrono.

import { copyText as copyServiceText } from "./copyService";

export async function copyText(text: string): Promise<boolean> {
  const r = await copyServiceText(text);
  return Boolean(r?.ok);
}
