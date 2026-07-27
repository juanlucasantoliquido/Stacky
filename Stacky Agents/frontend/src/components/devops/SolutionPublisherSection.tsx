/**
 * Plan 215 F7 — Publicador de Soluciones.
 *
 * Catálogo de soluciones .NET del proyecto (el MISMO del Taller de Compilación,
 * Plan 201), config de publish por solución, publish 1-click con evidencia del
 * comando previsto, log vivo, descarga del artefacto, historial y puente al
 * agente DevOps cuando algo falla. Todo por clicks; nada se ejecuta sin que el
 * operador confirme.
 *
 * Degradaciones honestas: sin el Plan 201 el backend responde 200 con
 * `build_workshop_unavailable` (panel propio); sin toolchain .NET aparece el
 * doctor; si el backend se reinició, el seguimiento del run responde 404 y acá
 * se CORTA el sondeo en vez de reintentar para siempre.
 */
import React, { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  DevOpsAgentApi,
  DevOpsSolutionPublisher,
  type SolutionPublisherDeepScanResponse,
  type SolutionPublisherRunStatusResponse,
  type SolutionPublisherToolchain,
} from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { copyText } from "../../services/copyService";
import { useWorkbench } from "../../store/workbench";
import {
  Button,
  Checkbox,
  Dialog,
  Field,
  Input,
  SectionHeader,
  Select,
  Skeleton,
  Spinner,
  StatusChip,
  Textarea,
  useConfirm,
} from "../ui";
import LoadErrorState from "../LoadErrorState";
import Toast, { type ToastState } from "../Toast";
import {
  MAX_EXTRA_ARGS,
  PUBLISH_MODES,
  canPublish,
  commandPreview,
  formatBytes,
  isValidExtraArg,
  needsAttention,
  parseSolutionPathsFromText,
  planReasonLabel,
  publishModeLabel,
  publishStatusLabel,
  type PublishConfig,
  type PublisherSolution,
} from "./solutionPublisherModel";
import styles from "./SolutionPublisherSection.module.css";

type CliRuntime = "claude_code_cli" | "codex_cli";

/** Marcador visible del destino real: el artefacto SIEMPRE va al staging propio
 *  de Stacky, jamás al workspace del cliente. */
const STAGING_PLACEHOLDER = "<carpeta de artefactos de Stacky>";

function mensajeDeError(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  const m = /\{[\s\S]*\}$/.exec(err.message);
  if (m) {
    try {
      const parsed = JSON.parse(m[0]) as { error?: string };
      if (parsed?.error) return parsed.error;
    } catch {
      /* el cuerpo no era JSON: se muestra el mensaje crudo */
    }
  }
  return err.message || fallback;
}

/** argv previsto, SOLO como evidencia para el confirm. Espeja `_build_argv` del
 *  runner; el comando real lo arma el backend como lista. */
function argvPrevisto(
  sol: PublisherSolution,
  toolchain: SolutionPublisherToolchain | undefined,
): string[] {
  const cola = sol.plan?.argv_tail ?? [];
  const extra = sol.config?.extra_args ?? [];
  const configuracion = sol.config?.configuration || "Release";
  const dotnet = toolchain?.dotnet_path || "dotnet";
  const msbuild = toolchain?.msbuild_path || "MSBuild.exe";
  if (sol.plan?.mode_effective === "dotnet_publish") {
    return [dotnet, ...cola, "-o", STAGING_PLACEHOLDER, ...extra];
  }
  if (sol.plan?.mode_effective === "msbuild_pubxml") {
    return [msbuild, ...cola, `/p:publishUrl=${STAGING_PLACEHOLDER}`, ...extra];
  }
  if (toolchain?.builder === "dotnet") {
    return [dotnet, "build", sol.plan?.target ?? "", "-c", configuracion,
      "-o", STAGING_PLACEHOLDER, "--nologo", ...extra];
  }
  return [msbuild, sol.plan?.target ?? "", "/t:Build",
    `/p:Configuration=${configuracion}`, `/p:OutDir=${STAGING_PLACEHOLDER}`,
    "/nologo", ...extra];
}

function ToolchainBanner({ toolchain, onCopied }: {
  toolchain: SolutionPublisherToolchain | undefined;
  onCopied: (t: ToastState) => void;
}) {
  if (!toolchain) return null;
  if (toolchain.available) {
    return (
      <StatusChip tone="success">
        {toolchain.builder === "msbuild"
          ? "MSBuild listo para publicar"
          : `.NET ${toolchain.version ?? ""} listo para publicar`}
      </StatusChip>
    );
  }
  const rem = toolchain.remediation;
  return (
    <div className={styles.doctor}>
      <p className={styles.doctorTitle}>No se puede publicar en esta máquina</p>
      <p className={styles.doctorText}>{rem?.message}</p>
      {rem?.command && <code className={styles.code}>{rem.command}</code>}
      <div className={styles.toolbar}>
        {rem?.command && (
          <Button
            variant="secondary"
            onClick={() => {
              void copyText(rem.command).then((res) =>
                onCopied({
                  variant: res.ok ? "success" : "error",
                  body: res.ok ? "Comando copiado" : "No se pudo copiar el comando",
                }),
              );
            }}
          >
            Copiar comando
          </Button>
        )}
        {rem?.url && (
          <a href={rem.url} target="_blank" rel="noreferrer">
            Descargar .NET SDK
          </a>
        )}
      </div>
    </div>
  );
}

export const SolutionPublisherSection: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  const qc = useQueryClient();
  const askConfirm = useConfirm();
  const activeProject = useWorkbench((s) => s.activeProject);

  const [toast, setToast] = useState<ToastState | null>(null);
  const [busy, setBusy] = useState(false);
  const [deepBusy, setDeepBusy] = useState(false);
  const [deepResult, setDeepResult] = useState<SolutionPublisherDeepScanResponse | null>(null);
  const [seleccionadas, setSeleccionadas] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [rechazadas, setRechazadas] = useState<{ path: string; reason: string }[]>([]);
  const [configSlug, setConfigSlug] = useState<string | null>(null);
  const [draft, setDraft] = useState<PublishConfig | null>(null);
  const [nuevoArg, setNuevoArg] = useState("");
  const [configError, setConfigError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runPerdido, setRunPerdido] = useState(false);
  const [noSoportado, setNoSoportado] = useState<{ slug: string; reason: string } | null>(null);
  const [assist, setAssist] = useState<{ project: string; message: string } | null>(null);
  const [runtime, setRuntime] = useState<CliRuntime>("claude_code_cli");
  const [historialSlug, setHistorialSlug] = useState<string | null>(null);
  const primerScanAvisado = useRef(false);

  const visible = ctx.visible ?? true;

  const catalogQ = useQuery({
    queryKey: ["solution-publisher-catalog"],
    queryFn: () => DevOpsSolutionPublisher.catalog(),
  });

  const statusQ = useQuery({
    queryKey: ["solution-publisher-run", runId],
    queryFn: () => DevOpsSolutionPublisher.runStatus(runId as string),
    enabled: Boolean(runId) && visible,
    retry: false,
    // KPI-4 (plan 239 F6): con la sección oculta NO se sondea.
    refetchInterval: (q) =>
      visible &&
      (q.state.data as SolutionPublisherRunStatusResponse | undefined)?.status === "running"
        ? 1500
        : false,
  });

  const runsQ = useQuery({
    queryKey: ["solution-publisher-runs", historialSlug],
    queryFn: () => DevOpsSolutionPublisher.runs(historialSlug as string),
    enabled: Boolean(historialSlug),
    retry: false,
  });

  // C1 — el status de un run desconocido responde 404 (backend reiniciado): se
  // corta el sondeo en el primer error. Jamás un ciclo infinito de 404.
  useEffect(() => {
    if (statusQ.isError && runId) {
      setRunId(null);
      setRunPerdido(true);
    }
  }, [statusQ.isError, runId]);

  useEffect(() => {
    if (catalogQ.data?.first_scan_ran && !primerScanAvisado.current) {
      primerScanAvisado.current = true;
      setToast({
        variant: "success",
        body: "Se escanearon las soluciones del proyecto (una única vez)",
      });
    }
  }, [catalogQ.data?.first_scan_ran]);

  if (catalogQ.isLoading) return <Skeleton lines={3} height={60} />;
  if (catalogQ.isError) {
    return (
      <LoadErrorState
        what="el Publicador de Soluciones"
        error={catalogQ.error}
        onRetry={() => catalogQ.refetch()}
      />
    );
  }

  const data = catalogQ.data;

  if (data?.error === "build_workshop_unavailable") {
    return (
      <section className={styles.section}>
        <SectionHeader
          title="Publicar Soluciones"
          subtitle="Publicá una solución .NET a una carpeta lista para desplegar."
        />
        <div className={styles.unavailable}>
          <p className={styles.unavailableTitle}>Requiere el Taller de Compilación (Plan 201)</p>
          <p className={styles.doctorText}>
            {data.detail ?? "El publicador reusa el catálogo de soluciones del Taller de Compilación."}
          </p>
        </div>
      </section>
    );
  }

  const soluciones: PublisherSolution[] = data?.catalog?.solutions ?? [];
  const toolchain = data?.toolchain;
  const workspace = data?.workspace_root ?? "";
  const estado = statusQ.data;
  const chatDisponible = ctx.health?.agent_enabled === true && Boolean(activeProject?.name);

  const errorToast = (err: unknown, fallback: string) =>
    setToast({ variant: "error", body: mensajeDeError(err, fallback) });

  const copiar = (texto: string, okBody: string) => {
    void copyText(texto).then((res) =>
      setToast({
        variant: res.ok ? "success" : "error",
        body: res.ok ? okBody : "No se pudo copiar",
      }),
    );
  };

  const reescanear = () => {
    setBusy(true);
    void DevOpsSolutionPublisher.rescan()
      .then(() => qc.invalidateQueries({ queryKey: ["solution-publisher-catalog"] }))
      .catch((err: unknown) => errorToast(err, "No se pudo re-escanear"))
      .finally(() => setBusy(false));
  };

  const escaneoProfundo = () => {
    setDeepBusy(true);
    setDeepResult(null);
    setSeleccionadas([]);
    void DevOpsSolutionPublisher.deepScan()
      .then((res) => {
        setDeepResult(res);
        setSeleccionadas(res.new_paths ?? []);
      })
      .catch((err: unknown) => errorToast(err, "No se pudo hacer el escaneo profundo"))
      .finally(() => setDeepBusy(false));
  };

  const importar = async (paths: string[]) => {
    if (paths.length === 0) return;
    const ok = await askConfirm({
      title: "Agregar soluciones al catálogo",
      message: `¿Agregar ${paths.length} archivo(s) .sln al catálogo? El servidor valida cada ruta; no se compila ni se publica nada ahora.`,
      confirmLabel: "Agregar",
    });
    if (!ok) return;
    setBusy(true);
    try {
      const res = await DevOpsSolutionPublisher.importSolutions(paths);
      setRechazadas(res.rejected ?? []);
      const n = (res.added ?? []).length;
      setToast({
        variant: n > 0 ? "success" : "warning",
        body: n > 0 ? `${n} solución(es) agregada(s)` : "No se agregó ninguna ruta",
      });
      await qc.invalidateQueries({ queryKey: ["solution-publisher-catalog"] });
      if (n > 0) {
        setImportOpen(false);
        setImportText("");
        setDeepResult(null);
        setSeleccionadas([]);
      }
    } catch (err) {
      errorToast(err, "No se pudieron agregar las soluciones");
    } finally {
      setBusy(false);
    }
  };

  const abrirConfig = (sol: PublisherSolution) => {
    setConfigSlug(sol.slug);
    setDraft({ ...sol.config, extra_args: [...(sol.config?.extra_args ?? [])] });
    setNuevoArg("");
    setConfigError(null);
  };

  const guardarConfig = async () => {
    if (!draft || !configSlug) return;
    const invalidos = draft.extra_args.filter((a) => !isValidExtraArg(a));
    if (invalidos.length > 0) {
      setConfigError(`Argumentos inválidos (sin espacios ni metacaracteres): ${invalidos.join(", ")}`);
      return;
    }
    setBusy(true);
    try {
      await DevOpsSolutionPublisher.saveConfig(configSlug, {
        mode: draft.mode,
        configuration: draft.configuration,
        project_csproj: draft.project_csproj,
        publish_profile: draft.publish_profile,
        extra_args: draft.extra_args,
        register_as_deploy_app: draft.register_as_deploy_app,
      });
      setConfigSlug(null);
      setDraft(null);
      setConfigError(null);
      await qc.invalidateQueries({ queryKey: ["solution-publisher-catalog"] });
      setToast({ variant: "success", body: "Configuración guardada" });
    } catch (err) {
      setConfigError(mensajeDeError(err, "No se pudo guardar la configuración"));
    } finally {
      setBusy(false);
    }
  };

  const publicar = async (sol: PublisherSolution) => {
    const preview = commandPreview(argvPrevisto(sol, toolchain));
    const ok = await askConfirm({
      title: `Publicar ${sol.friendly_name}`,
      message: `Se va a ejecutar exactamente esto:\n\n${preview}\n\nLa salida va a una carpeta propia de Stacky; tu workspace no se toca.`,
      confirmLabel: "Publicar",
    });
    if (!ok) return;
    setBusy(true);
    setNoSoportado(null);
    setRunPerdido(false);
    try {
      const res = await DevOpsSolutionPublisher.run(sol.slug);
      if (res.status === "toolchain_missing") {
        await qc.invalidateQueries({ queryKey: ["solution-publisher-catalog"] });
        setToast({ variant: "warning", body: "Falta el toolchain .NET en esta máquina" });
        return;
      }
      if (res.status === "unsupported") {
        setNoSoportado({ slug: sol.slug, reason: res.reason ?? "" });
        return;
      }
      if (res.run_id) setRunId(res.run_id);
    } catch (err) {
      errorToast(err, "No se pudo iniciar la publicación");
    } finally {
      setBusy(false);
    }
  };

  const cancelar = async () => {
    if (!runId) return;
    const ok = await askConfirm({
      title: "Cancelar publicación",
      message: "¿Cancelar la publicación en curso? Lo que ya se generó queda donde está.",
      tone: "danger",
      confirmLabel: "Cancelar publicación",
      cancelLabel: "Seguir publicando",
    });
    if (!ok) return;
    void DevOpsSolutionPublisher.cancelRun(runId).catch((err: unknown) =>
      errorToast(err, "No se pudo cancelar"),
    );
  };

  const registrarApp = async (rid: string) => {
    const ok = await askConfirm({
      title: "Registrar como app de despliegue",
      message: "Se va a registrar el artefacto publicado en el Centro de Despliegues. Si la app todavía no tiene destino, vas a tener que configurarlo ahí.",
      confirmLabel: "Registrar",
    });
    if (!ok) return;
    try {
      await DevOpsSolutionPublisher.registerDeployApp(rid);
      setToast({ variant: "success", body: "Registrado en Despliegues" });
      await qc.invalidateQueries({ queryKey: ["devops-deployments-overview"] });
    } catch (err) {
      setToast({
        variant: "warning",
        body: mensajeDeError(err, "Configurá el destino en Despliegues y volvé a registrar"),
      });
    }
  };

  const abrirAsistente = async (rid: string) => {
    try {
      const res = await DevOpsSolutionPublisher.assistContext(rid);
      setAssist({ project: res.project, message: res.message });
    } catch (err) {
      errorToast(err, "No se pudo armar el contexto para el agente");
    }
  };

  const iniciarConversacion = async (project: string, message: string) => {
    const ok = await askConfirm({
      title: "Abrir conversación con el agente DevOps",
      message: "Se crea una conversación nueva con este contexto. El agente propone; no ejecuta nada sin que vos confirmes.",
      confirmLabel: "Iniciar conversación",
    });
    if (!ok) return;
    try {
      await DevOpsAgentApi.start({ project, message, runtime });
      setAssist(null);
      setToast({ variant: "success", body: "Conversación creada — abrila en «Agente DevOps»" });
      ctx.setActiveSection?.("agente");
    } catch (err) {
      errorToast(err, "No se pudo crear la conversación");
    }
  };

  const mensajeBusquedaAgente =
    `Buscá todos los archivos .sln del workspace ${workspace} y respondé SOLO la ` +
    `lista de rutas absolutas, una por línea.`;

  const rutasPegadas = parseSolutionPathsFromText(importText);
  const solConfig = soluciones.find((s) => s.slug === configSlug) ?? null;

  return (
    <section className={styles.section}>
      <SectionHeader
        title="Publicar Soluciones"
        subtitle="Elegí una solución del proyecto y publicala a una carpeta lista para desplegar. Un click, sin tocar tu workspace."
      />

      <ToolchainBanner toolchain={toolchain} onCopied={setToast} />

      {data?.warning && <div className={styles.banner}>{data.warning}</div>}
      {data?.catalog?.truncated && (
        <div className={styles.banner}>
          Se alcanzó el tope de escaneo; puede faltar alguna solución — probá el escaneo
          profundo o agregá el .sln a mano.
        </div>
      )}

      <div className={styles.toolbar}>
        <Button variant="secondary" onClick={reescanear} disabled={busy || deepBusy}>
          Re-escanear
        </Button>
        <Button variant="secondary" onClick={escaneoProfundo} disabled={busy || deepBusy}>
          Escaneo profundo
        </Button>
        <Button variant="secondary" onClick={() => setImportOpen(true)} disabled={busy}>
          Agregar .sln…
        </Button>
        {deepBusy && (
          <span className={styles.summary}>
            <Spinner /> Escaneo profundo en curso (hasta 45s)…
          </span>
        )}
        <span className={styles.spacer} />
        <span className={styles.summary}>
          {soluciones.length} solución(es) · {soluciones.filter(needsAttention).length} con
          atención
        </span>
      </div>

      {deepResult && !deepBusy && (
        <div className={styles.runBox}>
          <div className={styles.runHead}>
            <strong className={styles.itemName}>
              Escaneo profundo: {(deepResult.paths ?? []).length} .sln encontrados ·{" "}
              {(deepResult.new_paths ?? []).length} nuevos
            </strong>
            {deepResult.timed_out && (
              <StatusChip tone="warning">Se agotó el tiempo: puede faltar alguno</StatusChip>
            )}
          </div>
          {(deepResult.new_paths ?? []).length === 0 ? (
            <p className={styles.empty}>No apareció ninguna solución nueva.</p>
          ) : (
            <>
              <ul className={styles.pathList}>
                {(deepResult.new_paths ?? []).map((p) => (
                  <li key={p} className={styles.pathItem}>
                    <Checkbox
                      label={p}
                      checked={seleccionadas.includes(p)}
                      onChange={(e) =>
                        setSeleccionadas((prev) =>
                          e.target.checked ? [...prev, p] : prev.filter((x) => x !== p),
                        )
                      }
                    />
                  </li>
                ))}
              </ul>
              <div className={styles.toolbar}>
                <Button
                  onClick={() => void importar(seleccionadas)}
                  disabled={busy || seleccionadas.length === 0}
                >
                  Importar seleccionadas
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      {rechazadas.length > 0 && (
        <div className={styles.banner}>
          Rutas rechazadas por el servidor:
          <ul className={styles.pathList}>
            {rechazadas.map((r) => (
              <li key={r.path} className={styles.pathItem}>
                {r.path} — {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {soluciones.length === 0 ? (
        <div className={styles.agentBox}>
          <p className={styles.doctorText}>
            No hay soluciones en el catálogo. Probá «Escaneo profundo», agregá el .sln a mano,
            o pedile al agente DevOps que las busque por vos.
          </p>
          <div className={styles.formRow}>
            <Select
              value={runtime}
              onChange={(e) => setRuntime(e.target.value as CliRuntime)}
              aria-label="Runtime del agente"
            >
              <option value="claude_code_cli">Claude Code CLI</option>
              <option value="codex_cli">Codex CLI</option>
            </Select>
            {chatDisponible ? (
              <Button
                onClick={() =>
                  void iniciarConversacion(activeProject?.name ?? "", mensajeBusquedaAgente)
                }
              >
                Buscar con agente DevOps
              </Button>
            ) : (
              <Button
                variant="secondary"
                onClick={() => copiar(mensajeBusquedaAgente, "Pedido copiado")}
              >
                Copiar pedido
              </Button>
            )}
          </div>
          <p className={styles.hint}>
            El agente solo propone: las rutas que devuelva las pegás en «Agregar .sln…» y el
            servidor las valida.
          </p>
        </div>
      ) : (
        <ul className={styles.list}>
          {soluciones.map((sol) => (
            <li
              key={sol.slug}
              className={
                needsAttention(sol) ? `${styles.item} ${styles.itemAttention}` : styles.item
              }
            >
              <div className={styles.itemBody}>
                <div className={styles.itemHead}>
                  <span className={styles.itemName}>{sol.friendly_name}</span>
                  {sol.origin === "manual" && (
                    <span className={`${styles.chip} ${styles.chipManual}`}>manual</span>
                  )}
                  {sol.missing && (
                    <span className={`${styles.chip} ${styles.chipMissing}`}>no encontrado</span>
                  )}
                </div>
                <span className={styles.itemPath}>{sol.sln_path}</span>
                <div className={styles.chips}>
                  {(sol.projects ?? []).map((p) => (
                    <span key={p.csproj_path} className={styles.chip}>
                      {p.name} · {p.type}
                    </span>
                  ))}
                </div>
                <span className={styles.mode}>
                  Modo efectivo: {publishModeLabel(sol.plan?.mode_effective ?? "")}
                </span>
                {!sol.plan?.supported && sol.plan?.reason && (
                  <span className={styles.reason}>{planReasonLabel(sol.plan.reason)}</span>
                )}
                <div className={styles.itemActions}>
                  <Button variant="secondary" onClick={() => abrirConfig(sol)}>
                    Configurar
                  </Button>
                  <Button
                    onClick={() => void publicar(sol)}
                    disabled={busy || !canPublish(sol, Boolean(toolchain?.available))}
                  >
                    Publicar
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setHistorialSlug((prev) => (prev === sol.slug ? null : sol.slug))
                    }
                  >
                    {historialSlug === sol.slug ? "Ocultar historial" : "Historial"}
                  </Button>
                </div>
                {historialSlug === sol.slug && (
                  <div className={styles.runBox}>
                    {runsQ.isLoading && <p className={styles.empty}>Cargando historial…</p>}
                    {(runsQ.data?.runs ?? []).length === 0 && !runsQ.isLoading && (
                      <p className={styles.empty}>Todavía no hay publicaciones de esta solución.</p>
                    )}
                    {(runsQ.data?.runs ?? []).length > 0 && (
                      <table className={styles.historyTable}>
                        <thead>
                          <tr>
                            <th>Inicio</th>
                            <th>Estado</th>
                            <th>Causa probable</th>
                            <th>Duración</th>
                            <th>Artefacto</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(runsQ.data?.runs ?? []).map((r) => (
                            <tr key={r.run_id}>
                              <td>{r.started_at ?? "—"}</td>
                              <td>{publishStatusLabel(r.status)}</td>
                              <td>{r.failure_class?.hint ?? "—"}</td>
                              <td>{r.duration_sec != null ? `${r.duration_sec} s` : "—"}</td>
                              <td>
                                {r.artifact_ready ? (
                                  <a
                                    href={DevOpsSolutionPublisher.artifactDownloadUrl(r.run_id)}
                                    download
                                  >
                                    Descargar .zip
                                  </a>
                                ) : (
                                  "—"
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {noSoportado && (
        <div className={styles.banner}>
          No se puede publicar esta solución: {planReasonLabel(noSoportado.reason)}
        </div>
      )}

      {runPerdido && (
        <div className={styles.banner}>
          Run desconocido (backend reiniciado). Volvé a publicar o mirá el historial de la
          solución.
        </div>
      )}

      {runId && estado && (
        <div className={styles.runBox}>
          <div className={styles.runHead}>
            <StatusChip
              tone={
                estado.status === "success"
                  ? "success"
                  : estado.status === "running"
                    ? "info"
                    : "danger"
              }
            >
              {publishStatusLabel(estado.status)}
            </StatusChip>
            {estado.failure_class && (
              <StatusChip tone="warning">Causa probable: {estado.failure_class.hint}</StatusChip>
            )}
            <span className={styles.spacer} />
            {estado.status === "running" && (
              <Button variant="secondary" onClick={() => void cancelar()}>
                Cancelar
              </Button>
            )}
            {estado.artifact_ready && (
              <a href={DevOpsSolutionPublisher.artifactDownloadUrl(runId)} download>
                Descargar .zip
              </a>
            )}
            {estado.status === "success" &&
              soluciones.find((s) => s.slug === estado.slug)?.config?.register_as_deploy_app && (
                <Button variant="secondary" onClick={() => void registrarApp(runId)}>
                  Registrar como app de despliegue
                </Button>
              )}
            {(estado.status === "failed" ||
              estado.status === "unsupported" ||
              estado.status === "toolchain_missing") && (
              <Button variant="secondary" onClick={() => void abrirAsistente(runId)}>
                Asistir con agente DevOps
              </Button>
            )}
          </div>

          {estado.summary && (
            <div className={styles.evidence}>
              Duración: {estado.summary.duration_sec ?? "—"} s · {estado.summary.files} archivo(s)
              · {formatBytes(estado.summary.bytes)}
            </div>
          )}

          {estado.error && <p className={styles.error}>{estado.error}</p>}

          {estado.log.length > 0 && (
            <pre className={styles.log}>
              {estado.log.map((l) => `${l.level}: ${l.message}`).join("\n")}
            </pre>
          )}
        </div>
      )}

      <Dialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Agregar soluciones a mano"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(false)}>
              Cerrar
            </Button>
            <Button
              onClick={() => void importar(rutasPegadas)}
              disabled={busy || rutasPegadas.length === 0}
            >
              Agregar {rutasPegadas.length > 0 ? `(${rutasPegadas.length})` : ""}
            </Button>
          </>
        }
      >
        <div className={styles.form}>
          <Field label="Pegá una ruta .sln por línea" help="Se ignoran viñetas, comillas y la prosa que venga alrededor.">
            {(ctl) => (
              <Textarea
                {...ctl}
                rows={8}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
            )}
          </Field>
          {rutasPegadas.length > 0 && (
            <pre className={styles.preview}>{rutasPegadas.join("\n")}</pre>
          )}
          <p className={styles.hint}>
            El servidor valida cada ruta: las que no existan o no sean .sln se rechazan con su
            motivo.
          </p>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(configSlug && draft)}
        onClose={() => {
          setConfigSlug(null);
          setDraft(null);
        }}
        title={`Configurar ${solConfig?.friendly_name ?? ""}`}
        size="md"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfigSlug(null);
                setDraft(null);
              }}
            >
              Cancelar
            </Button>
            <Button onClick={() => void guardarConfig()} disabled={busy}>
              Guardar
            </Button>
          </>
        }
      >
        {draft && (
          <div className={styles.form}>
            <Field label="Modo de publicación">
              {(ctl) => (
                <Select
                  {...ctl}
                  value={draft.mode}
                  onChange={(e) =>
                    setDraft({ ...draft, mode: e.target.value as PublishConfig["mode"] })
                  }
                >
                  {PUBLISH_MODES.map((m) => (
                    <option key={m} value={m}>
                      {publishModeLabel(m)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <Field label="Proyecto a publicar">
              {(ctl) => (
                <Select
                  {...ctl}
                  value={draft.project_csproj ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, project_csproj: e.target.value || null })
                  }
                >
                  <option value="">Automático (el proyecto web, si hay)</option>
                  {(solConfig?.projects ?? []).map((p) => (
                    <option key={p.csproj_path} value={p.csproj_path}>
                      {p.name} · {p.type}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <Field
              label="Perfil de publicación (.pubxml)"
              help="Solo los perfiles a carpeta local (FileSystem) se pueden ejecutar."
            >
              {(ctl) => (
                <Select
                  {...ctl}
                  value={draft.publish_profile ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, publish_profile: e.target.value || null })
                  }
                >
                  <option value="">Automático (el primero a carpeta local)</option>
                  {(solConfig?.publish_profiles ?? []).map((p) => (
                    <option
                      key={`${p.csproj_path}::${p.name}`}
                      value={p.name}
                      disabled={p.method !== "FileSystem"}
                    >
                      {p.name} · {p.method}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <Field label="Configuración">
              {(ctl) => (
                <Input
                  {...ctl}
                  value={draft.configuration}
                  onChange={(e) => setDraft({ ...draft, configuration: e.target.value })}
                />
              )}
            </Field>

            <Field
              label={`Argumentos extra (máx ${MAX_EXTRA_ARGS})`}
              help="Sin espacios ni metacaracteres: el comando se arma como lista, nunca como línea de shell."
            >
              {(ctl) => (
                <div className={styles.formRow}>
                  <Input
                    {...ctl}
                    value={nuevoArg}
                    placeholder="/p:Foo=Bar"
                    onChange={(e) => setNuevoArg(e.target.value)}
                  />
                  <Button
                    variant="secondary"
                    disabled={
                      !isValidExtraArg(nuevoArg) || draft.extra_args.length >= MAX_EXTRA_ARGS
                    }
                    onClick={() => {
                      setDraft({ ...draft, extra_args: [...draft.extra_args, nuevoArg] });
                      setNuevoArg("");
                    }}
                  >
                    Agregar
                  </Button>
                </div>
              )}
            </Field>

            {draft.extra_args.length > 0 && (
              <div className={styles.chips}>
                {draft.extra_args.map((a, i) => (
                  <span key={`${a}-${i}`} className={styles.chip}>
                    {a}{" "}
                    <button
                      type="button"
                      aria-label={`Quitar ${a}`}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          extra_args: draft.extra_args.filter((_, j) => j !== i),
                        })
                      }
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* El backend guarda esta preferencia pero NO registra solo (sería
                autonomía sin click): lo que hace es OFRECER el botón al terminar. */}
            <Checkbox
              label="Al terminar, ofrecer «Registrar como app de despliegue»"
              checked={draft.register_as_deploy_app}
              onChange={(e) => setDraft({ ...draft, register_as_deploy_app: e.target.checked })}
            />

            {configError && <p className={styles.error}>{configError}</p>}
          </div>
        )}
      </Dialog>

      <Dialog
        open={Boolean(assist)}
        onClose={() => setAssist(null)}
        title="Asistir con el agente DevOps"
        size="lg"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => copiar(assist?.message ?? "", "Contexto copiado")}
            >
              Copiar contexto
            </Button>
            <Button
              disabled={ctx.health?.agent_enabled !== true}
              onClick={() =>
                void iniciarConversacion(assist?.project ?? "", assist?.message ?? "")
              }
            >
              Iniciar conversación
            </Button>
          </>
        }
      >
        <div className={styles.form}>
          <div className={styles.formRow}>
            <Select
              value={runtime}
              onChange={(e) => setRuntime(e.target.value as CliRuntime)}
              aria-label="Runtime del agente"
            >
              <option value="claude_code_cli">Claude Code CLI</option>
              <option value="codex_cli">Codex CLI</option>
            </Select>
            {ctx.health?.agent_enabled !== true && (
              <span className={styles.summary}>
                El chat DevOps está apagado: copiá el contexto y pegalo donde quieras.
              </span>
            )}
          </div>
          <pre className={styles.preview}>{assist?.message ?? ""}</pre>
          <p className={styles.hint}>
            El contexto ya viene enmascarado por el servidor. El agente propone; aplicar
            cualquier cambio sigue siendo decisión tuya.
          </p>
        </div>
      </Dialog>

      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </section>
  );
};
