/**
 * DocsPage.tsx - Página principal de documentación (Feature #3)
 *
 * Layout dos paneles:
 *   - Panel izquierdo: selector de fuente/carpeta, búsqueda y DocTree
 *   - Panel derecho: DocViewer con el markdown seleccionado
 */
import { useState, useCallback, useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import DocTree from "../components/DocTree";
import DocViewer from "../components/DocViewer";
import DocCoveragePanel from "../components/docs/DocCoveragePanel";
import DocGraphView from "../components/docs/DocGraphView";
import DocBacklinksPanel from "../components/docs/DocBacklinksPanel";
import DocumenterButton from "../components/docs/DocumenterButton";
import { Docs } from "../api/endpoints";
import type { DocNode, DocRoot, DocHeading } from "../api/endpoints";
import { buildNameIndex, type DocGraphResponse } from "../docs/docGraphModel";
import { useWorkbench } from "../store/workbench";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import { formatRelativeTime } from "../utils/formatRelativeTime";
import { readQueryParam } from "../utils/queryParams";
import styles from "./DocsPage.module.css";

function countDocFiles(nodes: DocNode[] = []): number {
  return nodes.reduce((acc, node) => {
    if (node.kind === "folder") return acc + countDocFiles(node.children ?? []);
    return acc + 1;
  }, 0);
}

/** DFS que devuelve el DocNode (no carpeta) cuyo path coincide, o null. */
function searchDocNodes(nodes: DocNode[] = [], path: string): DocNode | null {
  for (const node of nodes) {
    if (node.kind !== "folder" && node.path === path) return node;
    if (node.children && node.children.length) {
      const hit = searchDocNodes(node.children, path);
      if (hit) return hit;
    }
  }
  return null;
}

/** Busca un DocNode por path recorriendo los children de cada DocRoot. */
function findDocNodeByPath(roots: DocRoot[] = [], path: string): DocNode | null {
  for (const root of roots) {
    const hit = searchDocNodes(root.children ?? [], path);
    if (hit) return hit;
  }
  return null;
}

/** Resuelve el nodeId del grafo para el DocNode abierto (best-effort; null si no mapea). */
function noteIdFor(
  node: DocNode | null,
  sourceId: string,
  graph: DocGraphResponse | undefined
): string | null {
  if (!node || !graph) return null;
  const match = graph.nodes.find(
    (n) =>
      n.kind === "note" &&
      n.path === node.path &&
      (n.source_id === (node.source_id ?? sourceId))
  );
  return match ? match.id : null;
}

export default function DocsPage() {
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name;
  const [selectedNode, setSelectedNode] = useState<DocNode | null>(null);
  const [filterText, setFilterText] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [docsView, setDocsView] = useState<"reader" | "coverage" | "graph">("reader");
  const [pendingOpenPath, setPendingOpenPath] = useState<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    setSelectedNode(null);
    setFilterText("");
    setSelectedSourceId("");
    setDocsView("reader");
    setPendingOpenPath(null);
  }, [projectName]);

  // Plan 129 — deep-link receptor: ?path=<doc path> abre ese documento al
  // montar. Reusa el mecanismo pendingOpenPath ya existente (Plan 111 C2):
  // si el path no existe en el índice, el efecto de arriba ya lo ignora en
  // silencio (línea 231-241 más abajo).
  useEffect(() => {
    const raw = readQueryParam("path");
    if (raw) setPendingOpenPath(raw);
  }, []);

  // -- Fuentes/carpeta docs del proyecto activo -------------------------------
  const {
    data: sourcesData,
    isLoading: sourcesLoading,
    error: sourcesError,
  } = useQuery({
    queryKey: ["docs-sources", projectName ?? "active"],
    queryFn: () => Docs.getSources(projectName),
    staleTime: 60 * 1000,
    retry: 1,
  });

  const sources = sourcesData?.sources ?? [];
  const selectedSource = sources.find((source) => source.id === selectedSourceId) ?? null;

  useEffect(() => {
    if (!sourcesData) return;
    const nextSourceId =
      sourcesData.default_source_id || sourcesData.sources[0]?.id || "stacky";
    const currentStillExists = sourcesData.sources.some((source) => source.id === selectedSourceId);
    if (!selectedSourceId || !currentStillExists) {
      setSelectedSourceId(nextSourceId);
    }
  }, [sourcesData, selectedSourceId]);

  useEffect(() => {
    setSelectedNode(null);
  }, [selectedSourceId]);

  // -- Cargar índice ----------------------------------------------------------
  const {
    data: indexData,
    isLoading: indexLoading,
    error: indexError,
  } = useQuery({
    queryKey: ["docs-index", projectName ?? "active", selectedSourceId],
    queryFn: () => Docs.getIndex({ project: projectName, sourceId: selectedSourceId }),
    enabled: selectedSourceId.length > 0,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });

  // -- Cargar contenido del nodo seleccionado ---------------------------------
  const selectedContentSourceId = selectedNode?.source_id ?? selectedSourceId;
  const {
    data: contentData,
    isLoading: contentLoading,
    error: contentError,
  } = useQuery({
    queryKey: ["docs-content", projectName ?? "active", selectedContentSourceId, selectedNode?.path],
    queryFn: () =>
      Docs.getContent(selectedNode!.path, {
        project: projectName,
        sourceId: selectedContentSourceId,
      }),
    enabled: selectedNode !== null && selectedNode.kind !== "folder",
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  // -- Grafo documental (Plan 109, gateado por flag) --------------------------
  const graphEnabled = sourcesData?.graph_enabled === true;
  const documenterEnabled = sourcesData?.documenter_enabled === true;
  const stalenessEnabled = sourcesData?.staleness_enabled === true;  // Plan 114
  const {
    data: graphData,
    isLoading: graphLoading,
    error: graphError,
  } = useQuery({
    queryKey: ["docs-graph", projectName ?? "active"],
    queryFn: () => Docs.getGraph(projectName),
    // (C1) enabled con la flag (todas las vistas): los wikilinks y backlinks del
    // Lector también necesitan el grafo, no solo Cobertura/Grafo.
    enabled: graphEnabled,
    staleTime: 60 * 1000,
    retry: 1,
  });

  // Índice nombre→nodeId para resolver wikilinks (Plan 111).
  const nameIndex = useMemo(
    () => (graphData ? buildNameIndex(graphData) : undefined),
    [graphData]
  );

  const handleRefreshGraph = useCallback(() => {
    Docs.getGraph(projectName, { refresh: true })
      .catch(() => undefined)
      .finally(() => {
        queryClient.invalidateQueries({ queryKey: ["docs-graph", projectName ?? "active"] });
      });
  }, [projectName, queryClient]);

  // -- Selección de nodo ------------------------------------------------------
  const handleSelect = useCallback((node: DocNode, heading?: DocHeading) => {
    setSelectedNode(node);
    if (heading) {
      setTimeout(() => {
        const el = document.getElementById(heading.anchor);
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 300);
    }
  }, []);

  // -- nodeId del grafo para la nota abierta (backlinks + halo del grafo) ------
  const currentNodeId = useMemo(
    () => noteIdFor(selectedNode, selectedContentSourceId, graphData),
    [selectedNode, selectedContentSourceId, graphData]
  );

  // -- Plan 114: staleness de la nota abierta + acción "Proponer actualización" --
  const currentGraphNode = useMemo(
    () => (graphData && currentNodeId
      ? graphData.nodes.find((n) => n.id === currentNodeId)
      : undefined),
    [graphData, currentNodeId]
  );
  const isCurrentStale =
    stalenessEnabled && graphEnabled && currentGraphNode?.has_stale === true;
  const [proposePending, setProposePending] = useState(false);
  const handleProposeUpdate = useCallback(() => {
    if (!selectedNode) return;
    setProposePending(true);
    Docs.stalenessFix(selectedNode.path, projectName)
      .catch(() => undefined)
      .finally(() => setProposePending(false));
  }, [selectedNode, projectName]);

  // -- (C2) Navegar a una nota por su nodeId (puede vivir en OTRA fuente) ------
  const handleOpenNoteById = useCallback(
    (nodeId: string) => {
      if (!graphData) return;
      const target = graphData.nodes.find((n) => n.id === nodeId);
      if (!target || target.kind !== "note") return;
      setDocsView("reader");
      if (target.source_id === selectedSourceId) {
        const docNode = findDocNodeByPath(indexData?.roots ?? [], target.path);
        if (docNode) setSelectedNode(docNode);
        return;
      }
      // OTRA fuente: cambiar de fuente y esperar el indexData async.
      setSelectedSourceId(target.source_id);
      setPendingOpenPath(target.path);
    },
    [graphData, selectedSourceId, indexData]
  );

  // Resolver el pendingOpenPath cuando llega el indexData de la fuente nueva.
  useEffect(() => {
    if (!pendingOpenPath) return;
    const docNode = findDocNodeByPath(indexData?.roots ?? [], pendingOpenPath);
    if (docNode) {
      setSelectedNode(docNode);
      setPendingOpenPath(null);
    } else if (indexData) {
      // el indexData llegó pero el path no existe (grafo stale): limpiar sin lanzar.
      setPendingOpenPath(null);
    }
  }, [indexData, pendingOpenPath]);

  const loadError = sourcesError || indexError;
  if (loadError) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <p className={styles.errorTitle}>Error al cargar la documentación</p>
          <p className={styles.errorDetail}>
            {loadError instanceof Error ? loadError.message : "Error de red"}
          </p>
          <p className={styles.errorHint}>
            Verificá que el backend esté corriendo en localhost:5050.
          </p>
        </div>
      </div>
    );
  }

  if (sourcesLoading || indexLoading || !selectedSourceId) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <SkeletonList rows={6} rowHeight={20} ariaLabel="Cargando documentación" />
        </div>
      </div>
    );
  }

  const roots = indexData?.roots ?? [];
  const totalDocs = roots.reduce((acc, root) => acc + countDocFiles(root.children), 0);
  const selectedProjectLabel =
    sourcesData?.project_display_name || sourcesData?.active_project || activeProject?.display_name || "Proyecto";

  return (
    <div className={styles.page}>
      <aside className={styles.sidePanel}>
        <div className={styles.sourceBox}>
          <label className={styles.sourceLabel} htmlFor="docs-source">
            Carpeta docs
          </label>
          <select
            id="docs-source"
            className={styles.sourceSelect}
            value={selectedSourceId}
            onChange={(e) => setSelectedSourceId(e.target.value)}
          >
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.configured
                  ? source.label
                  : source.kind === "project-docs"
                  ? `${selectedProjectLabel} / ${source.relative_path}`
                  : source.label}
              </option>
            ))}
          </select>
          <div className={styles.sourceMeta} title={selectedSource?.absolute_path ?? ""}>
            {selectedSource?.configured
              ? selectedSource.absolute_path
              : selectedSource?.kind === "project-docs"
              ? selectedSource.relative_path
              : sourcesData?.note ?? "Documentación interna de Stacky"}
          </div>
        </div>

        <div className={styles.searchBox}>
          <input
            type="search"
            className={styles.searchInput}
            placeholder="Buscar documentos..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            aria-label="Filtrar documentos"
          />
          {filterText && (
            <button
              className={styles.clearSearch}
              onClick={() => setFilterText("")}
              title="Limpiar búsqueda"
              aria-label="Limpiar búsqueda"
            >
              x
            </button>
          )}
        </div>

        <div className={styles.treeContainer}>
          {totalDocs === 0 ? (
            // Guard C1 (§10.7): llegar acá ya implica !sourcesError && !indexError
            // (el early-return de loadError, arriba, corta antes — dominio 135).
            <EmptyState variant="docs" />
          ) : (
            <DocTree
              roots={roots}
              onSelect={handleSelect}
              filterText={filterText}
              selectedNodeId={selectedNode?.id}
            />
          )}
        </div>

        <div className={styles.sideFooter}>
          {indexData?.indexed_at && (
            <span className={styles.indexedAt}>
              Indexado: {formatRelativeTime(indexData.indexed_at)}
            </span>
          )}
          <span className={styles.docCount}>{totalDocs} doc{totalDocs !== 1 ? "s" : ""}</span>
        </div>
      </aside>

      <main className={styles.viewerPanel}>
        {documenterEnabled && (
          <div style={{ marginBottom: 8 }}>
            <DocumenterButton projectName={projectName} />
          </div>
        )}
        {graphEnabled && (
          <div className={styles.docsTabs} role="tablist" aria-label="Vista de documentación">
            <button
              type="button"
              role="tab"
              aria-pressed={docsView === "reader"}
              className={`${styles.docsTab} ${docsView === "reader" ? styles.docsTabActive : ""}`}
              onClick={() => setDocsView("reader")}
            >
              Lector
            </button>
            <button
              type="button"
              role="tab"
              aria-pressed={docsView === "coverage"}
              className={`${styles.docsTab} ${docsView === "coverage" ? styles.docsTabActive : ""}`}
              onClick={() => setDocsView("coverage")}
            >
              Cobertura
            </button>
            <button
              type="button"
              role="tab"
              aria-pressed={docsView === "graph"}
              className={`${styles.docsTab} ${docsView === "graph" ? styles.docsTabActive : ""}`}
              onClick={() => setDocsView("graph")}
            >
              Grafo
            </button>
          </div>
        )}
        {graphEnabled && docsView === "coverage" ? (
          <DocCoveragePanel
            graph={graphData}
            isLoading={graphLoading}
            error={graphError ? String(graphError) : null}
            onRefresh={handleRefreshGraph}
          />
        ) : graphEnabled && docsView === "graph" ? (
          graphData ? (
            <DocGraphView
              graph={graphData}
              onOpenNoteById={handleOpenNoteById}
              selectedNodeId={currentNodeId}
            />
          ) : (
            <div className={styles.welcomeState}>
              <div className={styles.spinner} />
              <p className={styles.welcomeSubtitle}>
                {graphError ? "No se pudo cargar el grafo." : "Cargando grafo..."}
              </p>
            </div>
          )
        ) : selectedNode ? (
          <>
            <DocViewer
              node={selectedNode}
              content={contentData?.content ?? ""}
              isLoading={contentLoading}
              error={
                contentError
                  ? contentError instanceof Error
                    ? contentError.message
                    : "Error al cargar contenido"
                  : null
              }
              wikilinksEnabled={graphEnabled}
              nameIndex={nameIndex}
              onOpenNoteById={handleOpenNoteById}
              isStale={isCurrentStale}
              onProposeUpdate={documenterEnabled ? handleProposeUpdate : undefined}
              proposeUpdatePending={proposePending}
            />
            {graphEnabled && (
              <DocBacklinksPanel
                graph={graphData}
                currentNodeId={currentNodeId}
                onOpenNoteById={handleOpenNoteById}
              />
            )}
          </>
        ) : (
          <div className={styles.welcomeState}>
            <div className={styles.welcomeIcon}>&#128196;</div>
            <p className={styles.welcomeTitle}>Seleccioná un documento</p>
            <p className={styles.welcomeSubtitle}>
              {totalDocs} documento{totalDocs !== 1 ? "s" : ""} disponible{totalDocs !== 1 ? "s" : ""} en la carpeta seleccionada.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
