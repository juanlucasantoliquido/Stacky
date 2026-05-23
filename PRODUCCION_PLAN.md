# Stacky Agents — Plan para salir a producción

> Objetivo: dejar Stacky Agents instalable en la máquina de cualquier desarrollador
> **sin código fuente** (un instalador y listo), con cliente + servidor corriendo
> juntos en la misma máquina del operador. La configuración por cliente/proyecto
> se hace 100% desde la propia app.

---

## Bloqueos críticos detectados

### 1. Secretos en texto plano
- `Tools/Stacky/Stacky Agents/backend/.env` contiene `ADO_PAT=…` real, commiteable.
- `backend/projects/<NOMBRE>/auth/ado_auth.json` guarda el PAT en base64 (eso **no es cifrado**, sólo encoding).
- El instalador deja el PAT a la vista en disco una vez configurado.

### 2. Rutas hardcodeadas a la máquina del autor
- `backend/project_manager.py:12,171,222` → defaults `N:/GIT/RS/RSPacifico/trunk`,
  `N:/SVN/RS/B2Impact/trunk`, `N:/GIT/RS/MiRepo/trunk`.
- `backend/api/projects.py` repite la ruta en docstring.
- En la máquina de otro dev esos defaults son inválidos.

### 3. Empaquetado todavía requiere "código fuente"
- "Sin código fuente" hoy **no se cumple**: se copia toda la carpeta `Stacky/` con
  `.py`, `src/`, `requirements.txt`, etc. Hace falta un artefacto distribuible
  (instalador `.exe` / `.msi`) con backend congelado y frontend ya buildeado.
- `start_dashboard.bat:35` hardcodea `stacky-agents-0.3.2.vsix` → cada release
  pisa la línea a mano.
- El frontend corre con `npm run dev` (Vite dev server) en la máquina del operador:
  lento y dependiente de `node_modules` resueltos en runtime.

### 4. Faltan rutas de documentación configurables por proyecto
- Hoy `services/doc_indexer.py` autodescubre carpetas `docs/` cerca del
  `workspace_root` — funciona, pero no permite al operador elegir manualmente
  dónde está la doc técnica y dónde la funcional/manual.
- Sin esto, el panel **Docs** muestra lo que adivina, no lo que el cliente quiere.

---

## Plan propuesto (fases)

### Fase 1 — Seguridad y portabilidad (bloqueante)

1. **Quitar secretos del repo**
   - Vaciar `backend/.env` (template-only) y `projects/*/auth/*.json` antes de empaquetar.
   - Agregar regla en `.gitignore` y un script `scrub.ps1` que se ejecute antes de
     generar el artefacto distribuible.
   - **Rotar el PAT** actualmente expuesto (`UbimiaPacifico`) en ADO — acción manual de ops.

2. **Cifrado de credenciales en disco con DPAPI (Windows)**
   - Nueva utilidad `backend/services/secrets_store.py` usando
     `win32crypt.CryptProtectData` (vía `pywin32`).
   - Reemplazar el base64 actual en `ado_auth.json` / `jira_auth.json` /
     `mantis_auth.json` por blob cifrado ligado al SID del usuario.
   - Migración automática al primer arranque: si detecta `pat_format: "raw"` o
     base64, lo recifra con DPAPI y reescribe el archivo.

3. **Eliminar rutas hardcodeadas**
   - `project_manager.py:12,171,222`: reemplazar defaults `N:/GIT/...` por `""`.
   - Forzar al usuario a setear `workspace_root` desde el modal de "Nuevo proyecto"
     (validar que la carpeta exista al guardar).
   - Quitar las menciones de `N:/GIT/...` del docstring de `api/projects.py`.

---

### Fase 2 — Extender el modal de proyecto con rutas de documentación

El modal de **Nuevo proyecto** y **Editar proyecto** del nav bar ya existe
(`frontend/src/components/NewProjectModal.tsx`, `EditProjectModal.tsx`) y ya pide
`workspace_root` + credenciales del tracker. Sólo agregamos campos nuevos.

4. **Nuevos campos en el modal**
   - `docs_technical_path` — carpeta raíz de documentación técnica.
   - `docs_functional_path` — carpeta raíz de documentación funcional / manual.
   - Ambos opcionales. Botón **Examinar…** (file picker nativo) para evitar tipeo.
   - Validar al guardar: si están seteados, deben existir y ser carpetas leíbles.

5. **Persistencia**
   - Extender `project_manager.py` y el schema de `projects/<NOMBRE>/config.json`:
     ```json
     {
       "name": "RSPACIFICO",
       "workspace_root": "…",
       "docs_paths": {
         "technical":  "N:/Docs/RSPacifico/tecnica",
         "functional": "N:/Docs/RSPacifico/funcional"
       },
       "issue_tracker": { … }
     }
     ```
   - Migración suave: si `docs_paths` no existe se mantiene el autodescubrimiento actual.

6. **API**
   - `PATCH /api/projects/<name>` ya acepta merge — sumar validación de `docs_paths`.
   - Nuevo endpoint `POST /api/projects/<name>/test_docs_paths` (devuelve cuántos
     archivos `.md` / `.pdf` ve en cada carpeta) para feedback inmediato en el modal.

7. **Integrar las rutas configuradas en el panel Docs**
   - En `backend/services/doc_indexer.py` (líneas 321, 369, 412) reemplazar la
     heurística por:
     1. Si `docs_paths.technical` está seteado → indexar como root "📐 Técnica".
     2. Si `docs_paths.functional` está seteado → indexar como root "📋 Funcional / Manual".
     3. Si ambas vacías → caer al autodescubrimiento actual (compatibilidad).
   - En el frontend (`DocsPage.tsx`) mostrar las dos raíces como tabs o como
     árboles separados; el nombre del root viene del backend.

---

### Fase 3 — Empaquetado distribuible sin código fuente

Cliente y servidor van en la **misma máquina** del operador (sin remoto, sin
servicios externos). Lo que cambia es **cómo se distribuye**.

8. **Build de frontend al empaquetar (no en runtime)**
   - `npm run build` → `frontend/dist/`.
   - Agregar ruta en Flask que sirva `dist/` desde `/` (un sólo proceso, un sólo puerto).
   - Quita la necesidad de `npm run dev` y de tener `node_modules` en la máquina destino.

9. **Backend congelado con PyInstaller**
   - `pyinstaller --onedir backend/app.py` → `stacky-backend.exe` con todas las
     deps embebidas (Flask, SQLAlchemy, requests, dotenv, truststore, pywin32).
   - Elimina `requirements.txt` y `.venv` del payload distribuido.

10. **Instalador MSI/EXE (Inno Setup o WiX)**
    - Empaqueta: `stacky-backend.exe`, `frontend/dist/`, `vscode_extension/*.vsix`,
      `data/` vacío, `START.bat`.
    - Auto-detecta `code.cmd` e instala el `.vsix` **más reciente** (glob, no versión fija).
    - Crea acceso directo en menú inicio y escritorio.
    - Idempotente: detecta versión previa, **preserva `data/` y `projects/`**
      (el usuario no pierde su configuración al actualizar).
    - Desinstalador limpio (deja `data/` por seguridad, lo borra sólo con flag explícito).

11. **Fix de `start_dashboard.bat:35`**
    - Reemplazar `stacky-agents-0.3.2.vsix` por glob:
      `for /f "delims=" %%i in ('dir /b /o-d vscode_extension\stacky-agents-*.vsix') do …`
    - Así no hay que tocar el `.bat` en cada release.

12. **CORS / puertos**
    - Cuando Flask sirve el frontend buildeado, `ALLOWED_ORIGINS` queda
      irrelevante (mismo origen). Dejar la variable sólo para modo dev.
    - Mantener `PORT` configurable (`.env` o `data/runtime_config.json`) por si
      5050 está ocupado en la máquina destino.

---

### Fase 4 — Operación local en la máquina del operador

> **Aclaración de alcance**: la app corre 100% local en la máquina del dev. No hay
> servidor central, no hay telemetría remota, no hay servicio Windows. Sólo
> nos aseguramos de que si algo falla, el operador (o el equipo de soporte) pueda
> diagnosticarlo sin abrir VS Code ni leer logs crudos.

13. **Pantalla de diagnóstico in-app**
    - Nueva ruta `/diagnostics` en el frontend que muestre, con semáforo verde/rojo:
      - Backend up (`/api/health`).
      - ADO/Jira alcanzable con las credenciales guardadas.
      - `gh` autenticado.
      - VS Code instalado y `.vsix` presente.
      - Bridge VS Code :5052 respondiendo.
      - `data/stacky_agents.db` escribible y con espacio.
    - Integra y reemplaza el script suelto `backend/tmp_diag.py`.

14. **Logs a archivo rotativo local**
    - Escribir a `data/logs/stacky-YYYY-MM-DD.log` (rotación diaria, 14 días de retención).
    - Botón "Exportar logs" en la pantalla de diagnóstico → genera un `.zip` con
      últimos 3 días, para enviar a soporte.

15. **Backup local automático de la DB**
    - Copia semanal de `data/stacky_agents.db` a `data/backups/stacky_agents-YYYYMMDD.db`.
    - Mantener los últimos 4. Tarea schedulable desde `start_dashboard.bat` o
      al arrancar el backend si detecta que no hay backup esta semana.

---

### Fase 5 — Calidad y CI de release

16. **Pipeline de empaquetado en ADO**
    - En cada tag `vX.Y.Z`: `npm run build`, `pyinstaller`, generar `.msi`,
      firmar con Authenticode (requiere certificado), publicar release.

17. **Smoke test post-instalación**
    - Pytest mínimo que arranque el backend en puerto random, llame `/api/health`,
      `/api/projects`, valide que el frontend buildeado se sirve correctamente.
    - Se ejecuta como último paso de `INSTALL.ps1` antes de declarar éxito.

18. **Limpieza del payload distribuido**
    - Sacar del `.msi` los `.md` de roadmap/análisis interno
      (`ArreglosStackyAgents.md`, `MejorasStackyAgent.md`,
      `STACKY_AGENTS_COMPLETE.md`, `Stacky Agents QA UAT roadmap *.md`,
      `README_PARA_AGENTES.md`).
    - Mantener sólo `INSTALLER.md` + un `OPERATOR_GUIDE.md` nuevo orientado a
      "cómo usar la app, no cómo construirla".

---

## Resumen de entregables

| Entregable | Fase | Estado actual |
|---|---|---|
| Cifrado DPAPI de PAT/tokens | 1 | No existe (base64 plano) |
| Defaults sin rutas locales del autor | 1 | Hardcodeado `N:/GIT/...` |
| Campos `docs_paths` en modal de proyecto | 2 | No existen |
| Panel Docs usando rutas configuradas | 2 | Sólo autodescubrimiento |
| Backend congelado (PyInstaller) | 3 | Corre con `python app.py` |
| Frontend buildeado y servido por Flask | 3 | `npm run dev` en runtime |
| Instalador MSI/EXE firmado | 3 | `INSTALL.ps1` + copiar carpeta |
| Detección automática del `.vsix` | 3 | Versión fija en `.bat` |
| Pantalla de diagnóstico in-app | 4 | Script suelto `tmp_diag.py` |
| Logs a archivo rotativo local | 4 | Sólo stdout |
| Backup local de la DB | 4 | No existe |
| CI de release con firma | 5 | No existe |
| Payload limpio (sin docs internos) | 5 | Distribuye todos los `.md` |

---

## Orden sugerido de ejecución

1. **Fase 1** (seguridad y rutas) — bloqueante: sin esto no se puede ni instalar en
   una segunda máquina sin filtrar credenciales.
2. **Fase 2** (docs_paths en modal de proyecto) — habilita que el operador
   configure todo desde la UI sin tocar JSON.
3. **Fase 3** (empaquetado) — recién acá se cumple "instalable sin código fuente".
4. **Fase 4** (operación local) — calidad de vida para soporte.
5. **Fase 5** (CI) — automatizar lo que las fases 1-4 dejaron listo.

Fases 1 y 2 se pueden hacer en paralelo (tocan archivos distintos). Fase 3
depende de tener 1 y 2 listas para no congelar un backend con secretos hardcodeados.
