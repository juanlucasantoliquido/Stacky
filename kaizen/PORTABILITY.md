# PORTABILITY — Manifiesto de Portabilidad

> Objetivo: que mover esta carpeta a otro repositorio o convertirla en una herramienta
> independiente sea **copiar `kaizen/` y nada más**.

## Garantías de portabilidad

1. **Raíz única.** Todo vive bajo `kaizen/`. No hay archivos del sistema fuera de esta carpeta.
2. **Rutas relativas.** Ningún archivo referencia rutas absolutas ni el nombre del repo padre.
   Todas las referencias internas son relativas a la raíz `kaizen/`.
3. **Sin dependencias del padre.** El código de soporte (`scripts/`) usa **solo la librería
   estándar de Python 3**. No importa nada de `Stacky Agents/` ni de otros directorios hermanos.
4. **Formatos abiertos.** Markdown para docs/plantillas, JSON Schema para contratos, YAML/JSON
   para config y datos. Nada propietario.
5. **Acoplamiento aislado.** Cualquier dependencia hacia un proyecto concreto vive **solo** en
   `adapters/<proyecto>/`. El núcleo nunca importa un adapter por nombre fijo: lo resuelve por
   configuración (`config/kaizen.config.yaml: adapter`).

## Frontera genérico vs. reemplazable

```
GENÉRICO (se mueve tal cual)              REEMPLAZABLE (por proyecto)
────────────────────────────             ────────────────────────────
docs/  config/(esquema)  contracts/      adapters/<proyecto>/
prompts/  agents/  skills/  templates/   config/(valores concretos)
scripts/
```

- El **núcleo genérico** no conoce ningún proyecto. Define el ciclo, los contratos y las plantillas.
- El **adapter** traduce el mundo del proyecto (dónde está su código, cómo se mide una mejora,
  qué comando corre sus tests) al vocabulario genérico de Kaizen.

## Checklist para trasladar a otro repo

- [ ] Copiar la carpeta `kaizen/` completa al destino.
- [ ] Conservar `kaizen/` como raíz (o renombrarla; ningún archivo depende del nombre).
- [ ] Copiar `config/kaizen.config.example.yaml` → `config/kaizen.config.yaml` y elegir `adapter`.
- [ ] Crear `adapters/<tu-proyecto>/adapter.yaml` a partir de `adapters/example-project/`.
- [ ] Verificar: `python kaizen/scripts/new_session.py "smoke-test"` debe crear una sesión sin error.
- [ ] Borrar (opcional) `adapters/example-project/` si no aplica.

## Checklist para extraer como herramienta independiente

Ver el esqueleto detallado en [`docs/05_MIGRATION.md`](docs/05_MIGRATION.md). Resumen:

- [ ] `git subtree split` / copia de `kaizen/` a un repo nuevo, llevándola a la raíz.
- [ ] Agregar empaquetado (`pyproject.toml`) envolviendo `scripts/` como CLI `kaizen`.
- [ ] Promover `adapters/` a un sistema de plugins descubribles.
- [ ] Mantener los contratos como API pública estable (versionar con SemVer).

## Anti-portabilidad: qué está PROHIBIDO

- ❌ `import` de módulos del proyecto padre desde `scripts/`.
- ❌ Rutas absolutas (`N:\...`, `C:\...`, `/home/...`) en cualquier archivo versionado.
- ❌ Hardcodear el nombre del repo padre o de `Stacky Agents` en el núcleo genérico.
- ❌ Referenciar un adapter concreto fuera de `config/` y `adapters/`.
