/**
 * DocsPage.tsx - Página principal de documentación (Feature #3)
 *
 * Layout dos paneles:
 *   - Panel izquierdo: selector de fuente/carpeta, búsqueda y DocTree
 *   - Panel derecho: DocViewer con el markdown seleccionado
 */
import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import DocTree from "../components/DocTree";
import DocViewer from "../components/DocViewer";
import { Docs } from "../api/endpoints";
import type { DocNode, DocHeading } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./DocsPage.module.css";

function countDocFiles(nodes: DocNode[] = []): number {
  return nodes.reduce((acc, node) => {
    if (node.kind === "folder") return acc + countDocFiles(node.children ?? []);
    return acc + 1;
  }, 0);
}

export default function DocsPage() {
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name;
  const [selectedNode, setSelectedNode] = useState<DocNode | null>(null);
  const [filterText, setFilterText] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");

  useEffect(() => {
    setSelectedNode(null);
    setFilterText("");
    setSelectedSourceId("");
  }, [projectName]);

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
          <div className={styles.spinner} />
          <p>Cargando documentación...</p>
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
                {source.kind === "project-docs"
                  ? `${selectedProjectLabel} / ${source.relative_path}`
                  : source.label}
              </option>
            ))}
          </select>
          <div className={styles.sourceMeta} title={selectedSource?.absolute_path ?? ""}>
            {selectedSource?.kind === "project-docs"
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
            <div className={styles.emptyState}>
              {sourcesData?.note ?? "No se encontró documentación. Verificá la ruta configurada."}
            </div>
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
              Indexado: {new Date(indexData.indexed_at).toLocaleTimeString()}
            </span>
          )}
          <span className={styles.docCount}>{totalDocs} doc{totalDocs !== 1 ? "s" : ""}</span>
        </div>
      </aside>

      <main className={styles.viewerPanel}>
        {selectedNode ? (
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
          />
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
