import {
  createContext,
  useCallback,
  useContext,
  useReducer,
  useRef,
  ReactNode,
} from "react";
import ConfirmDialog from "./ConfirmDialog";
import AlertDialog from "./AlertDialog";
import PromptDialog from "./PromptDialog";
import {
  dialogHostReducer,
  dismissValueFor,
  type DialogRequest,
  type DialogHostState,
} from "./dialogHostReducer";

/**
 * Plan 164 F1 — Host global de diálogos promise-based. Montado UNA vez alrededor
 * de <App/> (main.tsx). Expone useConfirm/useAlert/useTextPrompt: cada uno
 * devuelve una función async awaitable. REGLA DURA (C1): toda vía de cierre
 * RESUELVE la promesa (settle idempotente); ningún await queda colgado.
 */
export interface ConfirmOpts {
  title?: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
}

export interface AlertOpts {
  title?: ReactNode;
  message: ReactNode;
  okLabel?: string;
}

export interface TextPromptOpts {
  title?: ReactNode;
  message?: ReactNode;
  label?: ReactNode;
  initialValue?: string;
  requiredText?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
}

interface DialogHostContextValue {
  requestConfirm: (opts: ConfirmOpts) => Promise<boolean>;
  requestAlert: (opts: AlertOpts) => Promise<void>;
  requestTextPrompt: (opts: TextPromptOpts) => Promise<string | null>;
}

const DialogHostContext = createContext<DialogHostContextValue | null>(null);

const INITIAL: DialogHostState = { queue: [], current: null };

export default function DialogHost({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(dialogHostReducer, INITIAL);
  const idSeq = useRef(0);
  const settledRef = useRef<Set<string>>(new Set());

  // C1: settle idempotente — la primera resolución gana; nunca re-avanza la cola.
  const settle = useCallback((req: DialogRequest, value: unknown) => {
    if (settledRef.current.has(req.id)) return;
    settledRef.current.add(req.id);
    req.resolve?.(value);
    dispatch({ type: "resolveCurrent", id: req.id });
  }, []);

  const enqueue = useCallback(
    <T,>(kind: DialogRequest["kind"], opts: Record<string, unknown>): Promise<T> =>
      new Promise<T>((resolve) => {
        idSeq.current += 1;
        const id = `dlg-${idSeq.current}`;
        dispatch({
          type: "enqueue",
          request: { id, kind, opts, resolve: resolve as (v: unknown) => void },
        });
      }),
    [],
  );

  const requestConfirm = useCallback(
    (opts: ConfirmOpts) => enqueue<boolean>("confirm", opts as unknown as Record<string, unknown>),
    [enqueue],
  );
  const requestAlert = useCallback(
    (opts: AlertOpts) => enqueue<void>("alert", opts as unknown as Record<string, unknown>),
    [enqueue],
  );
  const requestTextPrompt = useCallback(
    (opts: TextPromptOpts) =>
      enqueue<string | null>("prompt", opts as unknown as Record<string, unknown>),
    [enqueue],
  );

  const ctx: DialogHostContextValue = {
    requestConfirm,
    requestAlert,
    requestTextPrompt,
  };

  const current = state.current;

  return (
    <DialogHostContext.Provider value={ctx}>
      {children}
      {current && current.kind === "confirm" && (
        <ConfirmDialog
          key={current.id}
          open
          {...(current.opts as unknown as ConfirmOpts)}
          onResolve={(ok) => settle(current, ok)}
        />
      )}
      {current && current.kind === "alert" && (
        <AlertDialog
          key={current.id}
          open
          {...(current.opts as unknown as AlertOpts)}
          onResolve={() => settle(current, dismissValueFor("alert"))}
        />
      )}
      {current && current.kind === "prompt" && (
        <PromptDialog
          key={current.id}
          open
          {...(current.opts as unknown as TextPromptOpts)}
          onResolve={(value) => settle(current, value)}
        />
      )}
    </DialogHostContext.Provider>
  );
}

export function useConfirm(): (opts: ConfirmOpts) => Promise<boolean> {
  const ctx = useContext(DialogHostContext);
  if (!ctx) throw new Error("useConfirm debe usarse dentro de <DialogHost>");
  return ctx.requestConfirm;
}

export function useAlert(): (opts: AlertOpts) => Promise<void> {
  const ctx = useContext(DialogHostContext);
  if (!ctx) throw new Error("useAlert debe usarse dentro de <DialogHost>");
  return ctx.requestAlert;
}

export function useTextPrompt(): (opts: TextPromptOpts) => Promise<string | null> {
  const ctx = useContext(DialogHostContext);
  if (!ctx) throw new Error("useTextPrompt debe usarse dentro de <DialogHost>");
  return ctx.requestTextPrompt;
}
