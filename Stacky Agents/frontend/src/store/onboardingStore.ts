import { create } from "zustand";
import { markSeen, safeStorage } from "../services/onboarding";

/**
 * Plan 151 F3 — Store compartido del tour (zustand, mismo patrón que
 * store/uiSectionsStore.ts).
 *
 * C2 (regla dura): `requestOpenTour` NO llama `resetSeen`. El "visto" solo
 * transiciona a `seen` (nunca al revés) en producción. Re-abrir el tour
 * on-demand y recargar a mitad NUNCA re-activa el auto-show.
 * El auto-show inicial NO decide con el store: usa `shouldAutoShow` en el
 * effect de F5 y luego llama `setOpen(true)`.
 */
interface OnboardingState {
  open: boolean;
  /** On-demand (launcher "?", Configuración, paleta): SOLO abre. NO toca seen. */
  requestOpenTour: () => void;
  /** Cierra + marca visto (idempotente). Única transición de `seen` en prod. */
  closeTour: () => void;
  /** Usado por el auto-show de F5. */
  setOpen: (v: boolean) => void;
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  open: false,
  requestOpenTour: () => set({ open: true }),
  closeTour: () => {
    markSeen(safeStorage());
    set({ open: false });
  },
  setOpen: (v) => set({ open: v }),
}));
