# Stacky Agents — Plan de Adopción para Devs (Contribución)

> **Complemento de `PRODUCCION_PLAN.md`.**
> Aquel cubre lo *bloqueante* (seguridad, empaquetado, CI). Este cubre lo que
> hace falta para que, una vez instalado, **el dev no pueda dejar de usarlo**.
>
> Objetivo: que abrir Stacky sea más rápido y satisfactorio que abrir VS Code en frío.
> Intuitivo, rápido, *game changer*, adictivo — y profesional.

---

## Diagnóstico honesto

Stacky Agents tiene **52 moats**, multi-tracker, packs, VS Code bridge, SSE,
extensión, observabilidad… y aún así un dev nuevo puede abrirlo y **no entender
qué hacer en los primeros 3 minutos**. El problema no es funcionalidad: es
**fricción de adopción**.

Lo que falta no es código de features — es **diseño del primer día**, **rituales
de uso diario** y **señales de victoria** que hagan que el dev vuelva mañana sin
que nadie se lo recuerde.

---

## Pilar 1 — Primer-Wow en 5 minutos (onboarding obligatorio)

**Hipótesis:** si un dev no obtiene un output útil en su *primera* sesión, no
hay segunda. Hoy depende de leer el README.

### C1. **Tour interactivo "Tu primer ticket"** (15 pasos, skippable)
- Overlay con `react-joyride` o tooltips propios sobre la Team Screen ya existente.
- Detecta `first_run == true` en `preferences.json` y lanza solo.
- Cierra con un *commit real* (ticket sandbox pre-cargado) y un toast:
  *"Tu primer agente corrió en 4'12''. Bienvenido."*
- Métrica: `time_to_first_useful_output` (TTFUO) en `system_logs`.
  Target: **< 5 min** p90.

### C2. **Sandbox de ticket falso**
- Backend siembra al primer arranque un proyecto `__demo__` con 3 tickets
  ficticios (Business → Functional → Developer → QA) ya armados.
- El dev puede tocar todo sin miedo a romper ADO real.
- Botón **"Ocultar demo"** una vez que conectó su primer tracker real.

### C3. **Health-check visual antes del primer click**
- Ya hay `tmp_diag.py` y `/diagnostics` proyectado en `PRODUCCION_PLAN.md` §13.
- Acá lo subo a **bloqueante de UX**: si algo rojo, la Team Screen muestra
  un banner *amigable* con un solo botón **"Arreglar esto"** que dispara
  acciones (re-login ADO, instalar `.vsix`, abrir puerto). No "ver logs".

---

## Pilar 2 — Intuición (zero-curve, todo descubrible)

### C4. **Command Palette global (`Ctrl+K`)**
- Estilo Linear / Raycast. Una sola tecla y podés:
  - lanzar cualquier agente,
  - saltar a un ticket por código (`T-170`),
  - cambiar de proyecto,
  - abrir el último output,
  - ejecutar un pack,
  - abrir `/diagnostics`.
- Implementación: `cmdk` (npm) + indexado en memoria de `agents`, `tickets`,
  `packs`, `projects`, `executions`.
- Atajos memorables: `?` muestra todos, `g t` go-to-ticket, `g a` go-to-agent.

### C5. **Empty states que enseñan, no que reprochan**
- Cada vista vacía actual ("No hay ejecuciones") se reemplaza por una tarjeta con:
  - ilustración pixel-art reutilizando `avatarGallery` (consistencia visual),
  - 1 frase explicando *qué pasa acá*,
  - 1 botón que ejecuta la acción típica.
- Componente nuevo: `<EmptyState variant="executions|tickets|packs|docs" />`.

### C6. **Inline "Why this output?"**
- En cada `OutputPanel`, un botón discreto **"Cómo se construyó esto"** abre un
  drawer con: prompt final usado, fuentes (FA-01 cross-ticket, FA-15 glossary,
  FA-05 git context), modelo, tokens, costo, confidence (FA-35).
- Convierte el agente de *caja negra* a *aprendizaje*. Es el rasgo más citado
  por usuarios power de Cursor/Copilot.

### C7. **Atajos contextuales tipo IDE**
- `Enter` corre, `Shift+Enter` corre con edición de prompt, `Ctrl+R` re-ejecuta,
  `Ctrl+Shift+R` re-ejecuta como otro agente, `Ctrl+/` toggle Workbench↔Team.
- Mostrar pista al hover sobre cada botón (`title=` + `kbd` chip visual).

---

## Pilar 3 — Game Changer (las cosas que harán que un dev recomiende esto)

### C8. **"Continuar donde lo dejé" persistente**
- Al reabrir la app, en lugar de Team Screen pelada: card grande
  *"Volver al ticket T-172 — Developer corrió hace 12 min, falta QA"*.
- Backend: `GET /api/session/resume` devuelve el último ticket + agente + estado
  del Workbench. Frontend: hidrata `store/workbench.ts` automáticamente.

### C9. **Agente "Explain my repo"** (nuevo, no en los 52 moats actuales)
- Toma `workspace_root` + `git log` + `FA-15 glossary` y produce un **mapa
  mental** del repo en Mermaid (FA-21 ya renderea).
- Output: dependencias entre módulos, propietarios por `git blame` agregado,
  archivos "hot" (más cambios últimos 30 días), tests con menor coverage.
- *Game changer*: el dev nuevo entiende el repo en 30s sin leer ningún README.

### C10. **"Asignación inversa": el ticket viene a vos**
- Notificación nativa de Windows (`win10toast`) cuando un ticket en ADO cambia a
  un estado donde tu rol-favorito (configurado en `preferences.json`) aplica.
- Click → abre Team Screen ya posicionada en ese ticket.
- Backend: extender `services/ado_sync.py` con webhook *outbound* a localhost.

### C11. **Replay de ejecuciones (timeline)**
- Cada ejecución guarda `events.jsonl` (ya hay `system_logs`).
- Botón **▶ Replay** que reproduce paso a paso: tokens streamed, herramientas
  invocadas, archivos tocados — como un "video" del agente trabajando.
- Para revisión, para enseñar a un junior, para defender ante un PR review.

### C12. **Comparador A/B de outputs (FA-49 visible)**
- `Parallel exploration` ya existe en backend. Falta UI: dos columnas lado a
  lado con highlight de diferencias (diff-match-patch).
- Selector **"Quedarme con éste"** que marca el ganador y entrena `FA-12
  best-output few-shot` automáticamente.

---

## Pilar 4 — Adicción saludable (loops dopamínicos profesionales)

> Adictivo no significa gamificado infantil. Significa **señales claras de
> progreso** que el dev valora.

### C13. **Streak de tickets cerrados con asistencia de agentes**
- Contador discreto en la barra superior: *"🔥 5 días seguidos cerrando tickets
  con agentes."* Reset si pasa 1 día sin cerrar nada.
- Sin badges infantiles. Tipografía monoespaciada, sobrio.

### C14. **"Tiempo ahorrado" calculado, no inventado**
- Para cada ticket cerrado vía pack: comparar duración real vs **baseline**
  (mediana histórica del mismo tipo de ticket sin agentes, leída de ADO).
- Mostrar en una tarjeta semanal: *"Esta semana ahorraste 4h 12m respecto a tu
  media de 2025-Q4."*
- Métrica honesta. Si el agente fue más lento, lo dice.

### C15. **Daily standup auto-generado**
- Cada mañana a las 09:00 (configurable), Stacky abre un modal con:
  - tickets en los que avanzaste ayer,
  - bloqueos detectados (QA FAIL, tests rotos, comments sin responder),
  - sugerencias del agente **PM Intelligence** (ya existe, ver `11_PM_INTELLIGENCE_SUITE.md`).
- Botón "Copiar a Teams/Slack" → te pasa el texto listo. Eso convierte a Stacky
  en parte del ritual de la mañana, no una herramienta opcional.

### C16. **Notificación de "agente terminó"**
- Hoy hay que mirar la pantalla. Agregar:
  - sonido sutil (toggle off por defecto, opt-in en preferences),
  - flash del icono de la taskbar,
  - badge en la extensión VS Code (`statusBarItem` con count).
- *Adictivo* porque permite hacer otra cosa mientras corre y volver justo a
  tiempo.

---

## Pilar 5 — Profesional (que el tech lead lo apruebe sin dudar)

### C17. **Modo "auditoría legible"**
- En cualquier ejecución: botón **Exportar a PDF** con header (proyecto,
  ticket, agente, modelo, timestamp, HMAC chain de FA-39), body (prompt +
  output formateado), footer con citaciones (FA-20).
- Esto convierte un output de agente en **evidencia adjuntable a un PR o a un
  ticket de auditoría interno**.

### C18. **Política de costo visible y *configurable* por proyecto**
- FA-33 (cost preview) existe. Falta hacerlo **gobernable**:
  - cap mensual por proyecto en USD,
  - alerta visual al 80% del cap,
  - bloqueo opcional al 100% (override con motivo).
- Configurable desde el modal de proyecto (extender el de `PRODUCCION_PLAN.md` §4).

### C19. **"Why not me?" — explicabilidad de routing**
- FA-04 multi-LLM routing decide qué modelo usar. Hoy es opaco.
- Mostrar al lado del output: *"Se usó Sonnet 4.6 porque: ticket type=bug,
  context size=3.4k tokens, drift score=low. Costo estimado: $0.04."*
- Profesional = explicable.

### C20. **Modo "read-only safe demo"**
- Toggle en navbar: **Modo Demo**. En ese modo:
  - los agentes corren contra fixtures locales, nunca llaman al LLM real,
  - los outputs son los últimos cacheados (FA-31),
  - el badge "DEMO" aparece en todos los outputs.
- Sirve para reuniones con cliente, training y demos sin riesgo de filtrar info.

---

## Pilar 6 — Métricas que validan que esto funciona

Sin medición no hay adopción real. Agregar en `services/stacky_logger.py`:

| Métrica | Cómo se calcula | Target |
|---|---|---|
| **TTFUO** (Time-To-First-Useful-Output) | timestamp del primer `output.accepted=true` − primer login | < 5 min p90 |
| **DAU/MAU** | usuarios únicos diarios / mensuales | > 0.5 |
| **Agent-assisted close rate** | tickets cerrados con ≥1 ejecución vinculada / total | > 60% en 60 días |
| **Re-run rate** | re-runs / runs totales por agente | indica calidad del prompt: bajar |
| **Cost per closed ticket** | suma costos LLM / tickets cerrados con asistencia | tendencia ↓ mes a mes |
| **NPS interno** | encuesta in-app trimestral (1 pregunta) | > 40 |

Dashboard `/admin/adoption` que solo ve el tech lead (gate por rol en
`preferences.json:role`).

---

## Pilar 7 — Lo que NO hay que hacer

- ❌ **No agregar otro moat**. Hay 52. La marginal de un FA-53 hoy es **negativa**:
  más superficie, menos foco. El usuario no pidió más features — pidió usar las
  que ya hay sin sufrir.
- ❌ **No gamificar con puntos o niveles**. Esto es para devs profesionales,
  no para una app de fitness. Streaks discretos sí; XP no.
- ❌ **No hacer un "modo experto" oculto**. Todo descubrible vía `Ctrl+K`.
- ❌ **No mover Stacky a la nube todavía**. La promesa de "corre en tu máquina"
  es parte del *trust*. Cloud es otro producto, otra conversación.

---

## Roadmap de ejecución sugerido

Las contribuciones se ordenan por **ROI de adopción / esfuerzo**, no por
dependencia técnica.

### Sprint 1 (2 semanas) — *Hacer que entren*
- C1 Tour interactivo
- C2 Sandbox demo
- C5 Empty states
- C16 Notificación de fin de ejecución

> Resultado esperado: TTFUO baja a < 5 min, DAU sube +30%.

### Sprint 2 (2 semanas) — *Hacer que vuelvan*
- C4 Command Palette
- C8 "Continuar donde lo dejé"
- C13 Streak
- C15 Daily standup

> Resultado esperado: retención D7 sube de ~20% (estimado) a > 50%.

### Sprint 3 (3 semanas) — *Hacer que recomienden*
- C9 Agente "Explain my repo"
- C11 Replay
- C12 Comparador A/B (UI sobre FA-49)
- C14 Tiempo ahorrado

> Resultado esperado: NPS interno > 40, primer "tráelo a mi equipo" orgánico.

### Sprint 4 (2 semanas) — *Hacer que el lead lo bendiga*
- C17 Auditoría PDF
- C18 Cost cap
- C19 Why-this-model
- C20 Demo mode
- Pilar 6 dashboard

> Resultado esperado: aprobación formal de tech-leads para uso obligatorio en
> tickets ≥ M.

Sprints 1–2 se pueden empezar en paralelo a las fases 1–3 de
`PRODUCCION_PLAN.md` (tocan archivos distintos: aquel toca empaquetado, este
toca UI y `frontend/src/pages/*`).

---

## Mapeo a archivos concretos

| Contribución | Archivos a tocar / crear |
|---|---|
| C1 Tour | `frontend/src/components/OnboardingTour.tsx` (nuevo), gate en `pages/TeamScreen.tsx` |
| C2 Sandbox | `backend/services/demo_seed.py` (nuevo), invocado en `app.py` al arrancar si DB vacía |
| C3 Health-check banner | `frontend/src/components/HealthBanner.tsx` (nuevo), consume `/api/diagnostics` |
| C4 Command Palette | `frontend/src/components/CommandPalette.tsx` (nuevo) + hook global en `App.tsx` |
| C5 Empty states | `frontend/src/components/EmptyState.tsx` (nuevo) + replace en cada page |
| C6 "Why this output" | extender `OutputPanel.tsx`, nuevo endpoint `GET /api/executions/:id/provenance` |
| C7 Atajos | hook `useKeyboardShortcuts.ts` (nuevo), tooltips en botones existentes |
| C8 Resume | `GET /api/session/resume` en `api/executions.py`, hidratar `store/workbench.ts` |
| C9 Explain repo | `backend/agents/explain_repo.py` (nuevo), reusa `services/git.py` + `FA-15` |
| C10 Notif inversa | extender `services/ado_sync.py`, nuevo `services/desktop_notifier.py` (`win10toast`) |
| C11 Replay | persistir `events.jsonl` por execution, nuevo `frontend/src/components/ReplayPlayer.tsx` |
| C12 A/B UI | `frontend/src/components/ABCompare.tsx` (nuevo), reusa endpoints FA-49 |
| C13 Streak | columna `last_close_at` en `users`, componente `<StreakBadge />` |
| C14 Tiempo ahorrado | `backend/services/savings_calculator.py` (nuevo), nuevo endpoint `GET /api/savings/weekly` |
| C15 Daily standup | reusa `11_PM_INTELLIGENCE_SUITE.md`, nuevo `DailyStandupModal.tsx` con cron en frontend |
| C16 Notif fin | `services/desktop_notifier.py` (compartido con C10) |
| C17 PDF | `backend/services/pdf_export.py` (nuevo, `reportlab` o `weasyprint`) |
| C18 Cost cap | extender modal de proyecto (PRODUCCION_PLAN §4), columna `monthly_cap_usd` en `projects` |
| C19 Why-this-model | extender respuesta de `agent_runner.py` con `routing_decision`, mostrar en `OutputPanel` |
| C20 Demo mode | flag global `DEMO_MODE` en `store/preferences.ts`, intercepta `api/client.ts` |

---

## Cierre

La diferencia entre *un dashboard interno más que nadie usa* y *la herramienta
que el dev abre antes que VS Code* no son features. Son:

1. **el primer minuto** (Pilar 1),
2. **la fluidez de los próximos 100 usos** (Pilares 2, 4),
3. **una historia que se pueda contar al lead** (Pilar 5),
4. **una métrica que pruebe que pasó** (Pilar 6).

Con `PRODUCCION_PLAN.md` el producto se puede *instalar*. Con este plan, además,
se *usa*.
