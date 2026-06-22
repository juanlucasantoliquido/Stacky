# Adapters — Único punto de acoplamiento

Un **adapter** traduce el mundo de un proyecto concreto al vocabulario genérico de Kaizen.
Es la **única** parte del sistema que puede conocer detalles de un proyecto. El núcleo
(`docs/`, `contracts/`, `prompts/`, `agents/`, `skills/`, `templates/`, `scripts/`) **nunca**
nombra un adapter: lo resuelve por configuración (`config/kaizen.config.yaml: adapter`).

## Frontera

```
NÚCLEO GENÉRICO  ──(resuelve por config)──►  adapters/<proyecto>/  ──►  proyecto real (afuera)
   no sabe de proyectos                       sabe del proyecto         vive fuera de kaizen/
```

## Adapters incluidos

| Adapter | Para qué |
|---|---|
| `generic/` | Default. Sin acoplarse a nada externo. El ciclo corre con observación/aplicación manual. |
| `example-project/` | **Ejemplo ilustrativo** de qué se reemplaza al acoplar a un proyecto. No funcional; es plantilla. |

## Crear tu adapter

1. Copiá `example-project/` a `adapters/<tu-proyecto>/`.
2. Completá `adapter.yaml` según `adapter.contract.md`.
3. Seleccionalo en `config/kaizen.config.yaml: adapter: <tu-proyecto>`.
4. Secretos/credenciales: en `adapters/<tu-proyecto>/secrets/` o `.env` (ambos gitignored).

## Reglas

- Un adapter **no** importa otro adapter.
- Toda dependencia del proyecto padre se declara también en `ASSUMPTIONS.md`.
- Las rutas hacia el proyecto se expresan relativas o por variable de entorno, **nunca** absolutas
  versionadas.
