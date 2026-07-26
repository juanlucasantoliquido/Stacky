// Plan 174 F2 — ¿El operador está mirando el fondo de una lista que crece?
//
// El holgura existe porque el scroll no cae siempre en un múltiplo exacto de la
// altura de fila: sin ella, estar "al fondo" fallaría por 3 píxeles y el
// autoscroll se cortaría solo.

export const STICK_SLACK_PX = 40;

export function isPinnedToBottom(
  scrollTopPx: number,
  viewportHeightPx: number,
  contentHeightPx: number,
  slackPx: number = STICK_SLACK_PX,
): boolean {
  return contentHeightPx - (scrollTopPx + viewportHeightPx) <= slackPx;
}
