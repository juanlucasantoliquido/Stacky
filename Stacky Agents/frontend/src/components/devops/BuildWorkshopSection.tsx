import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { DevOpsBuildWorkshop } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { copyText } from "../../services/copyService";
import { Button, Checkbox, SectionHeader, Skeleton, StatusChip, useConfirm } from "../ui";
import LoadErrorState from "../LoadErrorState";
import Toast, { type ToastState } from "../Toast";
import {
  buildStatusLabel,
  canCompile,
  compileMode,
  formatBytes,
  projectTypeLabel,
  summarizeCatalog,
  trackedSlugs,
  type BuildStatus,
  type SolutionEntry,
  type Toolchain,
} from "./buildWorkshopModel";
import styles from "./BuildWorkshopSection.module.css";

/**
 * Plan 201 F10 — Taller de Compilación: detectar soluciones, tildar cuáles
 * importan, compilar en Release y descargar el artefacto. Todo por clicks.
 *
 * Sin toolchain .NET la sección NO se rompe: muestra el doctor con el comando
 * exacto para instalarlo. Stacky nunca instala nada por su cuenta.
 */

function ToolchainBanner({ toolchain, onCopied }: {
  toolchain: Toolchain | undefined;
  onCopied: (t: ToastState) => void;
}) {
  if (!toolchain) return null;
  if (toolchain.available) {
    return (
      <StatusChip tone="success">
        {toolchain.builder === "msbuild" ? "MSBuild listo" : `.NET ${toolchain.version ?? ""} listo`}
      </StatusChip>
    );
  }
  const rem = toolchain.remediation;
  return (
    <div className={styles.doctor}>
      <p className={styles.doctorTitle}>No se puede compilar en esta máquina</p>
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

export const BuildWorkshopSection: React.FC<{ ctx: DevOpsSectionContext }> = () => {
  const qc = useQueryClient();
  const askConfirm = useConfirm();
  const [unified, setUnified] = useState(false);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [busy, setBusy] = useState(false);

  const catalogQ = useQuery({
    queryKey: ["build-catalog"],
    queryFn: () => DevOpsBuildWorkshop.catalog(),
  });

  const statusQ = useQuery({
    queryKey: ["build-status", buildId],
    queryFn: () => DevOpsBuildWorkshop.status(buildId as string),
    enabled: Boolean(buildId),
    refetchInterval: (q) =>
      (q.state.data as BuildStatus | undefined)?.status === "running" ? 1500 : false,
  });

  if (catalogQ.isLoading) return <Skeleton lines={3} height={60} />;
  if (catalogQ.isError) {
    return (
      <LoadErrorState
        what="el Taller de Compilación"
        error={catalogQ.error}
        onRetry={() => catalogQ.refetch()}
      />
    );
  }

  const data = catalogQ.data;
  const solutions: SolutionEntry[] = data?.catalog?.solutions ?? [];
  const toolchain = data?.toolchain;
  const resumen = summarizeCatalog(solutions);
  const seleccionados = trackedSlugs(solutions);
  const modo = compileMode(unified, seleccionados.length);
  const puedeCompilar =
    canCompile(toolchain as Toolchain, seleccionados.length) && modo !== "invalid" && !busy;

  const escanear = () => {
    setBusy(true);
    void DevOpsBuildWorkshop.scan()
      .then(() => qc.invalidateQueries({ queryKey: ["build-catalog"] }))
      .catch((err: unknown) =>
        setToast({
          variant: "error",
          body: err instanceof Error ? err.message : "No se pudo escanear",
        }),
      )
      .finally(() => setBusy(false));
  };

  const tildar = (slug: string, next: boolean) => {
    void DevOpsBuildWorkshop.track(slug, next)
      .then(() => qc.invalidateQueries({ queryKey: ["build-catalog"] }))
      .catch(() => setToast({ variant: "error", body: "No se pudo guardar la selección" }));
  };

  const compilar = async () => {
    const ok = await askConfirm({
      title: "Compilar en Release",
      message: `¿Compilar ${seleccionados.length} solución(es) en Release? Se creará una carpeta nueva de artefactos; nada existente se sobrescribe.`,
      confirmLabel: "Compilar",
    });
    if (!ok) return;
    setBusy(true);
    void DevOpsBuildWorkshop.compile(seleccionados, unified)
      .then((res) => {
        if (res.status === "toolchain_missing") {
          void qc.invalidateQueries({ queryKey: ["build-catalog"] });
          setToast({ variant: "warning", body: "Falta el toolchain de compilación" });
          return;
        }
        setBuildId(res.build_id);
      })
      .catch((err: unknown) =>
        setToast({
          variant: "error",
          body: err instanceof Error ? err.message : "No se pudo iniciar el build",
        }),
      )
      .finally(() => setBusy(false));
  };

  const cancelar = async () => {
    if (!buildId) return;
    const ok = await askConfirm({
      title: "Cancelar build",
      message: "¿Cancelar el build en curso? Los archivos ya compilados quedan donde están.",
      tone: "danger",
      confirmLabel: "Cancelar build",
      cancelLabel: "Seguir compilando",
    });
    if (!ok) return;
    void DevOpsBuildWorkshop.cancel(buildId).catch(() =>
      setToast({ variant: "error", body: "No se pudo cancelar" }),
    );
  };

  const registrarApp = (slug: string) => {
    if (!buildId) return;
    void DevOpsBuildWorkshop.registerDeployApp(buildId, slug)
      .then(() => {
        setToast({ variant: "success", body: "Registrado en Despliegues" });
        void qc.invalidateQueries({ queryKey: ["devops-deployments-overview"] });
      })
      .catch((err: unknown) =>
        setToast({
          variant: "warning",
          body:
            err instanceof Error
              ? err.message
              : "Configurá el destino en Despliegues y volvé a registrar",
        }),
      );
  };

  const estado = statusQ.data;

  return (
    <section className={styles.section}>
      <SectionHeader
        title="Taller de Compilación"
        subtitle="Detectá las soluciones del proyecto, compilalas en Release y descargá el artefacto."
      />

      <ToolchainBanner toolchain={toolchain} onCopied={setToast} />

      {data?.warning && <div className={styles.banner}>{data.warning}</div>}
      {data?.catalog?.truncated && (
        <div className={styles.banner}>
          Se alcanzó el tope de escaneo; puede faltar alguna solución — escaneá una
          subcarpeta más específica.
        </div>
      )}

      <div className={styles.toolbar}>
        <Button onClick={escanear} disabled={busy}>
          Escanear
        </Button>
        <span className={styles.summary}>
          {resumen.total} solución(es) · {resumen.tracked} tildada(s)
        </span>
        <span className={styles.spacer} />
        <Checkbox
          label="Unificado"
          checked={unified}
          onChange={(e) => setUnified(e.target.checked)}
        />
        <Button onClick={() => void compilar()} disabled={!puedeCompilar}>
          Compilar
        </Button>
      </div>

      {modo === "invalid" && (
        <p className={styles.error}>
          Para varias soluciones activá «Unificado» o dejá tildada una sola.
        </p>
      )}

      {solutions.length === 0 ? (
        <p className={styles.empty}>
          Todavía no hay soluciones detectadas. Apretá «Escanear».
        </p>
      ) : (
        <ul className={styles.list}>
          {solutions.map((sol) => (
            <li key={sol.slug} className={styles.item}>
              <Checkbox
                label=""
                checked={sol.tracked}
                onChange={(e) => tildar(sol.slug, e.target.checked)}
                aria-label={`Tildar ${sol.friendly_name}`}
              />
              <div className={styles.itemBody}>
                <span className={styles.itemName}>{sol.friendly_name}</span>
                <span className={styles.itemPath}>{sol.sln_path}</span>
                <div className={styles.chips}>
                  {sol.projects.map((p) => (
                    <span key={p.csproj_path} className={styles.chip}>
                      {p.name} · {projectTypeLabel(p.type)}
                    </span>
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {buildId && estado && (
        <div className={styles.buildBox}>
          <div className={styles.buildHead}>
            <StatusChip
              tone={
                estado.status === "success"
                  ? "success"
                  : estado.status === "running"
                    ? "info"
                    : "danger"
              }
            >
              {buildStatusLabel(estado.status)}
            </StatusChip>
            <span className={styles.spacer} />
            {estado.status === "running" && (
              <Button variant="secondary" onClick={() => void cancelar()}>
                Cancelar
              </Button>
            )}
            {estado.artifact_ready && (
              <a href={DevOpsBuildWorkshop.artifactDownloadUrl(buildId)} download>
                Descargar .zip
              </a>
            )}
          </div>

          {estado.summary && (
            <div className={styles.evidence}>
              Duración: {estado.summary.duration_sec ?? "—"} s · Toolchain:{" "}
              {estado.summary.toolchain?.builder ?? "—"}
              {estado.summary.artifacts?.map((a) => (
                <div key={a.slug}>
                  {a.slug}: {a.files} archivo(s) · {formatBytes(a.bytes)}{" "}
                  {estado.status === "success" && (
                    <Button variant="secondary" onClick={() => registrarApp(a.slug)}>
                      Usar como app de despliegue
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}

          {estado.log.length > 0 && (
            <pre className={styles.log}>
              {estado.log.map((l) => `${l.level}: ${l.message}`).join("\n")}
            </pre>
          )}
        </div>
      )}

      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </section>
  );
};
