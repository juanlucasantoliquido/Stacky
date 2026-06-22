# scripts/

Utilidades de soporte. **Garantía de portabilidad:** solo librería estándar de Python 3, sin red,
sin importar nada del proyecto padre, sin rutas absolutas. Resuelven todo relativo a la raíz
`kaizen/` (que se calcula desde la ubicación del propio script).

| Script | Qué hace | Uso |
|---|---|---|
| `new_session.py` | Crea una sesión nueva desde las plantillas y la registra en el índice. | `python scripts/new_session.py "<objetivo>"` |

## Garantías de `new_session.py`
- No sobrescribe sesiones existentes.
- No realiza acciones destructivas.
- Imprime la ruta de la sesión creada y sale con código 0 en éxito.
- Lee el `mode`/`adapter` de `config/kaizen.config.yaml` si existe; si no, usa defaults
  (`hitl` / `generic`) sin fallar.
