/**
 * Plan 78 F2 — Hook de preferencia de UI del arnés, persistida en localStorage.
 *
 * Key: "stacky.harness.uiMode"
 * Valores: "simple" | "experto". Default: "simple" (lo menos abrumador).
 * Fallback: si localStorage no está disponible → default "simple" (sin lanzar).
 * Valor corrupto en storage → tratado como "simple".
 */

import { useState, useCallback } from "react";

export type HarnessUiMode = "simple" | "experto";

const STORAGE_KEY = "stacky.harness.uiMode";

function readMode(): HarnessUiMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "experto" ? "experto" : "simple"; // default seguro
  } catch {
    return "simple"; // SSR / storage bloqueado → default
  }
}

export function useHarnessUiPrefs() {
  const [mode, setModeState] = useState<HarnessUiMode>(readMode);

  const setMode = useCallback((m: HarnessUiMode) => {
    try {
      localStorage.setItem(STORAGE_KEY, m);
    } catch {
      /* no-op: storage bloqueado */
    }
    setModeState(m);
  }, []);

  return { mode, setMode };
}
