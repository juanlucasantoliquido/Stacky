# 05 — Esqueleto de Migración a Herramienta Independiente

> Cómo extraer `kaizen/` a su propio repositorio / paquete sin reescribir el núcleo.

## Estado objetivo

```
kaizen-tool/                 (repo nuevo, kaizen/ promovido a raíz)
├── pyproject.toml           # empaqueta scripts/ como CLI `kaizen`
├── src/kaizen/              # = scripts/ actuales, como módulo instalable
│   ├── __init__.py
│   ├── cli.py               # envuelve new_session.py y futuros comandos
│   └── core/                # validación de contratos, índice de sesiones
├── contracts/               # API pública estable (SemVer)
├── docs/  prompts/  agents/  skills/  templates/   (tal cual)
├── adapters/                # sistema de plugins descubribles
└── config/
```

## Pasos

### Fase M0 — Extracción (sin cambios de código)

- [ ] `git subtree split --prefix=kaizen <rama>` → repo nuevo, o copia directa de `kaizen/`.
- [ ] Promover `kaizen/` a la raíz del repo nuevo.
- [ ] Verificar que el smoke test sigue verde: `python scripts/new_session.py "smoke"`.

> Como el núcleo no referencia el repo padre ni rutas absolutas (ver `PORTABILITY.md`), esta fase
> no requiere tocar código.

### Fase M1 — Empaquetado

- [ ] Agregar `pyproject.toml` con un entry-point `kaizen = "kaizen.cli:main"`.
- [ ] Mover `scripts/new_session.py` → `src/kaizen/` y exponerlo como subcomando `kaizen new`.
- [ ] Mantener compatibilidad: `python scripts/new_session.py` puede quedar como shim.

### Fase M2 — Contratos como API pública

- [ ] Congelar los esquemas de `contracts/` bajo SemVer (ver `contracts/README.md`).
- [ ] Agregar un validador (`kaizen validate <session>`) que chequee artefactos contra esquemas.

### Fase M3 — Adapters como plugins

- [ ] Definir descubrimiento de adapters (entry-points o carpeta `adapters/` escaneada).
- [ ] El adapter `generic/` queda como referencia y default.
- [ ] Documentar el contrato de plugin a partir de `adapters/adapter.contract.md`.

### Fase M4 — Motor AOTL (opcional)

- [ ] Implementar un runner que ejecute `agents/improver` y `agents/evaluator` contra un motor real,
      detrás del contrato de adapter (el núcleo sigue sin dependencias).

## Qué NO cambia al migrar

- El **ciclo** (observar→proponer→evaluar→decidir→registrar).
- Los **contratos** (son la API).
- Las **plantillas**, **prompts**, **docs** y la rúbrica de evaluación.
- La **frontera** genérico/adapter.

> Migrar es promover de carpeta a paquete, no rediseñar. El diseño actual ya separa núcleo
> portable de acoplamiento por adapter justamente para que esta migración sea mecánica.
