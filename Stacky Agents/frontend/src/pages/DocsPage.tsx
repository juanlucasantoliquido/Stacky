/**
 * DocsPage.tsx — Página principal de documentación (Feature #3)
 *
 * Layout dos paneles:
 *   - Panel izquierdo: campo de búsqueda + DocTree (árbol navegable)
 *   - Panel derecho: DocViewer (renderizado markdown del nodo seleccionado)
 *
 * Datos:
 *   - useQuery para getIndex() → cargado una vez, con cache de react-query
 *   - getContent() → cargado al seleccionar un nodo
 *
 * Estados:
 *   - loading inicial del índice
 *   - empty: sin documentos
 *   - error: fallo de red
 *   - sin selección: mensaje de bienvenida
 *
 * Nota sobre filtro (Fase 3.C):
 *   El estado filterText se mantiene aquí y se pasa a DocTree.
 *   El filtro opera solo sobre títulos y headings (client-side),
 *   sin re-fetch de contenido completo (v1).
 */
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import DocTree from "../components/DocTree";
import DocViewer from "../components/DocViewer";
import { Docs } from "../api/endpoints";
import type { DocNode, DocHeading } from "../api/endpoints";
import styles from "./DocsPage.module.css";

export default function DocsPage() {
  const [selectedNode, setSelectedNode] = useState<DocNode | null>(null);
  const [filterText, setFilterText] = useState("");

  // ── Cargar índice ──────────────────────────────────────────────────────────
  const {
    data: indexData,
    isLoading: indexLoading,
    error: indexError,
  } = useQuery({
    queryKey: ["docs-index"],
    queryFn: () => Docs.getIndex(),
    staleTime: 5 * 60 * 1000, // 5 min (alineado con el TTL del backend)
    retry: 2,
  });

  // ── Cargar contenido del nodo seleccionado ─────────────────────────────────
  const {
    data: contentData,
    isLoading: contentLoading,
    error: contentError,
  } = useQuery({
    queryKey: ["docs-content", selectedNode?.path],
    queryFn: () => Docs.getContent(selectedNode!.path),
    enabled: selectedNode !== null,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  // ── Selección de nodo ──────────────────────────────────────────────────────
  const handleSelect = useCallback((node: DocNode, heading?: DocHeading) => {
    setSelectedNode(node);
    // Si hay heading, scroll después de que el viewer cargue
    // (se implementa mediante ancla en el DOM; el LinkRenderer del DocViewer maneja el scroll)
    if (heading) {
      setTimeout(() => {
        const el = document.getElementById(heading.anchor);
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 300);
    }
  }, []);

  // ── Render: error de carga del índice ──────────────────────────────────────
  if (indexError) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <p className={styles.errorTitle}>Error al cargar la documentación</p>
          <p className={styles.errorDetail}>
            {indexError instanceof Error ? indexError.message : "Error de red"}
          </p>
          <p className={styles.errorHint}>
            Verificá que el backend esté corriendo en localhost:5050.
          </p>
        </div>
      </div>
    );
  }

  // ── Render: cargando índice ────────────────────────────────────────────────
  if (indexLoading) {
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
  const totalDocs = roots.reduce((acc, r) => acc + r.children.length, 0);

  return (
    <div className={styles.page}>
      {/* Panel izquierdo: búsqueda + árbol */}
      <aside className={styles.sidePanel}>
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
              No se encontró documentación. Verificá la ruta configurada.
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

      {/* Panel derecho: viewer */}
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
              {totalDocs} documento{totalDocs !== 1 ? "s" : ""} disponible{totalDocs !== 1 ? "s" : ""}.
              Hacé click en un nodo del árbol para leerlo.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
