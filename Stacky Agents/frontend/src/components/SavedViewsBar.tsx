import { useEffect, useState } from "react";

import {
  applyView,
  computeActiveView,
  deleteView,
  EMPTY_SAVED_VIEWS,
  renameView,
  sanitizeSavedViews,
  upsertView,
  validateViewName,
  type SavedViewsState,
} from "../services/savedViews";
import {
  hydrateUiPref,
  loadUiPrefLocal,
  saveUiPref,
  useSavedViewsEnabled,
} from "../services/uiPrefs";
import { Button, ConfirmDialog, Field, Input, Select } from "./ui";
import styles from "./SavedViewsBar.module.css";

export interface SavedViewsBarProps {
  screenId: "history" | "syslogs" | "ticketBoard";
  /** Ya normalizados por el caller. */
  currentFilters: Record<string, string>;
  onApply: (filters: Record<string, string>) => void;
}

type Modo = null | "guardar" | "renombrar";

/**
 * Plan 173 F3 — Guardar la vista actual con nombre y volver a ella de un click.
 *
 * El operador reconstruye los mismos 4 filtros veinte veces al día. Esto es el
 * corazón del plan: un click en lugar de esa reconstrucción.
 *
 * Nada destructivo pasa sin confirmar — ni borrar ni sobrescribir un preset.
 */
export function SavedViewsBar({ screenId, currentFilters, onApply }: SavedViewsBarProps) {
  const enabled = useSavedViewsEnabled();
  const storeKey = `views.${screenId}`;

  const [state, setState] = useState<SavedViewsState>(() =>
    sanitizeSavedViews(loadUiPrefLocal(storeKey, EMPTY_SAVED_VIEWS)),
  );
  const [seleccion, setSeleccion] = useState("");
  const [modo, setModo] = useState<Modo>(null);
  const [nombre, setNombre] = useState("");
  const [porBorrar, setPorBorrar] = useState<string | null>(null);
  const [porSobrescribir, setPorSobrescribir] = useState<string | null>(null);

  // Lo local pinta YA; el backend gana cuando llega. Así la barra no espera a la
  // red para aparecer, pero las vistas de otra máquina terminan mandando.
  useEffect(() => {
    let vivo = true;
    void hydrateUiPref(storeKey, sanitizeSavedViews).then((remoto) => {
      if (vivo && remoto) setState(remoto);
    });
    return () => {
      vivo = false;
    };
  }, [storeKey]);

  if (!enabled) return null;

  const activa = computeActiveView(state, currentFilters);
  const errorNombre = modo ? validateViewName(nombre, state, modo === "renombrar" ? seleccion : undefined) : null;

  function persistir(nuevo: SavedViewsState) {
    setState(nuevo);
    saveUiPref(storeKey, nuevo);
  }

  function aplicar(name: string) {
    setSeleccion(name);
    if (!name) return;
    const r = applyView(state, name);
    if (!r) return;
    persistir(r.state);
    onApply(r.filters);
  }

  function confirmarGuardar(forzado = false) {
    const limpio = nombre.trim();
    const existe = state.views.some((v) => v.name.toLowerCase() === limpio.toLowerCase());
    // Pisar un preset guardado es destructivo: se pregunta antes.
    if (existe && !forzado) {
      setPorSobrescribir(limpio);
      return;
    }
    persistir(upsertView(state, limpio, currentFilters));
    setSeleccion(limpio);
    setModo(null);
  }

  function confirmarRenombrar() {
    persistir(renameView(state, seleccion, nombre.trim()));
    setSeleccion(nombre.trim());
    setModo(null);
  }

  return (
    <div className={styles.bar}>
      <Select
        aria-label="Vistas guardadas"
        className={styles.select}
        value={seleccion}
        onChange={(e) => aplicar(e.target.value)}
      >
        <option value="">Vistas…</option>
        {state.views.map((v) => (
          <option key={v.name} value={v.name}>
            {v.name === activa ? `⭐ ${v.name}` : v.name}
          </option>
        ))}
      </Select>

      {modo === null && (
        <>
          <Button
            size="sm"
            onClick={() => {
              setNombre(activa ?? "");
              setModo("guardar");
            }}
          >
            {activa ? "Actualizar" : "Guardar"}
          </Button>
          {seleccion && (
            <>
              <Button
                size="sm"
                onClick={() => {
                  setNombre(seleccion);
                  setModo("renombrar");
                }}
              >
                Renombrar
              </Button>
              <Button size="sm" onClick={() => setPorBorrar(seleccion)}>
                Borrar
              </Button>
            </>
          )}
        </>
      )}

      {modo !== null && (
        <div className={styles.editRow}>
          <Field label="Nombre de la vista" error={errorNombre ?? undefined}>
            {(ctl) => (
              <Input
                {...ctl}
                value={nombre}
                autoFocus
                onChange={(e) => setNombre(e.target.value)}
              />
            )}
          </Field>
          <Button
            size="sm"
            variant="primary"
            disabled={Boolean(errorNombre)}
            onClick={() => (modo === "guardar" ? confirmarGuardar() : confirmarRenombrar())}
          >
            Confirmar
          </Button>
          <Button size="sm" onClick={() => setModo(null)}>
            Cancelar
          </Button>
        </div>
      )}

      {state.views.length === 0 && modo === null && (
        <span className={styles.hint}>Guardá los filtros actuales para volver con un click.</span>
      )}

      <ConfirmDialog
        open={porBorrar !== null}
        title="Borrar vista"
        message={`¿Borrar la vista "${porBorrar ?? ""}"?`}
        tone="danger"
        confirmLabel="Borrar"
        onResolve={(ok) => {
          if (ok && porBorrar) {
            persistir(deleteView(state, porBorrar));
            setSeleccion("");
          }
          setPorBorrar(null);
        }}
      />

      <ConfirmDialog
        open={porSobrescribir !== null}
        title="Reemplazar vista"
        message={`Ya existe "${porSobrescribir ?? ""}". ¿Reemplazar sus filtros por los actuales?`}
        tone="danger"
        confirmLabel="Reemplazar"
        onResolve={(ok) => {
          setPorSobrescribir(null);
          if (ok) confirmarGuardar(true);
        }}
      />
    </div>
  );
}

export default SavedViewsBar;
