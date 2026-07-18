/*
 * Plan 151 F3 — Launcher "?" persistente en la topbar.
 * Re-abre el tour on-demand (KPI-6). Usa la primitiva IconButton del 138
 * (label/icon obligatorios; el label alimenta aria-label y title). El atributo
 * de ancla del tour pasa a la primitiva (extiende ButtonHTMLAttributes) y
 * cumple el ancla del step "help".
 */
import { IconButton } from "./ui";
import { useOnboardingStore } from "../store/onboardingStore";

export default function HelpLauncher() {
  const requestOpen = useOnboardingStore((s) => s.requestOpenTour);
  return (
    <IconButton
      label="Ver tour de bienvenida"
      icon="?"
      data-tour="help-launcher"
      onClick={requestOpen}
    />
  );
}
