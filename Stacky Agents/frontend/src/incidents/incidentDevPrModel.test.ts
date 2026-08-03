import { describe, it, expect } from "vitest";
import {
  DEFAULT_OPEN_PR,
  shouldShowOpenPrCheckbox,
  describeOpenPrControl,
  describePrResult,
  etiquetaProveedor,
  resumirEstadoDeRepos,
  PREFLIGHT_CAIDO,
  type DevPrPreflight,
  type DevPrResultDTO,
} from "./incidentDevPrModel";

/** Copia literal del texto de "cargando": si alguien lo cambia y el caído
 *  empieza a mostrarlo, el test de abajo lo detecta. */
const ESPERANDO_TEXTO = "Verificando el repositorio git del proyecto…";

describe("incidentDevPrModel", () => {
  it("DEFAULT_OPEN_PR es true (premarcado)", () => {
    expect(DEFAULT_OPEN_PR).toBe(true);
  });

  it("muestra el checkbox cuando canResolve && devPrEnabled", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: true, devPrEnabled: true })).toBe(true);
  });

  it("oculta el checkbox si devPrEnabled es false", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: true, devPrEnabled: false })).toBe(false);
  });

  it("oculta el checkbox si canResolve es false", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: false, devPrEnabled: true })).toBe(false);
  });
});

// ── Chequeo previo de repo git ↔ estado del tilde ────────────────────────────

const okPreflight: DevPrPreflight = {
  ok: true,
  reason: null,
  message: "",
  warning: null,
  warning_message: "",
  repo_root: "N:/repo",
  origin: "https://gitlab.local/g/p.git",
  workspace_root: "N:/repo/ws",
  tracker_type: "gitlab",
  provider_label: "gitlab", // crudo: el backend manda el `name` del provider
  project: "RSPACIFICO",
};

function preflightRoto(reason: string, message: string): DevPrPreflight {
  return { ...okPreflight, ok: false, reason, message, repo_root: null, provider_label: null };
}

describe("resumirEstadoDeRepos (vista de conjunto)", () => {
  const fila = (p: Partial<DevPrPreflight> & { project: string }): DevPrPreflight => ({
    ...okPreflight, ...p,
  });

  it("cuenta los que tienen git y los que no", () => {
    const r = resumirEstadoDeRepos({
      ok: true, total: 3, con_git: 2, dev_pr_enabled: true, message: "",
      projects: [
        fila({ project: "A" }),
        fila({ project: "B" }),
        fila({ project: "C", ok: false, reason: "no_es_repo_git", message: "no esta bajo git" }),
      ],
    });
    expect(r.conGit).toBe(2);
    expect(r.sinGit).toBe(1);
    expect(r.filas).toHaveLength(3);
  });

  it("ordena primero los que NO andan: son los accionables", () => {
    const r = resumirEstadoDeRepos({
      ok: true, total: 2, con_git: 1, dev_pr_enabled: true, message: "",
      projects: [fila({ project: "OK" }), fila({ project: "ROTO", ok: false, reason: "x" })],
    });
    expect(r.filas[0].project).toBe("ROTO");
  });

  it("cada fila trae su estado legible y su motivo", () => {
    const r = resumirEstadoDeRepos({
      ok: true, total: 1, con_git: 0, dev_pr_enabled: true, message: "",
      projects: [fila({ project: "X", ok: false, reason: "ruta_inaccesible",
                        message: "no se pudo leer la carpeta" })],
    });
    expect(r.filas[0].estado).toBe("sin-git");
    expect(r.filas[0].detalle).toContain("no se pudo leer");
  });

  it("un proyecto con git pero con aviso NO se marca como roto", () => {
    const r = resumirEstadoDeRepos({
      ok: true, total: 1, con_git: 1, dev_pr_enabled: true, message: "",
      projects: [fila({ project: "S", warning: "workspace_es_subdirectorio",
                        warning_message: "es una SUBCARPETA del repositorio" })],
    });
    expect(r.filas[0].estado).toBe("con-git");
    expect(r.filas[0].detalle).toContain("SUBCARPETA");
  });

  it("sin datos todavía devuelve una vista vacía, no explota", () => {
    const r = resumirEstadoDeRepos(null);
    expect(r.filas).toEqual([]);
    expect(r.conGit).toBe(0);
    expect(r.sinGit).toBe(0);
  });

  it("si el backend falló, el motivo se propaga en vez de mostrar 0 proyectos sin más", () => {
    const r = resumirEstadoDeRepos({
      ok: false, total: 0, con_git: 0, dev_pr_enabled: true,
      message: "No se pudo verificar el estado", projects: [],
    });
    expect(r.error).toContain("No se pudo verificar");
  });
});

describe("etiquetaProveedor", () => {
  it("traduce los nombres crudos del backend", () => {
    expect(etiquetaProveedor("gitlab")).toBe("GitLab");
    expect(etiquetaProveedor("azure_devops")).toBe("Azure DevOps");
  });

  it("un proveedor nuevo del backend se muestra igual, no se traga", () => {
    expect(etiquetaProveedor("bitbucket")).toBe("bitbucket");
  });

  it("sin proveedor devuelve null", () => {
    expect(etiquetaProveedor(null)).toBe(null);
    expect(etiquetaProveedor("")).toBe(null);
  });
});

describe("describeOpenPrControl", () => {
  it("con repo git reconocido, el tilde se puede usar y nombra el proveedor", () => {
    const c = describeOpenPrControl({
      canResolve: true, devPrEnabled: true, preflight: okPreflight, deseado: true,
    });
    expect(c.visible).toBe(true);
    expect(c.disabled).toBe(false);
    expect(c.checked).toBe(true);
    expect(c.etiqueta).toContain("GitLab");
  });

  it("mientras el chequeo no vuelve, el tilde está deshabilitado y lo dice", () => {
    const c = describeOpenPrControl({
      canResolve: true, devPrEnabled: true, preflight: null, deseado: true,
    });
    expect(c.visible).toBe(true);
    expect(c.disabled).toBe(true);
    expect(c.checked).toBe(false);
    expect(c.motivo).not.toBe("");
  });

  it("sin repo git: VISIBLE pero deshabilitado y con el motivo del backend", () => {
    // El defecto reportado era justamente que no se veía nada. Esconder el
    // control es degradación SILENCIOSA: acá se muestra y se explica.
    const c = describeOpenPrControl({
      canResolve: true,
      devPrEnabled: true,
      preflight: preflightRoto("no_es_repo_git", "La carpeta del proyecto no es un repositorio git"),
      deseado: true,
    });
    expect(c.visible).toBe(true);
    expect(c.disabled).toBe(true);
    expect(c.checked).toBe(false); // nunca tildado si el PR no puede salir
    expect(c.motivo).toContain("repositorio git");
  });

  it("con la capacidad apagada sigue VISIBLE, deshabilitada y con motivo", () => {
    const c = describeOpenPrControl({
      canResolve: true, devPrEnabled: false, preflight: null, deseado: true,
    });
    expect(c.visible).toBe(true);
    expect(c.disabled).toBe(true);
    expect(c.motivo).not.toBe("");
  });

  it("si el ticket no admite el resolutor, no hay control", () => {
    const c = describeOpenPrControl({
      canResolve: false, devPrEnabled: true, preflight: okPreflight, deseado: true,
    });
    expect(c.visible).toBe(false);
  });

  it("respeta el destilde del operador (opt-in, nunca forzado)", () => {
    const c = describeOpenPrControl({
      canResolve: true, devPrEnabled: true, preflight: okPreflight, deseado: false,
    });
    expect(c.disabled).toBe(false);
    expect(c.checked).toBe(false);
  });

  it("si el chequeo mismo se cayó, NO se queda en 'verificando' para siempre", () => {
    const c = describeOpenPrControl({
      canResolve: true, devPrEnabled: true, preflight: PREFLIGHT_CAIDO, deseado: true,
    });
    expect(c.visible).toBe(true);
    expect(c.disabled).toBe(true);
    expect(c.checked).toBe(false);
    expect(c.motivo).not.toBe(ESPERANDO_TEXTO);
    expect(c.motivo).toContain("repositorio git");
  });

  it("un repo sin remoto 'origin' habilita igual, pero avisa", () => {
    const c = describeOpenPrControl({
      canResolve: true,
      devPrEnabled: true,
      preflight: { ...okPreflight, warning: "sin_origin", warning_message: "El repo no tiene remoto origin" },
      deseado: true,
    });
    expect(c.disabled).toBe(false);
    expect(c.checked).toBe(true);
    expect(c.motivo).toContain("origin");
  });
});

// ── Resultado del PR ─────────────────────────────────────────────────────────

function res(p: Partial<DevPrResultDTO>): DevPrResultDTO {
  return { ok: true, found: true, status: "pendiente", terminal: false, execution_id: 1, ...p };
}

describe("describePrResult", () => {
  it("sin datos todavía no muestra nada", () => {
    expect(describePrResult(null).visible).toBe(false);
  });

  it("no_solicitado no muestra nada (el operador destildó)", () => {
    const d = describePrResult(res({ found: false, status: "no_solicitado", terminal: true }));
    expect(d.visible).toBe(false);
  });

  it("pendiente avisa que el PR sale al terminar", () => {
    const d = describePrResult(res({ status: "pendiente" }));
    expect(d.visible).toBe(true);
    expect(d.tono).toBe("pendiente");
    expect(d.url).toBe(null);
  });

  it("abierto muestra la URL clicable y el id", () => {
    const d = describePrResult(res({
      status: "opened", terminal: true, pr_id: 9, branch: "stacky/incidencia-1-exec-7",
      pr_url: "https://gitlab.local/g/p/-/merge_requests/9",
    }));
    expect(d.tono).toBe("ok");
    expect(d.url).toBe("https://gitlab.local/g/p/-/merge_requests/9");
    expect(d.texto).toContain("9");
  });

  it("abierto SIN url no inventa un link roto", () => {
    const d = describePrResult(res({ status: "opened", terminal: true, pr_id: 9 }));
    expect(d.tono).toBe("ok");
    expect(d.url).toBe(null);
  });

  it("sin cambios de código explica por qué no hubo PR", () => {
    const d = describePrResult(res({ status: "blocked_empty", terminal: true }));
    expect(d.tono).toBe("info");
    expect(d.texto.toLowerCase()).toContain("cambios");
  });

  it("salteado repite el motivo exacto del backend", () => {
    const d = describePrResult(res({
      status: "skipped", terminal: true, error: "el working tree apunta a otro remoto",
    }));
    expect(d.tono).toBe("info");
    expect(d.texto).toContain("otro remoto");
  });

  it("error muestra el error legible, no un genérico", () => {
    const d = describePrResult(res({
      status: "error", terminal: true, error: "401 Unauthorized del tracker",
    }));
    expect(d.tono).toBe("error");
    expect(d.texto).toContain("401");
  });

  it("un status desconocido del backend no rompe la UI", () => {
    const d = describePrResult(res({ status: "marciano", terminal: false }));
    expect(d.visible).toBe(true);
    expect(d.texto).not.toBe("");
  });
});
