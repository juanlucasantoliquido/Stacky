// Plan 175 F1 — Punto ÚNICO de confirmación de las acciones con efecto.
//
// Human-in-the-loop innegociable: todo lo que muta algo pasa por acá. Tenerlo en
// un solo módulo es lo que permite cambiar CÓMO se pregunta sin tocar ninguna
// acción — hoy delega en el diálogo canónico del plan 164.
//
// PROHIBIDO usar los diálogos nativos del navegador en cualquier versión:
// bloquean el hilo y el arnés no puede verlos.

export interface ConfirmRequest {
  title: string;
  message: string;
  confirmLabel: string;
  tone: "default" | "danger";
}

export type ConfirmFn = (req: ConfirmRequest) => Promise<boolean>;

/** Gateway por defecto: NIEGA. Una acción sin gateway cableado no puede
 *  ejecutarse "porque sí" — el default seguro es no hacer nada. */
export const denyByDefault: ConfirmFn = async () => false;
