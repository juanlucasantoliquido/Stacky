# 13 — Documentación, RAG y Grafo documental

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [06-servicios-daemons](06-servicios-daemons.md) · [10-grafo](10-grafo.md)

Subsistema que indexa, busca, grafica y (opcionalmente) documenta los `.md` de un proyecto. Construido por los
planes 109-115 (grafo read-only, wikilinks, retrieval híbrido, documentador, doctor de staleness, motor TF-IDF
compartido) + 137 (documentador v2). Es el motor que consume la `DocsPage` del SPA. [V: frontend/src/App.tsx:8; api/docs.py:1-16]

## Superficie API
### `/api/docs` (blueprint `docs`) [V: api/docs.py:28,52-347]
| Ruta | Función | Plan |
|------|---------|------|
| GET `/sources` | fuentes docs seleccionables (+ flags graph/documenter/staleness) | — [V: docs.py:52-60] |
| GET `/index` | árbol indexado de documentos | — [V: docs.py:66] |
| GET `/content?path=` | contenido raw (path traversal bloqueado) | — [V: docs.py:133; docstring:10] |
| GET `/graph` | grafo documental (links md, wikilinks, refs a código) | 109 [V: docs.py:210] |
| POST `/documenter/run`, GET `/documenter/status`, POST `/documenter/decide` | documentador 1-click / panel de revisión | 113/137 [V: docs.py:267,290,347] |
| POST `/staleness/fix` | doctor de staleness doc↔código | 114 [V: docs.py:316] |

### `/api/docs-rag` (blueprint `docs_rag`) [V: api/docs_rag.py:30,126-215]
POST `/index` · GET `/stats` · POST `/search` · POST `/chat`. Indexa `workspace_root/docs_subpath/**/*.md` en la
tabla SQLite `docs_index` y busca chunks por similitud TF-IDF para enriquecer el contexto de un LLM. [V: services/docs_rag.py:1-10; api/docs_rag.py:126-215]

## Servicios / motores
- `doc_indexer` — resuelve fuentes docs y sirve contenido (cache 5 min, bloquea path traversal). [V: api/docs.py:10-11,24]
- `doc_graph` — grafo READ-ONLY: parsea aristas md→md, wikilinks `[[x]]` y refs a código; NO escribe, NO usa LLM, NO hace retrieval. [V: services/doc_graph.py:1-6]
- `docs_rag` — índice TF-IDF por proyecto en tabla `docs_index`. [V: services/docs_rag.py:1-10]
- `rag_retriever` — RAG local TF-IDF puro, funciones sin estado/red/LLM; usa `lexical_core` (núcleo compartido, plan 115). [V: services/rag_retriever.py:1-12]
- Modelo persistente `DocChunk` (creado por `init_db`). [V: db.py:42-80; ver 03-modelo-datos]

## Flags [V: config.py:511-539,516-526]
| Flag | Default | Controla | Plan |
|------|---------|----------|------|
| `STACKY_DOCS_GRAPH_ENABLED` | true | endpoint `/api/docs/graph` | 109 [V: config.py:511-512] |
| `STACKY_DOCS_DOCUMENTER_ENABLED` | true | documentador 1-click | 113 [V: config.py:530-531] |
| `STACKY_DOCS_STALENESS_ENABLED` | true | doctor de staleness | 114 [V: config.py:538-539] |
| `STACKY_DOCS_RAG_HYBRID_ENABLED` | true | retrieval híbrido (+`_ALPHA`/`_BETA`/`_MAX_NEIGHBORS`) | 112 [V: config.py:516-526] |

## Relación con esta doc canónica
Este subsistema opera sobre CUALQUIER fuente de `.md` de un proyecto (incluida `docs/sistema/`). El grafo de
`/api/docs/graph` es un grafo de LINKS entre notas; el grafo de sistema de [10-grafo](10-grafo.md) es un grafo de
COMPONENTES. Son complementarios, no el mismo artefacto. [INF: doc_graph.py:1-6 parsea links; 10-grafo modela componentes]

## Límites
- Coincidencia de nombres de wikilinks y refs a código es heurística (regex); falsos positivos posibles. [INF: doc_graph.py:18-29]
- El documentador v2 (plan 137, evidencia real + citas verificadas + panel de revisión) tiene endpoints en código pero su implementación completa está pendiente. [V: docs.py:267-347 rutas existen] / [INF: MEMORY plan-137-status "falta implementar"]
