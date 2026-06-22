# artifacts/

Artefactos **promovidos** desde las sesiones que se quieren conservar (diffs, reportes, datasets,
notas). Cada artefacto debería acompañarse de metadatos conforme a
`contracts/artifact.schema.json` (al menos: `id`, `session_id`, `kind`, `path`, `created_utc`).

- Las rutas en los metadatos son **relativas** a la raíz `kaizen/`.
- El contenido de esta carpeta está gitignored por defecto (datos locales); se versiona este README.
  Versioná manualmente lo que deba perdurar.
