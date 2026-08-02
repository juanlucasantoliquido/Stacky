# 16 — El sync incremental de GitLab (plan 292)

El sync de GitLab pide **sólo lo que cambió desde la última vez** en vez de traer
el listado completo de issues abiertos en cada corrida.

> Origen: plan 292. Todo lo de acá se midió abriendo el archivo o ejecutando el
> comando; lo que no se puede saber sin consultarle al GitLab del operador está
> marcado como tal y **no** se usa como criterio.

---

## 1. Los dos modos

| Modo | Query emitida | Regla de ausencia | Barrera de admisión |
|---|---|---|---|
| **COMPLETO** | `TrackerQuery(state="open")` — byte-idéntico a antes del plan | **ACTIVA** | no se aplica |
| **INCREMENTAL** | `TrackerQuery(state="all", updated_after=W)` | **APAGADA POR COMPLETO** | **ACTIVA** |

**Por qué `state="all"` y no `state="open"` en el incremental.** Con
`state="open"&updated_after=W`, un issue que se **cerró** después de `W` no viene
en la respuesta —GitLab lo filtra por estado—, así que el incremental sería
incapaz de enterarse de un cierre: ni por presencia ni por ausencia. Con
`state="all"` el issue cerrado **sí** viene, con `"state": "closed"`, y el upsert
lo refleja solo. **El cierre del delta se captura por el estado propio del issue,
no por su ausencia.** Por eso, y sólo por eso, la regla de ausencia puede
apagarse sin perder la detección de cierres recientes.

---

## 2. Las DOS barreras de correctitud

Este cambio es un riesgo de **datos**, no de performance. Invertir la semántica
de la query tiene **dos** consecuencias, no una:

### 2.1. Barrera de LECTURA — la regla de ausencia se apaga

`services/gitlab_sync.py` marca `closed` lo que dejó de venir en el listado. Esa
regla **sólo es correcta si la query trajo todo lo abierto**. En modo parcial la
respuesta no contiene todo lo abierto, así que dejarla viva marcaría `closed`
todo el backlog que no cambió. El daño depende del tamaño del delta:

| Delta que devuelve GitLab | Filas mal cerradas (de 63) |
|---|---|
| vacío | **0** — el `if vistos_external:` preexistente ya corta |
| 1 ítem ya conocido | **62** |
| k ítems ya conocidos | **63 − k** |
| sólo ítems nuevos | **63** — el peor caso |

⚠️ **El delta vacío es el único escenario donde el bug NO puede ocurrir.** Un
gate que use una tanda vacía como caso representativo pasa sin el arreglo puesto,
y su mitad de contraste no puede fallar. El gate del plan usa un delta **parcial
no vacío**, donde el daño existe y está medido.

El módulo lo había anticipado por escrito, años antes, en su propio docstring:
que la query de abiertos y la regla de `removed` **van juntas**.

### 2.2. Barrera de ESCRITURA — `admitir_del_delta`

`state="all"` no sólo **lee** distinto: **escribe filas que hoy no existen**. La
rama de alta del upsert no mira el estado, así que un issue cerrado hace meses al
que alguien le puso un comentario entra en el delta y se **inserta**.

> En modo INCREMENTAL, un ítem del delta puede ACTUALIZAR una fila existente,
> pero sólo puede CREAR una fila si viene `opened`.

| Ítem del delta | Fila local | Qué hace |
|---|---|---|
| `opened` | existe | actualiza |
| `opened` | no existe | **crea** — es un issue nuevo, tiene que entrar |
| `closed` | existe | actualiza ⇒ la fila pasa a `closed` (es la detección de cierre) |
| `closed` | **no existe** | **se SALTEA**, y se cuenta en `omitidos_cerrados_desconocidos` |

**Por qué importa:** nadie borra esas filas nunca (el modo COMPLETO marca cerrado
por ausencia, jamás borra), `list_tickets` no filtra por `ado_state` y ordena por
`last_synced_at DESC` con tope 500 ⇒ cada fantasma va **arriba** del tablero y le
come una posición a un abierto real.

**La barrera vive SÓLO en el bucle del listado, nunca en el traído de padres.** Un
padre cerrado **sí** debe entrar: es la deuda que saldó el plan 277 F6 (una épica
cerrada cuyos hijos quedarían huérfanos).

Es una **función pura** (`admitir_del_delta`) y no un `if` suelto por tres
motivos: se prueba sin base ni proveedor, es el punto de extensión del próximo
tracker, y deja el `if` de producción con un solo símbolo grepeable.

---

## 3. Cuándo se hace COMPLETO

Lo decide `decidir_modo_de_sync`, función pura. Devuelve COMPLETO si **cualquiera**
de estas es cierta; el orden es de **evaluación**, no de prioridad:

| # | Condición | Motivo |
|---|---|---|
| 1 | el llamador lo pidió | `pedido_explicito` |
| 2 | la opción de sincronización parcial está apagada | `opcion_apagada` |
| 3 | no hay marca para este proyecto (primera corrida) | `sin_marca` |
| 4 | la marca es ilegible (JSON roto, no es objeto, fecha inválida, contador no entero) | `marca_ilegible` |
| 5 | la marca es más vieja que 24 h — **o está en el futuro** | `marca_vencida` |
| 6 | el contador de parciales alcanzó la cuota (default 10) | `cuota_cumplida` |

**Consecuencia de diseño, deliberada: COMPLETO es el default de TODOS los caminos
de error.** Perder el archivo, corromperlo, borrarlo a mano, un disco lleno, una
excepción al leerlo — todo termina en COMPLETO, que es el comportamiento previo al
plan. **Nunca en "no sincronizar".** Ninguna condición puede llevar a que el sync
haga menos de lo que hacía antes.

La condición 5 incluye la marca del **futuro** a propósito: una marca posterior a
`ahora` haría que el delta viniera vacío para siempre y el tablero se congelaría
en silencio.

---

## 4. El reloj: el del servidor de GitLab, nunca el de la máquina

La marca es el **máximo `updated_at` de los ítems que GitLab devolvió**, no
`datetime.utcnow()`. Si el reloj del operador adelantara respecto del servidor,
una marca local dejaría fuera del delta siguiente todo lo modificado en la
ventana de desfase, **en silencio y para siempre**.

Tres refuerzos, los tres obligatorios:

- **Solapamiento de 120 s.** Se guarda `max(updated_at) − 120 s`. Cubre (a) el
  issue modificado *durante* el sync, entre la primera página y la última, y (b)
  la duda sobre si `updated_after` de GitLab es inclusivo o exclusivo —que **no se
  puede resolver sin consultar la API del operador**—: con el solapamiento el
  diseño es correcto en los dos casos. El precio es traer de nuevo lo tocado en
  los últimos dos minutos, que es exactamente lo que se quiere.
- **Delta vacío ⇒ la marca NO se toca.** "No cambió nada" no es "avanzá el reloj".
- **La marca es MONÓTONA: nunca retrocede.** En modo COMPLETO los ítems son sólo
  los **abiertos**, así que si el cambio más reciente del proyecto fue sobre un
  **cerrado**, el máximo de esa tanda es **más viejo** que la marca previa.
  Escribirlo haría que la corrida siguiente pidiera una ventana enorme: mataría el
  ahorro justo después de cada corrida de cuota y arrastraría una tanda grande de
  cerrados, componiendo con §2.2. Quedarse atrás sólo cuesta traer de más —el lado
  seguro—; adelantarse pierde ítems en silencio.

**Parseo:** `datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)`.
NO usar `strptime` con `"%Y-%m-%dT%H:%M:%SZ"`: revienta con los milisegundos que
manda GitLab (`.000Z`). Tampoco `.rstrip("Z")`, que descarta la zona en vez de
convertirla.

---

## 5. Dónde vive la marca

Un JSON por proyecto en `data_dir()`, con el molde de
`services/integration_breaker.py`. **No** es una columna de `tickets`: el rebuild
de esa tabla tiene la lista de columnas hardcodeada y borraría la columna nueva en
silencio junto con el dato del operador, y además la granularidad correcta es
**por proyecto**, no por ticket.

⚠️ **`data_dir()` es la misma carpeta donde vive la base del operador.** Todo test
que ejercite el store tiene que redirigir la ruta a un temporal. Además el store
**se niega a escribir bajo `STACKY_TEST_MODE` si la ruta no fue redirigida**: una
suite ajena que ejercite el sync entero no puede dejarle al operador una marca
inventada que suprima su primera corrida completa.

---

## 6. Los tres disparadores, y por qué son asimétricos

| Disparador | Modo | Por qué |
|---|---|---|
| Arranque del proceso | **COMPLETO forzado** | ocurre una vez por proceso, no es polling, y el proceso pudo estar apagado días |
| `POST /sync` (pedido manual del operador) | **COMPLETO forzado** | un pedido explícito trae todo; es la forma que **ya** tiene el operador de forzar una completa, sin agregar un control nuevo |
| `POST /sync-v2` (poll del tablero, cada 45 s) | **parcial** | es el que corre todo el tiempo: es donde está el ahorro |
| Post-completación de una ejecución | **parcial** | sync reactivo y frecuente |

---

## 7. Paridad de los tres runtimes

El sync es **transversal y vive fuera de los runtimes**: `gitlab`,
`sync_gitlab_tickets` y `completion_sync` tienen **0 hits** en
`services/codex_cli_runner.py`, `services/claude_code_cli_runner.py` y
`copilot_bridge.py`. Los tres disparadores son agnósticos al runner, así que el
cambio da paridad **sin tocar ni un runner** y no hace falta ningún fallback.

Esto no se afirma: hay un gate que falla si un runner empezara a nombrar GitLab, y
un censo por **AST** (no por grep) que exige que los llamadores sigan siendo
exactamente esos tres, **por nombre**. El censo acepta la forma por alias
(`gs.sync_gitlab_tickets(...)`), porque un AST que sólo mire `ast.Name` cuenta
**cero** el día que alguien importe el módulo en vez de la función.

---

## 8. Qué NO detecta el incremental

Un issue **borrado** de GitLab (delete real) o movido de proyecto: no viene en el
delta ni deja rastro. Lo captura el modo COMPLETO periódico —la cuota o las 24 h—,
a lo sumo 10 corridas o un día después. Ese es el motivo de existir de la cuota.

---

## 9. Lo que este cambio NO promete

- **No baja requests.** Sobre el proyecto medido hay 1 request de listado hoy y 1
  después: los 63 abiertos entran en una sola página. Lo que baja es **bytes**.
- **El ahorro en bytes es una PROYECCIÓN**, no una medición: el byte real depende
  del servidor y no se puede medir sin consultarlo. Por eso el sync reporta
  `bytes_recibidos` en su dict de retorno y en su log — el operador ve la **serie**
  del ahorro en su propia corrida, sin que nadie le pregunte nada a GitLab. Mide
  carga **serializada**, no bytes de cable (no incluye compresión ni cabeceras).
- **No mejora la frescura.** El disparador periódico ya existía en el navegador.
  Un daemon de backend quedó **fuera de scope**: sólo agregaría corridas cuando
  nadie está mirando, y el propio `app.py` prohíbe por escrito agregar threads
  nuevos (el camino correcto sería registrar una tarea en el loop único de
  mantenimiento).

**Recomendación independiente, fuera de este plan:** subir el intervalo del poll
del tablero de 45 s a 180 s baja el 75 % del tráfico con **una línea** y cero
riesgo de correctitud. Es más barato que todo esto junto y conviene saberlo.

---

## 10. Rollback

Apagar la opción de sincronización parcial deja el sync **byte-idéntico** al
anterior al plan: query de abiertos y regla de ausencia activa. No hay migración
que revertir; el JSON de la marca queda inerte y se ignora.
