# Manual de uso — Memoria colaborativa de Stacky Agents

> Guía práctica para **activar**, **usar**, **notar** y **probar** la feature de
> memoria colaborativa. Pensada para operar sin conocer el código.
>
> Plan de diseño: `docs/plans/plan-memoria-colaborativa-stacky-agents-2026-06-06-v2.md`

---

## 1. Qué es (en una frase)

Stacky puede **recordar** lo aprendido en ejecuciones anteriores (bugs, decisiones,
hallazgos, políticas del cliente) y **reinyectar** ese conocimiento al contexto de
los agentes en runs futuros, con curaduría, validación de seguridad y —si se quiere—
sincronización entre máquinas vía Git.

---

## 2. Lo más importante: todo nace APAGADO

La feature **no cambia nada** del comportamiento actual hasta que vos prendés un
interruptor (flag). De fábrica:

- No se inyecta memoria a los prompts.
- No se captura memoria automáticamente.
- El validador no corre checks caros.
- No hay sincronización por Git.
- El frontend muestra solo lo mínimo (lista de memorias + borradores).

Esto es a propósito: primero se valida la memoria **local**, y recién cuando haya
demanda real se prende la colaboración por Git (que además requiere aprobación del
cliente porque empuja datos a un repositorio compartido).

---

## 3. Los interruptores (flags)

### Backend — archivo `Stacky Agents/backend/.env`

| Flag | Qué hace | Default |
|---|---|---|
| `STACKY_MEMORY_INJECTION_ENABLED` | Inyecta el bloque "Memoria Stacky relevante" al inicio del prompt de cada agente | `false` |
| `STACKY_MEMORY_CAPTURE_ENABLED` | Captura memoria automáticamente al terminar/aprobar una ejecución | `false` |
| `STACKY_MEMORY_CAPTURE_MIN_SCORE` | Umbral de `contract_score` para crear un borrador | `70` |
| `STACKY_MEMORY_VALIDATOR_ADVANCED` | Habilita los checks caros del validador (duplicado semántico, grafo de conflictos, LLM judge) | `false` |
| `STACKY_MEMORY_GIT_SYNC_ENABLED` | Sincronización colaborativa por Git (Fase E) | `false` |
| `STACKY_PRE_RUN_GIT_PULL_ENABLED` | Hace `git pull` del workspace antes de cada run | `false` |
| `STACKY_PRE_RUN_GIT_PULL_REQUIRED` | Si el pre-run falla, bloquea el run | `false` |
| `STACKY_PRE_RUN_GIT_WORKSPACE_POLICY` | Política de frescura del workspace | `fetch_only_warn` |

> Después de tocar el `.env`, **reiniciá el backend** para que tome los cambios.

### Frontend — archivo `Stacky Agents/frontend/.env.local`

| Flag | Qué hace | Default |
|---|---|---|
| `VITE_MEMORY_ADVANCED` | Muestra las vistas avanzadas: pestañas **Triage** y **Grafo**, botón **Validar** y los **badges** de memoria en el tablero de tickets | `false` (no definido) |

> Después de tocar `.env.local`, **reconstruí/reiniciá el frontend** (`npm run dev`
> en desarrollo, o `npm run build` para producción).

Además, la sección "Memoria" del menú se activa/desactiva desde
**Configuración → Memoria** (igual que PM / Logs / Docs).

---

## 4. Activación paso a paso

### 4.1 Memoria local + inyección (lo central — empezá por acá)

1. En `backend/.env`:
   ```
   STACKY_MEMORY_CAPTURE_ENABLED=true
   STACKY_MEMORY_INJECTION_ENABLED=true
   ```
2. Reiniciá el backend.
3. Corré un agente sobre un ticket y **aprobalo** (verdict = `approved`).
   → Se crea una **memoria activa** con el resumen de esa ejecución.
4. Corré otro agente sobre un ticket relacionado.
   → Su contexto arranca con un bloque **"Memoria Stacky relevante: <proyecto>"**.

**Qué pasa por dentro (resumen):**
- Al **completar** un run con score ≥ umbral se crea un **borrador** (`draft`).
- Al **aprobar** el run, el borrador se **promueve** a `active` (y ya se inyecta).
- La inyección usa búsqueda TF-IDF (sin FTS5), ordena por relevancia + agente +
  confianza, y respeta topes por agente (p. ej. Developer hasta ~14k caracteres).
- Cualquier dato personal (email, DNI, CUIT, teléfono, tarjeta, CBU) se **redacta
  de forma irreversible** (`[PII_EMAIL]`, etc.) antes de guardarse o reinyectarse.

### 4.2 Solo capturar, sin inyectar (modo observación)

Si querés ver qué memoria se generaría sin que afecte a los agentes todavía:
```
STACKY_MEMORY_CAPTURE_ENABLED=true
STACKY_MEMORY_INJECTION_ENABLED=false
```
Las memorias aparecen en la UI (pestañas Memorias / Borradores) pero **no** entran a
ningún prompt.

### 4.3 Vistas avanzadas en el frontend (Triage / Grafo / Validar)

1. Creá `frontend/.env.local` con:
   ```
   VITE_MEMORY_ADVANCED=true
   ```
2. Reconstruí/reiniciá el frontend.
   → Reaparecen las pestañas **Triage** (hallazgos del validador) y **Grafo**
   (conflictos entre memorias), el botón **Validar** y los **badges** por ticket.

### 4.4 Validador (chequeos de calidad/seguridad)

- Con el botón **Validar** (requiere 4.3) se lanza un run de validación.
- Por default corre **4 checks baratos**: esquema, checksum, **secreto** y
  duplicado exacto.
- Los checks caros (duplicado semántico, grafo de conflictos, **LLM judge**) solo
  corren si además ponés en `backend/.env`:
  ```
  STACKY_MEMORY_VALIDATOR_ADVANCED=true
  ```
  (Esto evita gastar tokens de LLM sin querer.)

### 4.5 Sincronización Git colaborativa (Fase E) — DIFERIDA

> ⚠️ Empuja memoria a un **repositorio Git compartido**. Requiere **aprobación
> explícita del cliente** antes de activarse. Está apagada por default y, aunque
> alguien la dispare por API, no hace nada sin `enabled`.

Cuando se decida activarla:
1. En `backend/.env`: `STACKY_MEMORY_GIT_SYNC_ENABLED=true`.
2. Se usa un **repositorio de memoria dedicado y separado**
   (`<STACKY_HOME>/memory_repos/<proyecto>/`), **nunca** el repo del producto del
   cliente.
3. Solo se exportan memorias `active` de scope `project`/`team`/`global` (nunca
   `personal`/`private`), con **secretos en cuarentena** y **PII ya redactada**.

---

## 5. Cómo NOTÁS cada cambio (checklist visual)

| Cambio | Dónde mirarlo |
|---|---|
| La página de Memoria existe | Menú → **Memoria** (activable en Configuración) |
| MVP replegado | La página muestra **solo** "Memorias" y "Borradores" (sin Triage/Grafo/Validar) salvo que prendas `VITE_MEMORY_ADVANCED` |
| Captura post-run | Tras aprobar un run, aparece una fila en **Memorias**; antes de aprobar, en **Borradores** |
| Inyección | El prompt/contexto del agente arranca con **"Memoria Stacky relevante"** |
| Redacción PII | El contenido de una memoria muestra `[PII_EMAIL]` en vez del email real |
| Tablero desacoplado | Con el flag avanzado **apagado**, el tablero de tickets no pide badges de memoria |

---

## 6. Cómo PROBARLO (tests automáticos)

Desde PowerShell:

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"

# Recomendado: un archivo por vez (verde determinista)
foreach ($f in "test_memory_store","test_memory_injection","test_memory_api","test_post_run_memory","test_pre_run_git","test_memory_validator","test_memory_git_sync") {
  .\.venv\Scripts\python.exe -m pytest "tests/$f.py" -q
}
```

Lo que verifican, entre otros:
- Un **secreto nunca se exporta** (queda en cuarentena).
- Un **email se redacta** antes de exportarse o de reinyectarse.
- Un re-run **no degrada** una memoria ya aprobada.
- Los tipos que ya inyecta el system prompt (decisiones, anti-patrones, etc.) **no
  se doble-inyectan** por el user prompt.
- `POST /sync/run` sin `enabled` **no** activa la sincronización.

> ⚠️ **Caveat de testing:** correr los 7 archivos en **un solo comando** puede tirar
> `database table is locked`. Es una fragilidad del entorno de tests (la app levanta
> hilos de fondo que comparten la base SQLite en memoria), **no** un problema del
> código. Corriendo **un archivo por proceso** da verde siempre.

Frontend (chequeo de tipos):
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
```

Diagnóstico del pre-run git (no bloquea, solo reporta):
```
GET /api/diag/git/pull-check
```

---

## 7. Garantías de seguridad (qué se endureció)

- **Secretos:** se detectan (PAT de ADO, tokens GitHub/Slack/Google/AWS, claves PEM)
  y la memoria que los contenga queda en **cuarentena**; **nunca** se exporta al repo
  compartido. Es un invariante del camino de exportación, no un "best-effort".
- **PII:** se redacta de forma **irreversible** (`[PII_*]`) antes de persistir,
  exportar o reinyectar. (El enmascarado reversible per-run no se usa para esto.)
- **Roles:** `author_email`/`author_role` son **atribución**, no control de acceso.
  No hay login ni 403; es una herramienta mono-operador.
- **No cuelga:** todo `git` de red corre sin prompts interactivos
  (`GIT_TERMINAL_PROMPT=0`, `credential.helper=` vacío) y con timeout duro.
- **No bloquea:** el pre-run git nace OFF y, si se activa, por default solo
  **advierte** (no bloquea) ante workspace sucio o sin upstream.

---

## 8. Endpoints API de referencia

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/memory?project=&status=` | Listar memorias |
| POST | `/api/memory` | Crear una memoria manual |
| POST | `/api/memory/<id>/status` | Cambiar estado (activar/cuarentena/review) |
| GET | `/api/memory/status?project=` | Conteos por estado |
| POST | `/api/memory/validation/runs` | Lanzar validación (sin `checks` → 4 baratos) |
| GET | `/api/memory/validation/findings?project=` | Hallazgos abiertos |
| POST | `/api/memory/validation/findings/<id>/action` | Curar un hallazgo |
| GET | `/api/memory/conflict-graph?project=` | Grafo de conflictos |
| GET | `/api/memory/sync/status?project=` | Estado de sincronización Git |
| POST | `/api/memory/sync/run` | Disparar sync (necesita `enabled` o el flag) |
| GET | `/api/diag/git/pull-check` | Diagnóstico de frescura del workspace (report-only) |

---

## 9. Preguntas frecuentes

**No veo memorias en la página.**
Normal si no prendiste captura/inyección, o si todavía no aprobaste ningún run.
Ver §4.1.

**Activé el flag y no cambió nada.**
¿Reiniciaste el backend (cambios en `.env`) o reconstruiste el frontend (cambios en
`.env.local`)? Los flags se leen al arrancar.

**El validador no corre el LLM judge.**
Es a propósito: requiere `STACKY_MEMORY_VALIDATOR_ADVANCED=true` (§4.4).

**¿La memoria filtra datos personales del cliente?**
No: se redactan de forma irreversible antes de guardar/exportar/reinyectar, y los
secretos quedan en cuarentena sin exportarse (§7).

**¿Puedo borrar una memoria?**
Sí, cambiando su estado a cuarentena/rechazada desde la UI (botones por fila) o vía
`POST /api/memory/<id>/status`.

---

## 10. Pendientes conocidos (no bloquean el uso local)

Solo relevantes si en el futuro se activa la **sincronización Git colaborativa**
(Fase E, hoy apagada):

- Propagación de **borrados** entre clones (tombstones) aún no se exporta.
- El dedupe de chunks es por `chunk_id` (no `chunk_id+sha256`).
- En el pre-run pull, los runtimes **codex/claude CLI** todavía no inyectan el PAT
  (sí lo hace el runtime copilot); igual no cuelgan porque GCM queda deshabilitado.

Para el uso local (memoria + inyección + validación) **no hay nada pendiente**.
