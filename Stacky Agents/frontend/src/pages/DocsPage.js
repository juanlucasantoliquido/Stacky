import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import { useWorkbench } from "../store/workbench";
import styles from "./DocsPage.module.css";
function countDocFiles(nodes = []) {
    return nodes.reduce((acc, node) => {
        if (node.kind === "folder")
            return acc + countDocFiles(node.children ?? []);
        return acc + 1;
    }, 0);
}
export default function DocsPage() {
    const activeProject = useWorkbench((s) => s.activeProject);
    const projectName = activeProject?.name;
    const [selectedNode, setSelectedNode] = useState(null);
    const [filterText, setFilterText] = useState("");
    const [selectedSourceId, setSelectedSourceId] = useState("");
    useEffect(() => {
        setSelectedNode(null);
        setFilterText("");
        setSelectedSourceId("");
    }, [projectName]);
    // -- Fuentes/carpeta docs del proyecto activo -------------------------------
    const { data: sourcesData, isLoading: sourcesLoading, error: sourcesError, } = useQuery({
        queryKey: ["docs-sources", projectName ?? "active"],
        queryFn: () => Docs.getSources(projectName),
        staleTime: 60 * 1000,
        retry: 1,
    });
    const sources = sourcesData?.sources ?? [];
    const selectedSource = sources.find((source) => source.id === selectedSourceId) ?? null;
    useEffect(() => {
        if (!sourcesData)
            return;
        const nextSourceId = sourcesData.default_source_id || sourcesData.sources[0]?.id || "stacky";
        const currentStillExists = sourcesData.sources.some((source) => source.id === selectedSourceId);
        if (!selectedSourceId || !currentStillExists) {
            setSelectedSourceId(nextSourceId);
        }
    }, [sourcesData, selectedSourceId]);
    useEffect(() => {
        setSelectedNode(null);
    }, [selectedSourceId]);
    // -- Cargar índice ----------------------------------------------------------
    const { data: indexData, isLoading: indexLoading, error: indexError, } = useQuery({
        queryKey: ["docs-index", projectName ?? "active", selectedSourceId],
        queryFn: () => Docs.getIndex({ project: projectName, sourceId: selectedSourceId }),
        enabled: selectedSourceId.length > 0,
        staleTime: 5 * 60 * 1000,
        retry: 2,
    });
    // -- Cargar contenido del nodo seleccionado ---------------------------------
    const selectedContentSourceId = selectedNode?.source_id ?? selectedSourceId;
    const { data: contentData, isLoading: contentLoading, error: contentError, } = useQuery({
        queryKey: ["docs-content", projectName ?? "active", selectedContentSourceId, selectedNode?.path],
        queryFn: () => Docs.getContent(selectedNode.path, {
            project: projectName,
            sourceId: selectedContentSourceId,
        }),
        enabled: selectedNode !== null && selectedNode.kind !== "folder",
        staleTime: 5 * 60 * 1000,
        retry: 1,
    });
    // -- Selección de nodo ------------------------------------------------------
    const handleSelect = useCallback((node, heading) => {
        setSelectedNode(node);
        if (heading) {
            setTimeout(() => {
                const el = document.getElementById(heading.anchor);
                if (el)
                    el.scrollIntoView({ behavior: "smooth" });
            }, 300);
        }
    }, []);
    const loadError = sourcesError || indexError;
    if (loadError) {
        return (_jsx("div", { className: styles.page, children: _jsxs("div", { className: styles.errorState, children: [_jsx("p", { className: styles.errorTitle, children: "Error al cargar la documentaci\u00F3n" }), _jsx("p", { className: styles.errorDetail, children: loadError instanceof Error ? loadError.message : "Error de red" }), _jsx("p", { className: styles.errorHint, children: "Verific\u00E1 que el backend est\u00E9 corriendo en localhost:5050." })] }) }));
    }
    if (sourcesLoading || indexLoading || !selectedSourceId) {
        return (_jsx("div", { className: styles.page, children: _jsxs("div", { className: styles.loadingState, children: [_jsx("div", { className: styles.spinner }), _jsx("p", { children: "Cargando documentaci\u00F3n..." })] }) }));
    }
    const roots = indexData?.roots ?? [];
    const totalDocs = roots.reduce((acc, root) => acc + countDocFiles(root.children), 0);
    const selectedProjectLabel = sourcesData?.project_display_name || sourcesData?.active_project || activeProject?.display_name || "Proyecto";
    return (_jsxs("div", { className: styles.page, children: [_jsxs("aside", { className: styles.sidePanel, children: [_jsxs("div", { className: styles.sourceBox, children: [_jsx("label", { className: styles.sourceLabel, htmlFor: "docs-source", children: "Carpeta docs" }), _jsx("select", { id: "docs-source", className: styles.sourceSelect, value: selectedSourceId, onChange: (e) => setSelectedSourceId(e.target.value), children: sources.map((source) => (_jsx("option", { value: source.id, children: source.configured
                                        ? source.label
                                        : source.kind === "project-docs"
                                            ? `${selectedProjectLabel} / ${source.relative_path}`
                                            : source.label }, source.id))) }), _jsx("div", { className: styles.sourceMeta, title: selectedSource?.absolute_path ?? "", children: selectedSource?.configured
                                    ? selectedSource.absolute_path
                                    : selectedSource?.kind === "project-docs"
                                        ? selectedSource.relative_path
                                        : sourcesData?.note ?? "Documentación interna de Stacky" })] }), _jsxs("div", { className: styles.searchBox, children: [_jsx("input", { type: "search", className: styles.searchInput, placeholder: "Buscar documentos...", value: filterText, onChange: (e) => setFilterText(e.target.value), "aria-label": "Filtrar documentos" }), filterText && (_jsx("button", { className: styles.clearSearch, onClick: () => setFilterText(""), title: "Limpiar b\u00FAsqueda", "aria-label": "Limpiar b\u00FAsqueda", children: "x" }))] }), _jsx("div", { className: styles.treeContainer, children: totalDocs === 0 ? (_jsx("div", { className: styles.emptyState, children: sourcesData?.note ?? "No se encontró documentación. Verificá la ruta configurada." })) : (_jsx(DocTree, { roots: roots, onSelect: handleSelect, filterText: filterText, selectedNodeId: selectedNode?.id })) }), _jsxs("div", { className: styles.sideFooter, children: [indexData?.indexed_at && (_jsxs("span", { className: styles.indexedAt, children: ["Indexado: ", new Date(indexData.indexed_at).toLocaleTimeString()] })), _jsxs("span", { className: styles.docCount, children: [totalDocs, " doc", totalDocs !== 1 ? "s" : ""] })] })] }), _jsx("main", { className: styles.viewerPanel, children: selectedNode ? (_jsx(DocViewer, { node: selectedNode, content: contentData?.content ?? "", isLoading: contentLoading, error: contentError
                        ? contentError instanceof Error
                            ? contentError.message
                            : "Error al cargar contenido"
                        : null })) : (_jsxs("div", { className: styles.welcomeState, children: [_jsx("div", { className: styles.welcomeIcon, children: "\uD83D\uDCC4" }), _jsx("p", { className: styles.welcomeTitle, children: "Seleccion\u00E1 un documento" }), _jsxs("p", { className: styles.welcomeSubtitle, children: [totalDocs, " documento", totalDocs !== 1 ? "s" : "", " disponible", totalDocs !== 1 ? "s" : "", " en la carpeta seleccionada."] })] })) })] }));
}
