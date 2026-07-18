import { useSyncExternalStore } from "react";
import {
  getActivitySnapshot,
  markActivityRead,
  subscribeActivity,
} from "../services/activityCenter";
import {
  groupByKind,
  unreadCount,
  type ActivityEvent,
  type ActivityState,
} from "../services/activityReducer";

/**
 * Plan 152 F4 — Puente entre el store singleton y React vía useSyncExternalStore.
 * getActivitySnapshot devuelve una referencia estable entre cambios (requisito
 * del hook para no re-renderizar en bucle). SIN requests propios.
 */
export function useActivityCenter(): {
  snapshot: ActivityState;
  unread: number;
  groups: Record<string, ActivityEvent[]>;
  markRead: () => void;
} {
  const snapshot = useSyncExternalStore(
    subscribeActivity,
    getActivitySnapshot,
    getActivitySnapshot,
  );
  return {
    snapshot,
    unread: unreadCount(snapshot),
    groups: groupByKind(snapshot.events),
    markRead: markActivityRead,
  };
}
