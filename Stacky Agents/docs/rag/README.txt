STACKY DOCS/SISTEMA — CORPUS RAG (sidecar de metadata rica)
===========================================================

Que es
------
Capa RAG derivada de la doc canonica del sistema (Stacky Agents/docs/sistema/*.md).
Es un SIDECAR: NO reemplaza ni modifica la fuente, ni el indice runtime TF-IDF
(services/docs_rag.py -> tabla SQLite docs_index). Aporta chunks + metadata rica
(confianza, conectividad de grafo, links) consumible por retrieval agentico.

IMPORTANTE: extension NO-.md a proposito
----------------------------------------
Ningun archivo de este directorio usa .md. Motivo: doc_indexer._index_technical_docs()
escanea STACKY_AGENTS_ROOT/docs con rglob("*.md") (excludes solo:
node_modules,.venv,__pycache__,.git,data,dist,build). Un .md aqui seria indexado por el
DocTree 'stacky' y parseado por doc_graph (aristas de links) => contaminaria el grafo/index.
Por eso: .jsonl (corpus), .json (manifest/schema), .txt (este readme). No tocar esa regla.

Archivos
--------
- rag_corpus.jsonl : EL corpus. 94 lineas, un chunk JSON por linea. Ver schema.json.
- manifest.json    : inventario 15 archivos, conteos, prueba de no-perdida (tiling de lineas),
                     reglas de idempotencia y alineacion con el runtime.
- schema.json      : JSON Schema de un registro de chunk.
- README.txt       : este archivo.

Chunking (paridad con el runtime)
---------------------------------
Replica services/docs_rag._split_markdown_to_chunks:
  - Preambulo (todo lo anterior al primer "## ") = 1 chunk, section_heading="".
  - Cada seccion "## " = 1 chunk, desde su encabezado hasta el proximo "## " o EOF.
  - El bloque YAML graph: de 10-grafo.md §6.4 queda en UN solo chunk entero (no partido):
    10-grafo.md#c04, contains_graph_yaml=true.
Alineacion 1:1 => se puede unir este sidecar con los hits del retriever runtime por
(source_file, section_heading).

Como consumir (retrieval)
-------------------------
1. Cargar rag_corpus.jsonl (una linea = un chunk). Embeder/index text.
2. Metadata por chunk: id, source_file, section, heading_path, links_out, siblings,
   graph_node_ids, confidence, evidence, redacted, source_span.
3. Salto por grafo (ademas de similitud): desde un chunk, seguir links_out (a otros docs)
   y siblings (hermanos del encabezado); cruzar con el grafo de componentes via graph_node_ids
   (N1..N22, definidos en 10-grafo.md#c04).
4. text = contenido verbatim. Autoridad de no-perdida = source_span (line_start,line_end)
   contra la fuente inmutable docs/sistema/<source_file>.

No-perdida
----------
Cobertura 15/15 archivos (INDEX + 01..14), 94 chunks. Los source_span de cada archivo
tilan [1..EOF] de forma contigua (sin huecos ni solapes) => 100% de lineas y secciones.
Ver manifest.json -> no_loss_check y files[].spans.

Confianza / evidencia (handoff doc-graph-architect)
---------------------------------------------------
Los marcadores inline [V]/[INF]/[NV] se PRESERVAN en text y se resumen en confidence +
confidence_counts + evidence. Lo [NV] NO se materializa como hecho (ver manifest.preserved_NV).
Secretos: el fuente ya trae <REDACTADO>; se preserva el placeholder (redacted=true), nunca
el valor real.

Idempotencia
------------
chunk_id = <source_file>#c<NN> (determinista por archivo+orden de seccion). Regenerar con el
mismo fuente produce el mismo set de IDs y el mismo text. source_hash queda null en esta
corrida (sin runtime para SHA-256); un regenerador scriptado debe fijar sha256(text) por chunk.
