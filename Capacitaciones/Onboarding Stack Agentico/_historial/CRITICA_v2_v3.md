# Crítica v2 → v3 — Guion Sesión IA 05/08/2026

**Objeto:** estado intermedio v2 (v1 + las 11 correcciones de `CRITICA_v1_v2.md`).
**Enfoque de esta pasada:** los defectos **introducidos por las propias correcciones** de v1→v2. Una segunda crítica que solo repite la primera no sirve para nada.
**Veredicto: RECHAZADO.** 2 bloqueantes · 3 importantes · 3 menores.

---

## Bloqueantes

### D1 — La corrección C1 reintrodujo el defecto C2 por otra puerta
Para arreglar "faltan ejemplos humanos" (C1) se metió una tabla de **16 equivalencias**. Para arreglar "25 términos son demasiados" (C2) se recortó el diccionario a 14.

Resultado neto: la sala escucha **16 filas de tabla en vez de 25 definiciones**. No mejoró: cambió de formato.

Una tabla es un objeto **para leer**, no para escuchar. Leída en voz alta fila por fila es exactamente el mismo muro, con la agravante de que ahora hay una diapositiva llena de texto que la gente va a leer mientras el expositor habla — y perdés las dos cosas.

**Corrección:**
- La tabla de 16 se mantiene, pero **solo en la chuleta impresa**.
- Hablado, se cuenta como **una historia con 6 momentos** — el primer día del fichaje, hora por hora — y cada momento deja caer 2 o 3 conceptos naturalmente, sin nombrarlos como lista.
- En pantalla, durante ese bloque: **un dibujo por momento**, no la tabla.

---

### D2 — Los ejemplos humanos quedaron como decoración: no cierran en acción
Los ejemplos de v2 explican bien **qué es** cada cosa. Ninguno dice **qué hace el oyente con eso el lunes**.

Un asistente no técnico sale entendiendo qué es una skill y sin la menor idea de por qué debería importarle. Y entender sin poder usar se olvida en 48 horas — que es exactamente el fracaso que el propio guion denuncia en el bloque 2 ("si no obtiene algo útil en su primera sesión, no hay segunda sesión").

**Corrección:** cada concepto del bloque narrativo cierra con una línea marcada **`→ Para qué te sirve:`**, con una acción concreta y hacible esta semana. Sin excepción. Si un concepto no tiene acción asociada, no entra al guion hablado: se va a la chuleta.

---

## Importantes

### D3 — El hilo conductor tiene un punto ciego peligroso y v2 no lo marca
"Contratamos a alguien nuevo" funciona para 14 de los 16 conceptos. **Falla justo en el más importante: la alucinación.**

Un fichaje humano, cuando no sabe algo, **dice que no lo sabe**. O se le nota. Si la analogía se deja correr sin avisar, la sala sale con un modelo mental antropomórfico —"es como un compañero nuevo"— y ese modelo hace exactamente el daño que la charla quiere evitar: **te lleva a confiar por defecto**.

Es un defecto introducido por C6: al unificar el ejemplo, se ganó claridad y se perdió la advertencia.

**Corrección:** una parada explícita, con su propia diapositiva, titulada **"Dónde se rompe la comparación"**. Tres roturas: no dice "no lo sé", no aprende de lo que le corregís, y no tiene ni idea de si lo que dice es verdad. Va **inmediatamente después** del bloque narrativo, en el pico de simpatía de la analogía. Ahí es donde pega.

---

### D4 — El recorte de C2 tiró por la borda `grounding`, que es el eje del bloque 2
Al recortar de 25 a 14 conceptos, `RAG` y `grounding` se fueron a la chuleta.

Pero el bloque 2 entero descansa sobre grounding: el manual agéntico, el catálogo de procesos, el fallo del punto de entrada, la evidencia obligatoria con archivo y línea. Si el término no se explicó antes, el caso se cuenta con una palabra que la sala no tiene.

Es un defecto de **coherencia entre bloques** que solo aparece al releer los dos juntos.

**Corrección:** `grounding` vuelve al guion hablado con su ejemplo humano *(«no me lo digas de memoria, enséñame dónde lo pone»)*, y se marca en voz alta como **el concepto que hay que retener para la segunda parte**. `RAG` se queda como el caso particular más común de grounding, en una sola frase.

---

### D5 — No hay ningún chequeo de comprensión y la sala es mixta
En una sala mixta, **el no técnico que se perdió no levanta la mano**: se queda callado y desconecta. Y desde el atril no se nota, porque el técnico de la primera fila asiente.

v1 y v2 dicen "si algo no se entiende, me frenan". Eso no funciona: transfiere al oyente el coste social de interrumpir.

**Corrección:** una parada de 60 segundos a los ~12 minutos, con una pregunta cerrada y de bajo riesgo social — *"¿qué significa que la IA 'no busca, predice'?"* — pedida a la sala en general. Si nadie contesta o contestan mal, se repite el concepto y **se sigue igual**: la parada tiene tiempo asignado y no se negocia.

---

## Menores

### D6 — La chuleta creada en v2 no tiene momento de reparto
Si se reparte al principio, la gente **lee en vez de escuchar** y perdés la charla. Si se reparte al final, la mitad ya se fue.

**Corrección:** se reparte boca abajo al entrar, con la consigna explícita de darla vuelta al final; y se anuncia en el minuto 1 (*"no tomen notas, todo esto se lo llevan en papel"*), que además libera atención durante los 45 minutos.

---

### D7 — El cierre no dice qué hace cada perfil el lunes
El cierre de v2 es conceptual (tres frases). Cierra bien la charla y **no mueve a nadie**.

**Corrección:** cierre segmentado en dos: una acción concreta para quien escribe código y otra para quien no. Dos frases, no un plan.

---

### D8 — El anexo de preguntas no cubre la más probable del perfil no técnico
Están cubiertas: sustitución, error en producción, coste, datos, por dónde empiezo, qué modelo, cuánto llevó. Falta la que más se va a oír en una sala mixta: **"¿y yo, que no programo, esto para qué lo uso?"**.

**Corrección:** se añade, con respuesta concreta y sin condescendencia.

---

## Resumen de cambios aplicados en v3

| # | Cambio |
|---|---|
| D1 | La tabla de 16 sale del guion hablado; se cuenta como historia en 6 momentos. La tabla vive en la chuleta |
| D2 | Cada concepto cierra con `→ Para qué te sirve:` y una acción de esta semana |
| D3 | Nueva sección con diapositiva propia: *"Dónde se rompe la comparación"* |
| D4 | `grounding` vuelve al guion hablado y se marca como puente al bloque 2 |
| D5 | Parada de comprensión de 60 s en el minuto 12, con tiempo presupuestado |
| D6 | Protocolo de reparto de la chuleta, anunciado en el minuto 1 |
| D7 | Cierre segmentado: una acción para quien programa, otra para quien no |
| D8 | Nueva pregunta preparada en el anexo |

**Estado tras aplicar: v3 — APTA PARA ENSAYO.**
Pendiente que solo puede cerrar el operador: los datos marcados `[COMPLETAR]` en el bloque 2 (estado actual del batch, coste real, tiempo de montaje).
