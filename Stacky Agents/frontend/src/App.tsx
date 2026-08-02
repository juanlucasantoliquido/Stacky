import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import IncidentInboxPage from "./pages/IncidentInboxPage"; // Plan 238
import MeetingsPage from "./pages/MeetingsPage"; // Plan 283
import WorkbenchPage from "./pages/WorkbenchPage"; // Plan 293
import { INCIDENT_ICON } from "./utils/workItemTypeColor"; // Plan 238 (reuso)
import UnblockerPage from "./pages/UnblockerPage";
import SystemLogsPage from "./pages/SystemLogsPage";
import PMCommandCenter from "./pages/PMCommandCenter";
import SettingsPage from "./pages/SettingsPage";
import DocsPage from "./pages/DocsPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import MemoryPage from "./pages/MemoryPage";
import ExecutionHistoryPage from "./pages/ExecutionHistoryPage";
import ReviewInboxPage from "./pages/ReviewInboxPage";
import MigratorPage from "./pages/MigratorPage"; // Plan 74
import { DevOpsPage } from "./pages/DevOpsPage"; // Plan 87
import { DbComparePage } from "./components/dbcompare/DbComparePage"; // Plan 122
import CostCenterPage from "./pages/CostCenterPage"; // Plan 142
import PlansBoardPage from "./pages/PlansBoardPage"; // Plan 128
import EvolutionCenterPage from "./pages/EvolutionCenterPage"; // Plan 167
import TopBar from "./components/TopBar";
import HealthBanner from "./components/HealthBanner";
import ConnectionBanner from "./components/ConnectionBanner";
import CommandPalette from "./components/CommandPalette";
import DailyStandupModal from "./components/DailyStandupModal";
import OnboardingTour from "./components/OnboardingTour";
import UndoToastHost from "./components/UndoToastHost";
import ShortcutsCheatsheet from "./components/ShortcutsCheatsheet";
import DemoModeBanner from "./components/DemoModeBanner";
import CodexConsoleDock from "./components/CodexConsoleDock";
import ActiveRunsPanel from "./components/ActiveRunsPanel";
import PageErrorBoundary from "./components/PageErrorBoundary";
import { probeFlagHealth, nextEnabledState } from "./utils/flagHealth";
// Plan 273 F7 (B-01) — la maquina de tres estados del gate de tab.
import {
  type GateState, shouldRedirectAway, gateStateFromVerdict, isGateResolving, isGateOn,
} from "./services/gateState";
import { Skeleton } from "./components/ui";
import Toast, { type ToastState } from "./components/Toast";
import { toggleNavTab } from "./services/uiGuards";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { safeStorage, migrateLegacy, shouldAutoShow } from "./services/onboarding";
import { useOnboardingStore } from "./store/onboardingStore";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import { useGlobalExecutionNotifier } from "./hooks/useGlobalExecutionNotifier";
import { useGlobalShortcutListener } from "./hooks/useGlobalShortcutListener";
import { useShortcut } from "./hooks/useShortcut";
import {
  assertNoRuntimeCollisions,
  CORE_SHORTCUT_DEFS,
  setUiShortcutsEnabled,
} from "./services/shortcuts";
import { useRunActivityCapture } from "./hooks/useRunActivityCapture"; // Plan 152
import { HarnessFlags } from "./api/endpoints"; // Plan 152 — lectura del flag del centro de actividad
import { useReviewInboxCount } from "./hooks/useReviewInboxCount";
import { reviewBadgeLabel } from "./services/reviewInbox";
import AppSidebar from "./components/shell/AppSidebar";
import {
  computeVisibleTabs, parseCollapsed, SIDEBAR_COLLAPSED_KEY,
  SHELL_V2_DEFAULT, // Plan 273 F1 (B-03) — espejo del default del backend
  TAB_META,         // Plan 273 F7 (B-01) — el nombre HUMANO del tab para el aviso
} from "./components/shell/shellNav";
// Plan 273 F7 (B-01) — rastro consultable del gate apagado (misma pieza que usa
// PageErrorBoundary): el toast se va, el Centro de Actividad queda.
import { publishActivity } from "./services/activityCenter";
// Plan 165 F3 — fuente única del contrato de rutas (type Tab/TAB_PATHS/parseo).
import { parseRoute, serializeRoute, TAB_PATHS, type Tab, type RouteState } from "./services/routes";
// Plan 282 F4/F7 — los rótulos y los tabs siguen al tracker del proyecto activo.
import { useWorkbench } from "./store/workbench";
import { tituloDeTickets } from "./lib/trackerLabels";
import { tabDisponible, motivoNoDisponible } from "./lib/tabsPorTracker";
// Plan 282 F8 — los 4 kill-switches de UI viven en un módulo puro y se cargan
// desde la respuesta de /api/harness-flags que la app ya pide.
import { setTrackerUiFlags, CLAVES_DE_FLAG } from "./services/trackerUiFlags";
import styles from "./App.module.css";

export default function App() {
  // Plan 165 F3 (C1) — la ruta es ESTADO (no un ref congelado): popstate y la
  // navegación in-app la actualizan, y las páginas reciben props VIVAS (exec/subTab).
  const [route, setRoute] = useState<RouteState>(() =>
    parseRoute(window.location.pathname, window.location.search),
  );
  const tab = route.tab;  // todo el JSX existente que lee `tab` sigue idéntico
  // Plan 136 F7 — espejo del tab para handlers registrados con deps [] (el
  // closure del keydown quedaba congelado en el valor de montaje).
  const tabRef = useRef(tab);
  useEffect(() => { tabRef.current = tab; }, [tab]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);
  // Plan 273 F7 (B-01): la hidratacion del store de secciones. NO se convierte el
  // store a tri-estado (seria un refactor de un store compartido, colision
  // innecesaria): alcanza con no decidir por seccion hasta que hidrato.
  const [sectionsReady, setSectionsReady] = useState(false);
  // Plan 273 F7 (B-01): el aviso del gate apagado. Antes la redireccion era MUDA y
  // el operador leia "se perdio la pantalla". Se reusa el Toast de la casa
  // (components/Toast.tsx), montado en el shell.
  const [toast, setToast] = useState<ToastState | null>(null);
  const sections = useUiSectionsStore((s) => s.sections);
  // Plan 282 F4/F7 — tracker del proyecto activo. Misma fuente que TicketBoard
  // (Plan 276 F7); `Project.tracker_type` vive en store/workbench.
  const trackerType = useWorkbench((s) => s.activeProject?.tracker_type ?? null);
  // Plan 74: tab migrador visible solo si el flag está ON en el backend
  const [migradorGate, setMigradorGate] = useState<GateState>("unknown");
  // Plan 87: tab DevOps visible solo si el flag está ON en el backend
  const [devopsGate, setDevopsGate] = useState<GateState>("unknown");
  // Plan 122: tab Comparador BD visible solo si el flag está ON en el backend
  const [dbCompareGate, setDbCompareGate] = useState<GateState>("unknown");
  // Plan 142: tab Centro de Costos visible solo si el flag está ON en el backend
  // (default ON, C1 — pero se prueba en vivo igual que migrador/devops/dbcompare).
  const [costCenterGate, setCostCenterGate] = useState<GateState>("unknown");
  // Plan 139: App Shell v2 (sidebar agrupada) — flag leída una sola vez al montar.
  // Plan 273 F1 (B-03): el default del frontend ESPEJA el del backend
  // (STACKY_UI_SHELL_V2_ENABLED = "true", backend/config.py). Arrancar en false
  // pintaba la nav v1 en el primer paint de TODA carga y saltaba a v2 al resolver
  // el health: cambio de arquitectura de informacion visible, 100% de las cargas.
  const [shellV2Enabled, setShellV2Enabled] = useState(SHELL_V2_DEFAULT);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
    () => parseCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)),
  );
  const toggleSidebar = () => {
    setSidebarCollapsed((c) => {
      const next = !c;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "true" : "false");
      return next;
    });
  };
  // Plan 128: tab Planes visible solo si el flag está ON en el backend
  const [planesGate, setPlanesGate] = useState<GateState>("unknown");
  // Plan 167: tab Evolución visible solo si el flag está ON en el backend
  const [evolutionGate, setEvolutionGate] = useState<GateState>("unknown");
  const [incidentInboxGate, setIncidentInboxGate] = useState<GateState>("unknown"); // Plan 238
  const [meetingsGate, setMeetingsGate] = useState<GateState>("unknown"); // Plan 283
  const [publicarGate, setPublicarGate] = useState<GateState>("unknown"); // Plan 293
  // Plan 129: búsqueda profunda de la paleta (Ctrl+K) solo si el flag está ON en el backend
  const [deepSearchEnabled, setDeepSearchEnabled] = useState(false);

  // Plan 152 — Centro de Actividad: flag default ON (fail-open). Se lee del
  // registro canónico de flags vía el endpoint existente; OFF ⇒ campana oculta
  // + captura apagada (C2). No usa probeFlagHealth (135): ese es para health.
  const [notifEnabled, setNotifEnabled] = useState(true);

  useGlobalExecutionNotifier();
  useRunActivityCapture(notifEnabled); // Plan 152 F2 — reusa la query compartida (0 requests nuevos)
  const reviewCount = useReviewInboxCount();
  const reviewBadge = reviewBadgeLabel(reviewCount);

  // Plan 165 F3 [A1] — navigateToRoute: LA API de navegación tipada del router
  // casero. selectTab/navigateTo la reusan por dentro; es el punto de consumo del
  // plan 152. El pushState queda FUERA de todo updater de setState (regla §3.4
  // StrictMode: los updaters se invocan dos veces en dev → duplicarían historial).
  const navigateToRoute = (next: RouteState) => {
    const url = serializeRoute(next);
    const current = window.location.pathname + window.location.search;
    if (url !== current) window.history.pushState({}, "", url);
    setRoute(next);
  };

  // selectTab con query:{} LIMPIA el querystring al cambiar de tab (idéntico al
  // pushState(TAB_PATHS[next]) anterior); los filtros persisten en localStorage (F2).
  const selectTab = (next: Tab) => navigateToRoute({ tab: next, query: {} });

  const navigateTo = (path: string) => {           // la paleta sigue pasando strings
    const [pathname, search = ""] = path.split("?");
    navigateToRoute(parseRoute(pathname, search ? `?${search}` : ""));
  };

  useEffect(() => {
    initPreferences();
    let alive = true;
    // Plan 273 F7 (B-01): la hidratacion del store de secciones pasa a ser
    // OBSERVABLE. Antes era fire-and-forget y el efecto de redireccion decidia
    // con los defaults, asi que `team` (default oculto) rebotaba al montar.
    void initUiSections().finally(() => {
      if (alive) setSectionsReady(true);
    });
    // Plan 135 F6: solo un JSON válido con flag_enabled===true|false es
    // veredicto. Fallo de red/parseo => retry (≤2, backoff) y, si persiste,
    // "unknown" que CONSERVA el estado previo (nextEnabledState) en vez de
    // ocultar el tab toda la sesión. La desactivación real de la flag
    // (JSON ok con flag_enabled=false) sigue ocultando el tab, igual que hoy.
    void probeFlagHealth("/api/migrator/health").then((v) => {
      if (alive) setMigradorGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/devops/health").then((v) => {
      if (alive) setDevopsGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/db-compare/health").then((v) => {
      if (alive) setDbCompareGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/metrics/cost-center/health").then((v) => {
      if (alive) setCostCenterGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/plans-board/health").then((v) => {
      if (alive) setPlanesGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/evolution/health").then((v) => {
      if (alive) setEvolutionGate((prev) => gateStateFromVerdict(prev, v));
    });
    // Plan 238 — gate de la bandeja de incidencias (default ON del lado backend).
    void probeFlagHealth("/api/incident-inbox/status").then((v) => {
      if (alive) setIncidentInboxGate((prev) => gateStateFromVerdict(prev, v));
    });
    // Plan 283 — gate del tab Reuniones. Su /health responde 200 SIEMPRE, aun
    // con la capacidad apagada, para que el gate resuelva y el enlace directo
    // sobreviva; el flag_enabled del cuerpo es el veredicto.
    void probeFlagHealth("/api/meetings/health").then((v) => {
      if (alive) setMeetingsGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/workbench/health").then((v) => {   // Plan 293
      if (alive) setPublicarGate((prev) => gateStateFromVerdict(prev, v));
    });
    void probeFlagHealth("/api/search/health").then((v) => {
      if (alive) setDeepSearchEnabled((prev) => nextEnabledState(prev, v));
    });
    // Plan 139: lee la flag del shell v2 una sola vez al montar (recargar la
    // página para ver el efecto de un toggle; no hay re-montaje en caliente).
    fetch("/api/diag/health")
      .then((r) => r.json())
      .then((d: { shell_v2_enabled?: boolean; ui_shortcuts_enabled?: boolean }) => {
        // Plan 273 F1 (B-03, C8): `=== true` trataba "clave ausente" como
        // "apagado" y reintroducia el cambio de nav despues del primer paint con
        // un health 200 incompleto. `!== false` es el patron que el plan 172 F2 ya
        // uso para ui_shortcuts_enabled UNA LINEA ABAJO, por la misma razon.
        if (alive) setShellV2Enabled(d.shell_v2_enabled !== false);
        // Plan 172 F2 — default ON: una falla de red NO puede degradar el
        // teclado, así que la flag solo se toca cuando el health respondió.
        if (alive) setUiShortcutsEnabled(d.ui_shortcuts_enabled !== false);
      })
      .catch(() => {
        // Plan 273 F1 (B-03): un fallo de red NO cambia la arquitectura de
        // navegacion. Antes, un solo health fallido dejaba la nav v1 para toda la
        // sesion, sin ninguna senal al operador. Ahora se CONSERVA el optimista.
        // El .catch se deja VACIO a proposito: sin el, la promesa rechazada se
        // vuelve un unhandled rejection en consola.
      });
    return () => {
      alive = false;
    };
  }, []);

  // Plan 165 F3 (C1) — popstate re-deriva TODO el estado (tab+subtab+exec), no
  // solo el tab: Atrás/Adelante mueven sub-tab y drawer con la página ya montada.
  useEffect(() => {
    const onPopState = () =>
      setRoute(parseRoute(window.location.pathname, window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Plan 165 F3 (C5) — normalización backward-compat al montar: parseRoute ya
  // llevó /?exec= a {tab:"history"}; acá reescribimos la barra a la forma canónica.
  // replaceState (no pushState): no duplica historial ni dispara el double-push.
  useEffect(() => {
    const canonical = serializeRoute(route);
    const current = window.location.pathname + window.location.search;
    if (canonical !== current) window.history.replaceState({}, "", canonical);
  }, []);  // SOLO al montar

  // Plan 152 F3 — valor efectivo del flag del Centro de Actividad. FAIL-OPEN:
  // default ON aunque el flag no esté en la respuesta o falle la red (UI aditiva).
  useEffect(() => {
    let alive = true;
    HarnessFlags.list()
      .then((r) => {
        if (!alive) return;
        const f = r.flags.find((x) => x.key === "STACKY_NOTIFICATION_CENTER_ENABLED");
        setNotifEnabled(f ? f.value === true : true);
        // Plan 282 F8 — los 4 kill-switches de UI del eje GitLab, leídos de la
        // MISMA respuesta (cero requests extra). FAIL-OPEN: una clave ausente o
        // un fallo de red deja el comportamiento del plan, no lo apaga.
        const leer = (k: string) => {
          const s = r.flags.find((x) => x.key === k);
          return s ? s.value === true : true;
        };
        setTrackerUiFlags({
          labelsGlobal: leer(CLAVES_DE_FLAG.labelsGlobal),
          urlsRouted: leer(CLAVES_DE_FLAG.urlsRouted),
          stateFilterRouted: leer(CLAVES_DE_FLAG.stateFilterRouted),
          adoOnlyTabsGated: leer(CLAVES_DE_FLAG.adoOnlyTabsGated),
        });
      })
      .catch(() => {
        if (alive) setNotifEnabled(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Plan 151 F5 — migrar la key vieja del prototipo y auto-mostrar el tour SOLO
  // en first-run real. Este effect NO llama resetSeen (C2: nada en producción
  // la llama). Al cerrar el tour, closeTour() marca `seen` y no vuelve a
  // auto-aparecer.
  useEffect(() => {
    const s = safeStorage();
    migrateLegacy(s);
    if (shouldAutoShow(s)) {
      useOnboardingStore.getState().setOpen(true);
    }
  }, []);

  // Plan 172 F2 — los 3 atajos de siempre, ahora servidos por el registro.
  // Los combos y descripciones viven en CORE_SHORTCUT_DEFS (fuente única): acá
  // solo se adjunta el handler por id, así el overlay y el test de colisiones
  // miran el MISMO array que el runtime.
  const CORE_HANDLERS: Record<string, () => void> = {
    "palette.toggle": () => setPaletteOpen((v) => !v),
    "help.shortcuts": () => setCheatsheetOpen((v) => !v),
    // Plan 136 F7 — usar el tab ACTUAL (tabRef) y reusar selectTab, que ya
    // hace pushState con guard de pathname. PROHIBIDO meter pushState dentro
    // del updater de setTab: la app monta en <React.StrictMode> (main.tsx:13)
    // y en dev los updaters se invocan DOS veces (duplicaría el historial).
    "nav.toggle-board": () => selectTab(toggleNavTab(tabRef.current)),
  };

  useGlobalShortcutListener();
  // CORE_SHORTCUT_DEFS es una constante de módulo de longitud fija (3): la
  // cantidad de hooks no varía entre renders, así que el forEach cumple las
  // reglas de hooks. NO derivar este array de props/estado.
  CORE_SHORTCUT_DEFS.forEach((spec) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useShortcut({ ...spec, handler: CORE_HANDLERS[spec.id] }),
  );
  useEffect(() => {
    assertNoRuntimeCollisions();
  }, []);

  // Si el usuario tenía seleccionado un tab opcional que acaba de ocultarse,
  // fallback a "tickets" (la vista índice) para no quedar en blanco. Incluye
  // "team" (Mi Equipo), que ahora es ocultable y default oculto: si el deep-link
  // "/team" apunta a un equipo oculto, rebota a tickets.
  // Plan 273 F7 (B-01): DOS CADENAS INDEPENDIENTES, y la separacion es el fix de
  // C31. Las 5 ramas de seccion dependen de la hidratacion del store zustand; las
  // 7 de flag se resuelven por probeFlagHealth, que es otra via y puede resolver
  // antes, despues o nunca. Con una sola cadena, `if (!sectionsReady) return`
  // arriba apagaba TAMBIEN las 7 de flag: si el backend no responde,
  // `sectionsReady` queda false para siempre y ningun gate apagado redirige.
  // Los 5 nombres de seccion y los 7 de flag son DISJUNTOS, asi que un `tab` no
  // puede caer en las dos mitades: no hay doble selectTab ni doble aviso.
  useEffect(() => {
    const avisarYSalir = (t: Tab) => {
      const label = TAB_META[t as keyof typeof TAB_META]?.label ?? t;
      setToast({
        variant: "warning",
        title: `${label} está desactivado.`,
        body: "Esta sección se activa desde Configuración → Flags del arnés. Te llevamos a Tickets mientras tanto.",
      });
      // Rastro consultable despues de que el toast se fue (misma pieza que usa
      // PageErrorBoundary). El nombre tecnico de la flag NO va en la frase: va en
      // el enlace a Flags, via detail.flag (coherencia con F5).
      publishActivity({
        key: `gate-off:${t}`,
        kind: "error",
        // El plan decia `severity: "warning"`, pero la union de la casa
        // (activityReducer.ts:14) es "info" | "success" | "attention" | "error":
        // "attention" es el equivalente — un aviso, no una falla.
        severity: "attention",
        title: "Sección desactivada",
        body: `${label} está desactivado.`,
        ts: Date.now(),
      });
      selectTab("tickets");
    };
    if (sectionsReady) {
      if (tab === "team" && !sections.team) selectTab("tickets");
      else if (tab === "pm" && !sections.pm) selectTab("tickets");
      else if (tab === "logs" && !sections.logs) selectTab("tickets");
      else if (tab === "docs" && !sections.docs) selectTab("tickets");
      else if (tab === "memory" && !sections.memory) selectTab("tickets");
    }
    if (tab === "migrador" && shouldRedirectAway(migradorGate)) avisarYSalir("migrador");
    else if (tab === "devops" && shouldRedirectAway(devopsGate)) avisarYSalir("devops");
    else if (tab === "dbcompare" && shouldRedirectAway(dbCompareGate)) avisarYSalir("dbcompare");
    else if (tab === "costcenter" && shouldRedirectAway(costCenterGate)) avisarYSalir("costcenter");
    else if (tab === "planes" && shouldRedirectAway(planesGate)) avisarYSalir("planes");
    else if (tab === "evolution" && shouldRedirectAway(evolutionGate)) avisarYSalir("evolution");
    else if (tab === "incidencias" && shouldRedirectAway(incidentInboxGate)) avisarYSalir("incidencias");
    else if (tab === "reuniones" && shouldRedirectAway(meetingsGate)) avisarYSalir("reuniones"); // Plan 283
    else if (tab === "publicar" && shouldRedirectAway(publicarGate)) avisarYSalir("publicar"); // Plan 293
  }, [tab, sectionsReady, sections.team, sections.pm, sections.logs, sections.docs, sections.memory, migradorGate, devopsGate, dbCompareGate, costCenterGate, planesGate, evolutionGate, incidentInboxGate, meetingsGate, publicarGate]);

  const visibleTabs = computeVisibleTabs({
    sections: {
      team: !!sections.team, pm: !!sections.pm, logs: !!sections.logs,
      docs: !!sections.docs, memory: !!sections.memory,
    },
    // Plan 273 F7: un tab se MUESTRA solo si el gate resolvio ON. Con `unknown` no
    // aparece (evita que aparezca y desaparezca), PERO su ruta NO rebota: la nav
    // crece hacia arriba y el deep link sobrevive. Son cosas independientes.
    migradorEnabled: isGateOn(migradorGate),
    devopsEnabled: isGateOn(devopsGate),
    dbCompareEnabled: isGateOn(dbCompareGate),
    costCenterEnabled: isGateOn(costCenterGate),
    planesEnabled: isGateOn(planesGate),
    evolutionEnabled: isGateOn(evolutionGate),
    incidentInboxEnabled: isGateOn(incidentInboxGate), // Plan 238
    meetingsEnabled: isGateOn(meetingsGate), // Plan 283
    publicarEnabled: isGateOn(publicarGate), // Plan 293 — isGateOn, NUNCA el string
                                             // suelto: "off" es TRUTHY.
  });

  // [Contrato §3.2 Plan 139 — Plan 134] Espejo del badge de la nav v1: MISMA
  // fuente (reviewBadge = reviewBadgeLabel(reviewCount)); AppSidebar decide su
  // propia presentación (itemBadge) — no se reusa el markup navBadge de v1.
  const shellBadges: Partial<Record<Tab, ReactNode>> = {
    review: reviewBadge,
  };

  // Plan 139 §3.7 — extraído verbatim de las 14 líneas de montaje (mismos
  // condicionales exactos); un fragment de React es transparente en el DOM,
  // así que se renderiza IGUAL en ambas ramas (v1 nav / v2 sidebar): cero
  // remount extra, mismo timing de montaje/desmontaje.
  const pages = (
    <>
      {tab === "team"     && sections.team && <TeamScreen />}
      {/* Plan 287 F7/C4 — espejo exacto de la línea de `?exec=` de más abajo. Sin
          esta prop el enlace directo `?ticket=` queda CONSTRUIDO Y JAMÁS CABLEADO:
          el router lo parsea y nadie lo lee. NO agrega ningún gate de pantalla. */}
      {tab === "tickets"  && <TicketBoard ticket={route.ticket ?? null} />}
      {tab === "review"   && <ReviewInboxPage />}
      {tab === "unblocker" && <UnblockerPage />}
      {tab === "pm"       && sections.pm   && <PMCommandCenter />}
      {tab === "logs"     && sections.logs && <SystemLogsPage />}
      {tab === "settings" && <SettingsPage subTab={route.subtab ?? null} />}
      {tab === "docs"     && sections.docs && <DocsPage />}
      {tab === "memory"   && sections.memory && <MemoryPage />}
      {tab === "diagnostics" && <DiagnosticsPage />}
      {tab === "history"     && <ExecutionHistoryPage exec={route.exec ?? null} />}
      {tab === "migrador" && (isGateResolving(migradorGate)
        ? <Skeleton lines={3} />
        : isGateOn(migradorGate) && <MigratorPage />)} {/* Plan 74 */}
      {tab === "devops" && (isGateResolving(devopsGate)
        ? <Skeleton lines={3} />
        : isGateOn(devopsGate) && <DevOpsPage subTab={route.subtab ?? null} />)} {/* Plan 87 + 239 */}
      {tab === "dbcompare" && (isGateResolving(dbCompareGate)
        ? <Skeleton lines={3} />
        : isGateOn(dbCompareGate) && <DbComparePage />)} {/* Plan 122 */}
      {tab === "costcenter" && (isGateResolving(costCenterGate)
        ? <Skeleton lines={3} />
        : isGateOn(costCenterGate) && <CostCenterPage />)} {/* Plan 142 */}
      {tab === "planes" && (isGateResolving(planesGate)
        ? <Skeleton lines={3} />
        : isGateOn(planesGate) && <PlansBoardPage />)} {/* Plan 128 */}
      {tab === "evolution" && (isGateResolving(evolutionGate)
        ? <Skeleton lines={3} />
        : isGateOn(evolutionGate) && <EvolutionCenterPage />)} {/* Plan 167 */}
      {tab === "incidencias" && (isGateResolving(incidentInboxGate)
        ? <Skeleton lines={3} />
        : isGateOn(incidentInboxGate) && <IncidentInboxPage />)} {/* Plan 238 */}
      {tab === "reuniones" && (isGateResolving(meetingsGate)
        ? <Skeleton lines={3} />
        : isGateOn(meetingsGate) && <MeetingsPage />)} {/* Plan 283 */}
      {tab === "publicar" && (isGateResolving(publicarGate)
        ? <Skeleton lines={3} />
        : isGateOn(publicarGate) && <WorkbenchPage />)} {/* Plan 293 */}
    </>
  );

  return (
    <div className={styles.appRoot}>
      <DemoModeBanner />
      <TopBar
        onGoToTeam={sections.team ? () => selectTab("team") : undefined}
        shellV2={shellV2Enabled}
        notificationsEnabled={notifEnabled}
        onActivityNavigate={(nav) => selectTab(nav.tab as Tab)}
      />
      <ConnectionBanner />
      <HealthBanner />

      {shellV2Enabled ? (
        <div className={styles.shellLayout}>
          <AppSidebar
            activeTab={tab}
            onSelect={selectTab}
            visibleTabs={visibleTabs}
            collapsed={sidebarCollapsed}
            onToggleCollapsed={toggleSidebar}
            badges={shellBadges}
            trackerType={trackerType}
          />
          <main className={styles.shellContent}>
            <PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>
          </main>
        </div>
      ) : (
        <>
          {/* Tabs de navegación principal */}
          <nav className={styles.nav} data-tour="nav">
            {sections.team && (
              <button
                className={`${styles.navTab} ${tab === "team" ? styles.active : ""}`}
                onClick={() => selectTab("team")}
              >
                ⚡ Mi Equipo
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "tickets" ? styles.active : ""}`}
              onClick={() => selectTab("tickets")}
            >
              📋 {tituloDeTickets(trackerType)}
            </button>
            {isGateOn(incidentInboxGate) && (
              <button
                className={`${styles.navTab} ${tab === "incidencias" ? styles.active : ""}`}
                onClick={() => selectTab("incidencias")}
              >
                {INCIDENT_ICON} Incidencias
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "review" ? styles.active : ""}`}
              onClick={() => selectTab("review")}
            >
              🧭 Revisión
              {reviewBadge != null && (
                <span
                  className={styles.navBadge}
                  aria-label={`${reviewCount} ejecuciones esperando revisión`}
                >
                  {reviewBadge}
                </span>
              )}
            </button>
            <button
              className={`${styles.navTab} ${tab === "unblocker" ? styles.active : ""}`}
              onClick={() => selectTab("unblocker")}
            >
              🧹 Desatascador
            </button>
            {sections.pm && (
              <button
                className={`${styles.navTab} ${tab === "pm" ? styles.active : ""}`}
                onClick={() => selectTab("pm")}
                // Plan 282 F7 — se DESHABILITA con motivo, no se oculta: los
                // gates de tab que nacen `false` matan el deep link.
                disabled={!tabDisponible("pm", trackerType)}
                title={motivoNoDisponible("pm", trackerType) || undefined}
              >
                📊 PM
              </button>
            )}
            {sections.logs && (
              <button
                className={`${styles.navTab} ${tab === "logs" ? styles.active : ""}`}
                onClick={() => selectTab("logs")}
              >
                🔍 System Logs
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "settings" ? styles.active : ""}`}
              onClick={() => selectTab("settings")}
            >
              ⚙️ Configuración
            </button>
            {sections.docs && (
              <button
                className={`${styles.navTab} ${tab === "docs" ? styles.active : ""}`}
                onClick={() => selectTab("docs")}
              >
                📄 Docs
              </button>
            )}
            {sections.memory && (
              <button
                className={`${styles.navTab} ${tab === "memory" ? styles.active : ""}`}
                onClick={() => selectTab("memory")}
              >
                Memoria
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "diagnostics" ? styles.active : ""}`}
              onClick={() => selectTab("diagnostics")}
            >
              🩺 Diagnóstico
            </button>
            <button
              className={`${styles.navTab} ${tab === "history" ? styles.active : ""}`}
              onClick={() => selectTab("history")}
            >
              📋 Historial
            </button>
            {isGateOn(migradorGate) && (
              <button
                className={`${styles.navTab} ${tab === "migrador" ? styles.active : ""}`}
                onClick={() => selectTab("migrador")}
              >
                Migrador
              </button>
            )}
            {isGateOn(devopsGate) && (
              <button
                className={`${styles.navTab} ${tab === "devops" ? styles.active : ""}`}
                onClick={() => selectTab("devops")}
              >
                DevOps
              </button>
            )}
            {isGateOn(dbCompareGate) && (
              <button
                className={`${styles.navTab} ${tab === "dbcompare" ? styles.active : ""}`}
                onClick={() => selectTab("dbcompare")}
              >
                Comparador BD
              </button>
            )}
            {isGateOn(costCenterGate) && (
              <button
                className={`${styles.navTab} ${tab === "costcenter" ? styles.active : ""}`}
                onClick={() => selectTab("costcenter")}
              >
                💰 Centro de Costos
              </button>
            )}
            {isGateOn(planesGate) && (
              <button
                className={`${styles.navTab} ${tab === "planes" ? styles.active : ""}`}
                onClick={() => selectTab("planes")}
              >
                🧭 Planes
              </button>
            )}
            {isGateOn(evolutionGate) && (
              <button
                className={`${styles.navTab} ${tab === "evolution" ? styles.active : ""}`}
                onClick={() => selectTab("evolution")}
              >
                🧬 Evolución
              </button>
            )}
          </nav>

          <PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>
        </>
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={navigateTo}
        deepSearchEnabled={deepSearchEnabled}
        incidentInboxEnabled={isGateOn(incidentInboxGate)}
        onOpenShortcuts={() => setCheatsheetOpen(true)}
      />
      <ShortcutsCheatsheet
        open={cheatsheetOpen}
        onClose={() => setCheatsheetOpen(false)}
      />
      <DailyStandupModal />
      <OnboardingTour />

      {/* Plan 185 — host global de toasts de "Deshacer" (undo universal con
          gracia). Capa 2 esquina inferior derecha; ver tabla 197 §6.11. */}
      <UndoToastHost />
      {/* Plan 273 F7 (B-01): aviso del gate apagado. Toast es export default y sus
          props son {toast, onClose, inStack?} — NO `variant`/`body` sueltos, que es
          la forma del tipo ToastState (C27). */}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}

      {/* Consola flotante de runtimes CLI (Codex / Claude): muestra la actividad
          en vivo y permite responderle al agente. Se activa al lanzar un run CLI. */}
      <CodexConsoleDock />

      {/* Panel global de ejecuciones activas: permite cancelar manualmente
          cualquier run en curso (incluidos huérfanos/colgados de otro proyecto
          que el board no muestra). Solo aparece si hay runs activos. */}
      <ActiveRunsPanel />
    </div>
  );
}
