---
name: project-feature3-doctree
description: Feature #3 DocTree — estado completo, decisiones de implementación y hashes de commit
metadata:
  type: project
---

Feature #3 DocTree COMPLETA al 2026-05-19.

**Commits:**
- 3.A: `f4a68f4` — backend doc_indexer + /api/docs blueprint + 32 tests
- 3.B: `998af7f` — frontend DocsPage + DocTree + DocViewer (sin filtro separado)
- 3.C: `ff9d071` — filtro por texto libre con resaltado HighlightedText

**Why:** El SDD requería una pestaña "Docs" para navegar documentacion interna sin abrir el filesystem.

**Decisiones aplicadas:**
- DO-3.1: 3 raices: docs/, raiz *.md, y VSCODE_PROMPTS_DIR/*.agent.md
- DO-3.2: 3 secciones separadas en el arbol
- DO-3.4: react-markdown@9.0.1 + rehype-highlight@7.0.0 + remark-gfm@4.0.0 ya estaban en package.json

**Arquitectura backend:**
- `services/doc_indexer.py`: STACKY_AGENTS_ROOT = Path(__file__).parents[1] (backend → Stacky Agents/)
- Cache TTL 5min en variable modulo (_cache: tuple[float, dict] | None)
- Seguridad: read_content() usa Path.resolve() + comparacion contra raices permitidas
- Excludes: node_modules/, .venv/, __pycache__/, .git/, data/
- Blueprint registrado en api/__init__.py como docs_bp

**Arquitectura frontend:**
- Filtro 3.C: cliente-side sobre label + headings (no contenido completo — v1 deliberado)
- HighlightedText() resalta con <mark> la primera ocurrencia del filtro
- Links externos → target="_blank"; internos → preventDefault + scroll a ancla
- filterText state en DocsPage.tsx pasado hacia DocTree.tsx

**How to apply:** Si se amplian las raices o se agrega indexado en tiempo real, extender doc_indexer.py y agregar evento docs_index_invalidated a stacky_logger.
