# 17 — El tablero de trabajo: publicar sin terminal (plan 293)

Una pantalla para que **cualquier persona pueda guardar y publicar su trabajo sin
saber Git y sin abrir una consola**: ver qué cambió, elegir qué guardar, traer lo
de sus compañeros, enviarlo al servidor y pedir que se lo revisen.

> Esta página está escrita para **quien la usa**, no para quien la programó.
> Si algo tiene un nombre técnico, acá está el nombre común.
>
> Origen: plan 293. Todo lo de acá se midió abriendo el archivo o ejecutando el
> comando. Lo que no se puede saber sin credenciales reales está marcado como
> **[NV]** y no se usa como criterio.

---

## 1. Cómo se abre

En la barra de la izquierda, grupo **Trabajo** → **"Publicar mi trabajo"**.

También podés llegar de dos formas más:
- escribiendo la dirección `/publicar` directamente;
- con **Ctrl+K** (la paleta de comandos) → *"Ir a Publicar mi trabajo"*.

**Viene visible de fábrica**: la opción que la muestra nace encendida porque el
tablero, por sí solo, **sólo mira**. No modifica ni un archivo.
[V: `config.py` `STACKY_WORKBENCH_ENABLED` default `"true"`]

---

## 2. Qué ves cuando la abrís

| Zona | Qué muestra |
|---|---|
| Encabezado | En qué **versión de trabajo** estás y cuántos archivos tienen cambios sin guardar |
| Avisos | Los problemas que impiden avanzar, **en el primer paso y no al final** |
| Los cuatro pasos | *Mirá qué cambió · Elegí qué guardar · Contá qué hiciste · Confirmá* |
| Tus archivos | Agrupados en **En conflicto**, Modificados, Nuevos, Borrados, Renombrados, Sin seguimiento y Otros |
| "Ver qué cambió" | Abre las diferencias de ese archivo, con las contraseñas tapadas |
| **No se van a incluir** | La lista, **por nombre**, de lo que queda afuera del guardado |
| Lo que se guardó antes | Los últimos movimientos, con quién los hizo |

**"En conflicto" va siempre primero**, porque es lo urgente: son archivos que vos
y otra persona cambiaron a la vez y hay que decidir cuál versión queda. Mientras
haya conflictos **no se puede guardar nada**, y el tablero lo dice.

> **Por qué existe la lista "No se van a incluir".** En una misma carpeta puede
> haber trabajo de otras personas o de otras tareas. El tablero guarda
> **exactamente** los archivos que tildaste y **deja el resto intacto** — pero
> además te los muestra, para que veas que existen y que no se tocan.

---

## 3. Qué está apagado de fábrica y qué lo enciende

El tablero tiene **tres anillos**. El primero viene encendido; los otros dos no,
y es a propósito.

| Anillo | Qué habilita | Opción | De fábrica |
|---|---|---|---|
| **1 — Mirar** | Ver el estado, las diferencias, el historial y las versiones de trabajo | **"Tablero de trabajo"** (`STACKY_WORKBENCH_ENABLED`) | **Encendida** |
| **2 — Guardar y traer** | Guardar los archivos elegidos, traer novedades, cambiar de versión de trabajo | **"Dejar que el tablero guarde cambios en tu carpeta"** (`STACKY_WORKBENCH_WRITE_ENABLED`) | **Apagada** |
| **3 — Enviar y pedir revisión** | Enviar al servidor y abrir el pedido de revisión | **"Dejar que el tablero envíe tu trabajo al servidor"** (`STACKY_WORKBENCH_PUSH_ENABLED`) | **Apagada** |

**Dónde se encienden:** panel de opciones → categoría **"Capacidades opt-in"**.
El cambio **aplica en caliente**: no hay que reiniciar nada.

**Con los dos anillos apagados, el tablero se ve entero y no puede tocar nada**:
los botones aparecen deshabilitados y, al pasar el mouse, dicen exactamente qué
opción encender.

> **Por qué guardar y enviar están separados.** Guardar ocurre **dentro de tu
> máquina** y sólo lo ves vos. Enviar **sale de tu computadora y lo ve todo el
> equipo**. Son dos niveles de compromiso distintos, así que son dos permisos
> distintos.

---

## 4. Adjuntar capturas como evidencia

En el paso *"Contá qué hiciste"*, debajo de *"Qué probaste"*, hay una zona para
adjuntar **capturas de pantalla o PDF**. Sirven para que quien revise vea que lo
que hiciste funciona.

**Lo que ves, paso a paso:**
1. Elegís uno o varios archivos.
2. Aparecen como **miniaturas** con su nombre debajo. Un PDF muestra un recuadro
   con la palabra "PDF". **Eso es la previsualización, y ocurre antes de crear
   nada.**
3. Si alguna no entra, sale el bloque **"No se pudieron adjuntar (N)"** con el
   nombre y el motivo en castellano. **Las demás sí se adjuntan**: una captura
   mala no tira abajo a las buenas.
4. Al tocar **"Pedir que lo revisen"**, las capturas se suben y quedan **dentro
   del pedido de revisión**, en una sección "Evidencia adjunta".

**Qué se acepta:** imágenes (PNG, JPG, GIF, BMP, WEBP) y PDF. Hasta **10
archivos**, **10 MB** cada uno y **25 MB** en total.

> **Se mira el contenido, no el nombre.** Un archivo llamado `captura.png` que en
> realidad sea otra cosa **se rechaza**. La extensión la elige quien sube el
> archivo, así que no sirve para decidir si es seguro.

### 4.1. Qué pasa en Azure DevOps — **importante**

| Servidor | Qué pasa con las capturas |
|---|---|
| **GitLab** | Se **muestran dentro** del pedido de revisión, como imágenes |
| **Azure DevOps** | **No se pueden mostrar embebidas.** Las capturas quedan **guardadas en Stacky** y el pedido de revisión se crea igual |

Esto **no es una falla**: es un límite de Azure DevOps, que sólo sabe adjuntar
archivos a un *elemento de trabajo* y no a un pedido de revisión. El tablero lo
**declara** en pantalla en vez de fallar.

---

## 5. Lo que el tablero NO puede hacer, y por qué

| No puede | Por qué |
|---|---|
| **Deshacer** lo que guardaste | Deshacer, en el fondo, es borrar historia. Sobre una carpeta que puede tener trabajo de otras personas, eso es destructivo y no se ofrece **ni con la opción encendida** |
| **Borrar** una versión de trabajo | Mismo motivo |
| **Pisar** el trabajo del servidor | Si alguien subió algo antes que vos, el envío se **rechaza** y el tablero te dice que traigas los cambios primero. Nunca fuerza |
| **Elegir una carpeta entera** | Una carpeta arrastraría también cambios que no son tuyos. Se eligen archivos, uno por uno |
| Mostrar comentarios y aprobaciones de un pedido de revisión | Todavía no existe esa lectura en Stacky. Se ven en GitLab o Azure DevOps |

---

## 6. Si algo sale mal

**Ningún mensaje técnico llega en crudo.** Cada error se traduce a tres partes:
qué pasó, qué significa y **qué hacer ahora**. Por ejemplo:

- *"Alguien subió cambios antes que vos"* → **no se perdió nada**; tocá "Traer
  cambios" y volvé a enviar.
- *"La carpeta está ocupada"* → otro programa la está usando; esperá unos
  segundos.
- *"Quedó algo a medio terminar"* → una operación anterior no se completó; hay
  que cerrarla antes de guardar. **Tu trabajo no se pierde.**
- *"Tenés cambios sin guardar"* → cambiar de versión de trabajo ahora los
  perdería, así que **no se hizo nada**.

---

## 7. Decisiones que quedan para el operador

Todas están implementadas con el valor **más conservador**; cambiarlas es
decisión suya.

| # | Decisión | Valor actual y por qué |
|---|---|---|
| **D9** | **Dónde viven las capturas** | En el área de datos de Stacky, **nunca dentro de la carpeta de trabajo**. Adentro aparecerían como cambios sin guardar y le ensuciarían el propio tablero al usuario |
| **D10** | **Por cuánto tiempo se guardan** | **No se borran solas.** Borrar datos del operador sin que lo pida va contra el riel de la casa. Si se acumulan, la limpieza es manual |
| **D11** | **Cuánto se puede adjuntar** | 10 archivos · 10 MB cada uno · 25 MB en total — los mismos topes ya probados del buzón de incidencias |
| **D12** | **Qué formatos se aceptan** | Imágenes y PDF, **verificados por su contenido real** |
| **D8** | **No hay "deshacer"** | Ver §5. Si se quisiera, lo único admisible sería una operación que **crea** un movimiento nuevo en vez de borrar, y es otro plan |
| **D2** | **Git local, no la API del servidor** | Decisión tomada: todo pasa en la máquina del usuario salvo el pedido de revisión, que no tiene equivalente local |

---

## 8. Lo que todavía no se probó **[NV]**

El ciclo completo **contra un GitLab o un Azure DevOps reales nunca se ejecutó**:
todas las pruebas corren contra dobles y contra repositorios de prueba creados al
momento. La verificación de punta a punta requiere credenciales y es **trabajo
del operador**: encender los anillos 2 y 3, guardar un archivo, enviarlo, y
comprobar que el pedido de revisión aparece con su descripción, sus pruebas y sus
capturas — y que **no** quedó aprobado ni integrado solo.

Tampoco se abrió la pantalla en un navegador: está verificada por compilación y
por sus pruebas, pero **nadie la vio dibujada**.
