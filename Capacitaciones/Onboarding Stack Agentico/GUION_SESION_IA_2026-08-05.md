# Guion — Sesión de IA · Reunión presencial de equipo

**Versión:** v3 (tras dos rondas de crítica — ver `_historial/`)
**Fecha:** miércoles 05/08/2026 · **Expositor:** Juan Luca Santoliquido
**Bloque 1:** Conceptos básicos de IA — 45 min
**Bloque 2:** Caso de éxito Tech (flujo agéntico RS + Pacífico) — 20 min
**Audiencia:** mixta técnica / no técnica. **Supuesto de trabajo: nadie sabe nada de IA.**

---

## Cómo usar este documento

- **[DIGO]** — lo que decís, en lenguaje hablado. No es para leer palabra por palabra. Es el orden y el tono.
- **[PANTALLA]** — qué se ve mientras hablás.
- **[NOTA]** — recordatorio para vos. No se dice.
- **⏱** — reloj acumulado. Si te pasás, mirá el *Plan B de recortes* al final.
- **`→ Para qué te sirve:`** — la frase que convierte el concepto en algo usable. **No la saltees nunca.** Es lo único que la gente se lleva.

**Presupuesto real:** 40 minutos de contenido en el bloque de 45. 18 en el de 20. El colchón es parte del guion, no un accidente.

**Regla del día:** la palabra que no se entiende arruina todo lo que viene después. Mejor cinco conceptos entendidos que veinte oídos.

---
---

# BLOQUE 1 — CONCEPTOS BÁSICOS DE IA (45 min)

## 0. Apertura — 3 min · ⏱ 0:00 → 0:03

**[NOTA]** La chuleta se reparte **boca abajo** mientras entra la gente. Se anuncia en el minuto 1 y no se toca hasta el final.

**[PANTALLA]** Solo el título: *"IA: de qué estamos hablando realmente"*.

**[DIGO]**

> Antes de empezar, dos cosas.
>
> La primera: tienen un papel boca abajo delante. No lo den vuelta todavía. Es un resumen de todo lo que voy a contar. **No hace falta que tomen notas.** Todo lo que diga hoy está en ese papel.
>
> La segunda: una pregunta a mano alzada. ¿A quién le pasó alguna vez que le preguntó algo a ChatGPT, la respuesta sonaba **perfecta**, y después resultó que estaba mal?
>
> *(esperar — normalmente levantan la mano casi todos, y con una sonrisa)*
>
> Bien. Esa cara que están poniendo es de lo que vamos a hablar hoy.
>
> Les hago un contrato para estos 45 minutos. **No los voy a convertir en expertos.** No se puede y no hace falta. Quiero que salgan de acá con tres cosas:
>
> **Una.** Que entiendan todas las palabras cuando alguien hable de IA. Que nadie diga "agente" o "skill" y ustedes tengan que asentir sin saber.
>
> **Dos.** Que sepan elegir la herramienta correcta. Hoy hay veinte. Usar la equivocada es la forma más rápida de concluir que esto no sirve.
>
> **Tres.** Que sepan cuándo desconfiar. Esta es la importante.
>
> Voy a explicar todo desde cero. Si a alguien le parece básico, que aguante diez minutos. Después subimos.

**[NOTA]** Si la sala está fría y nadie levanta la mano, no insistas. Decí *"por las caras, veo que a varios sí"* y seguí. No pierdas 40 segundos.

---

## 1. ¿Qué es "la IA"? — 4 min · ⏱ 0:03 → 0:07

**[PANTALLA]** Círculos concéntricos: **IA ⊃ Machine Learning ⊃ IA Generativa ⊃ LLM**

**[DIGO]**

> Cuando alguien dice "IA" hoy, casi siempre habla de una cosa muy concreta. Pero el término es enorme. Vamos de afuera hacia adentro.
>
> **Inteligencia Artificial** es el círculo grande. Es un campo académico con setenta años. Es de los años cincuenta.
> La definición es simple: que una máquina haga algo que, si lo hiciera una persona, diríamos que requiere inteligencia.
> El corrector del Word es IA. El GPS que te calcula la ruta es IA. El filtro de spam es IA. Nada de eso es nuevo.
>
> Adentro está el **Machine Learning**. Y acá hay un cambio de mentalidad importante.
> Programar de toda la vida es: yo escribo las reglas, la máquina las ejecuta. *"Si el importe pasa de mil euros, pedí autorización."* Esa regla la escribí yo.
> El Machine Learning lo da vuelta. Yo **no** escribo las reglas.
> Le muestro diez mil correos que son spam y diez mil que no. Y el programa **deduce solo** cuáles son las reglas.
> Nadie le dijo "si dice VIAGRA en mayúsculas, es spam". Lo dedujo.
>
> Más adentro, la **IA Generativa**. Toda la IA anterior clasificaba: esto es spam, esto no.
> La generativa **crea cosas nuevas**: texto, imágenes, código, voz.
> Esto es lo que explotó a fines de 2022, con ChatGPT.
>
> Y en el centro está el **LLM**. Significa "modelo grande de lenguaje".
> Es el motor de ChatGPT, de Claude, de Gemini, de Copilot. De esto hablamos el resto de la charla.

**[PANTALLA]** Frase sola, muy grande: **"No busca. Predice."**

**[DIGO]**

> Ahora lo que quiero que se lleven aunque se olviden de todo lo demás.
>
> Un LLM, en el fondo, es **un autocompletar**.
> El mismo del teclado del móvil, ese que te sugiere la palabra siguiente.
>
> Solo que este leyó casi todo el texto público de internet.
> Y es tan grande que, para acertar la palabra siguiente, tuvo que aprender otras cosas de paso.
> Gramática. Lógica. Cómo se arma un argumento. Algo parecido a razonar. Y una cantidad brutal de conocimiento del mundo.
>
> Pero sigue siendo eso. **Una máquina de predecir qué viene después.**
>
> De ahí sale la frase más importante de hoy: **un LLM no busca información. La predice.**
>
> No es Google. No tiene una base de datos adentro. No va a buscar el dato.
> **Genera** la respuesta que le parece más probable.
>
> Esa sola frase explica el noventa por ciento de las cosas raras que hace la IA.

---

## 2. Cómo funciona, sin matemática — 5 min · ⏱ 0:07 → 0:12

**[PANTALLA]** Cinco puntos que aparecen de a uno.

**[DIGO]**

> Cinco cosas de cómo funciona. Cortas.
>
> **Uno: el token.** El modelo no ve palabras. Ve pedacitos de palabra, que se llaman *tokens*.
> Unos cuatro caracteres cada uno. Es un detalle técnico, pero importa por algo muy práctico: **todo se cobra y se mide en tokens**.
> Cuando alguien dice "esta consulta costó cuarenta céntimos", está contando tokens.
>
> **Dos: entrenar no es lo mismo que usar.**
> Entrenar un modelo grande cuesta cientos de millones. Tarda meses. Lo hacen cinco empresas en el mundo.
> Usarlo cuesta céntimos y tarda segundos.
> Es la diferencia entre la carrera de medicina y la consulta de veinte minutos.
> **Nosotros nunca vamos a entrenar nada. Nosotros usamos.**
>
> **Tres: no tiene memoria.** Y esto sorprende a todo el mundo.
> Cada conversación arranca de cero. No se acuerda de vos. No se acuerda de ayer. No aprende de lo que le corregiste.
> Cuando ChatGPT parece acordarse de tu nombre, es porque hay un programa alrededor que lo anotó y se lo vuelve a pegar.
> **La memoria no es del modelo. Es de la aplicación que lo envuelve.**
>
> **Cuatro: tiene fecha de corte.** Se entrenó hasta cierta fecha. De ahí en adelante no sabe nada.
> Si le preguntás por algo de la semana pasada, o te dice que no sabe, o te lo inventa.
>
> **Cinco: no es determinista.** Le hacés dos veces la misma pregunta y te da dos respuestas distintas.
> No es un fallo. Es de diseño: hay algo de azar controlado.
> Eso se regula con un parámetro que se llama **temperatura**. Baja, más predecible. Alta, más creativo y más impredecible.

**[PANTALLA]** Grande, en rojo: **ALUCINACIÓN**

**[DIGO]**

> Y ahora el concepto que más les va a servir en la vida real.
>
> Un modelo **alucina** cuando dice algo falso con seguridad absoluta.
> Te inventa una función que no existe. Una tabla que no está en la base. Un artículo de una ley. Una cita con autor y año.
>
> ¿Por qué? Volvemos a la frase: **su trabajo es que suene bien, no que sea cierto.**
> Está prediciendo texto probable. Y una ley que no existe pero que *podría* existir encaja perfecto en la predicción.
>
> Y acá está lo peligroso, y quiero que quede grabado: **la IA nunca suena insegura.**
> Cuando acierta y cuando se lo inventa, el tono es idéntico.
>
> Un compañero que no sabe algo, duda. Se le nota en la cara. Dice "creo que...".
> La IA no. Te va a decir la barbaridad más grande con la misma calma con la que te dice cuánto es dos más dos.
>
> **Toda la duda la tenés que poner vos.** Ese es el hilo de toda la charla.
>
> `→ Para qué te sirve:` cada vez que te dé un dato concreto —un número, un nombre, una norma— **preguntale de dónde lo sacó**. Esa sola costumbre te evita el 90% de los sustos.

---

## 3. Parada de comprensión — 1 min · ⏱ 0:12 → 0:13

**[NOTA]** ⚠️ Esta parada **no se negocia y no se recorta**. En una sala mixta, el que se perdió **no levanta la mano**: se queda callado y desconecta. Y desde el atril no lo ves, porque el técnico de la primera fila asiente.

**[PANTALLA]** *"No busca. Predice."* (la misma de antes)

**[DIGO]**

> Paro un segundo y pregunto a la sala, sin señalar a nadie.
>
> **¿Qué significa que la IA "no busca, predice"?**
>
> *(esperar de verdad. Contar hasta cinco. Incomodarse un poco es parte del trabajo.)*
>
> *(Si alguien contesta bien:)* Exacto. Y por eso, cuando no sabe algo, no se calla: **completa**.
>
> *(Si nadie contesta o contestan flojo:)* Lo digo yo entonces, porque es la clave de todo. No va a un archivo a buscar la respuesta. **La escribe.** Palabra por palabra, eligiendo la más probable. Por eso a veces escribe algo perfecto, y por eso a veces escribe algo perfectamente falso. Es el mismo mecanismo haciendo las dos cosas.
>
> Con eso alcanza. Seguimos.

---

## 4. El corazón: todo esto ya lo conocés — 12 min · ⏱ 0:13 → 0:25

**[NOTA]** 🎯 Este es **el bloque más importante de la charla** y el que cumple el encargo del correo. No lo recortes. Si vas mal de tiempo, recortá la sección 6 (modelos), no esta.
**No leas ninguna tabla en voz alta.** Va contado como una historia, hora por hora. La tabla completa está en la chuleta que tienen en la mano.

**[PANTALLA]** Un dibujo simple: una persona nueva entrando a una oficina. Título: **"Lunes, 9:00. Entra el fichaje nuevo."**

**[DIGO]**

> Ahora les voy a contar todos los conceptos de IA de una sola manera. Y no hace falta saber nada de tecnología.
>
> **Todos ustedes ya incorporaron a alguien alguna vez.** Un compañero nuevo, un becario, alguien que cambió de área.
>
> Resulta que **todo lo que hay que hacer para que una IA sea útil es exactamente lo mismo que hay que hacer para que un fichaje nuevo sea útil.** Punto por punto.
>
> Así que vamos a hacer eso. Lunes, nueve de la mañana. Entra alguien nuevo.

### Momento 1 — 9:00. Llega. ¿Qué trae puesto?

**[DIGO]**

> Llega y trae **lo que sabe**. Su carrera, sus años de oficio, su cultura general.
> Sabe contabilidad. Sabe redactar. Sabe inglés. Sabe programar.
>
> Y no sabe **absolutamente nada de nosotros**.
> No sabe cómo se llama nuestro cliente principal. No sabe dónde están los archivos. No sabe que los viernes se cierra a las tres.
>
> **Eso que trae puesto es el modelo.** El LLM.
> Es un producto de mercado. Muy bueno, muy caro de fabricar, y **exactamente igual al que puede contratar la competencia**.
>
> Todo lo demás que vamos a ver hoy es lo que vos le agregás encima. Y ahí sí está tu ventaja.
>
> `→ Para qué te sirve:` dejá de buscar "el mejor modelo". Es como buscar "el mejor licenciado". Lo que hace la diferencia es lo que le das después de contratarlo.

### Momento 2 — 9:15. Le pedís algo y le dejás papeles en la mesa

**[PANTALLA]** Un escritorio con una carpeta encima.

**[DIGO]**

> Le pedís lo primero: *"Prepárame el informe de morosidad de julio."*
>
> Esa petición, tal cual la dijiste, es el **prompt**. Nada más que eso. "Prompt" es la palabra de moda para decir *lo que le pediste*.
>
> Ahora bien. Si le decís solo eso y te vas, ¿qué te va a traer? Algo genérico. Un informe de morosidad de manual.
>
> Pero si le dejás encima de la mesa el fichero de julio, el informe del mes pasado y el correo del cliente, te trae otra cosa completamente distinta.
>
> **Esos papeles de la mesa son el contexto.**
>
> Y de acá sale la regla más rentable de toda la charla:
> **el contexto vale más que la pregunta.** No existe la frase mágica. Existe darle el material.
>
> Ahora, la mesa **tiene un tamaño**. Si le apilás cuatrocientas carpetas, las de abajo no las va a mirar.
> Eso es la **ventana de contexto**: cuánto material le entra de una vez.
> Por eso, en una conversación larguísima, el modelo "se olvida" de algo del principio. No se distrajo. **Se le cayó de la mesa.**
>
> `→ Para qué te sirve:` dos cosas, esta semana.
> Una: cuando te dé una respuesta floja, **no reescribas la pregunta. Pegale el documento.**
> Dos: cuando una conversación se puso larga y empezó a decir cosas raras, **abrí una nueva** y pegale lo importante. No pelees con una mesa desbordada.

### Momento 3 — 9:30. Las normas de la casa

**[DIGO]**

> Le explicás cómo funciona esto acá.
> *"Eres analista de riesgos. Escribes siempre en formato de informe. No hablas con clientes. Y todo lo que salga de aquí lo firma tu responsable."*
>
> Eso son las **instrucciones de sistema**. Las reglas permanentes, que no cambian con cada tarea.
> El usuario escribe la petición del momento. La empresa escribe las normas de la casa.
>
> Y hay una parte de esas normas que es especial: **lo que no puede hacer nunca**.
> No puede autorizar un pago. No puede escribirle al cliente. No puede tocar el sistema en producción.
>
> Eso se llama **guardrails**. Barandillas.
> Fíjense que a una persona nueva le decimos esto el primer día y nos parece lo más normal del mundo. Con la IA hay que hacer exactamente lo mismo, y mucha gente se lo saltea.
>
> `→ Para qué te sirve:` si vas a usar la IA para algo que repetís todas las semanas, **escribí una vez las reglas y pegalas siempre al principio**. Diez líneas. Te ahorra corregir lo mismo cuarenta veces.

### Momento 4 — 10:00. Cómo se hace ESTO, acá ⭐

**[PANTALLA]** Título grande: **SKILL** — subtítulo: *"El procedimiento de la casa, escrito."*

**[NOTA]** 🎯 Esta es **la parte que pidieron expresamente**. Tomate el tiempo. Es el minuto más valioso de la charla para el perfil no técnico.

**[DIGO]**

> Y ahora llegamos a la parte que a mí me parece la más interesante, y la que menos se entiende.
>
> Tu fichaje nuevo sabe contabilidad. Eso lo trae de fábrica.
> Pero **no tiene ni idea de cómo se cierra el mes acá**.
>
> Acá el cierre se hace el día tres. Primero se concilian bancos. El asiento de provisiones lo valida Marta. Y el fichero se sube a esa carpeta, con ese nombre, en ese formato.
>
> Nada de eso está en ninguna carrera. Está en la cabeza de la gente que lleva tiempo. O, con suerte, en un Word que nadie abre.
>
> **Cuando eso lo escribís y se lo entregás, eso es una skill.**
>
> Una skill es un **procedimiento de la casa, escrito**, que la IA carga cuando le hace falta.
> No es conocimiento general. Es **cómo se hace algo, aquí dentro.**

**[PANTALLA]** Los cinco ejemplos, uno por línea.

**[DIGO]**

> Déjenme darles cinco ejemplos, porque con uno solo no se ve.
>
> **Uno. La receta de tu casa.**
> Un cocinero profesional sabe cocinar. Eso es el modelo.
> Pero para que te haga **la paella como la hacía tu madre**, necesita la receta de tu casa. Esas cantidades. Ese orden. Ese truco del final que no está en ningún libro.
> Saber cocinar es el modelo. La receta de tu casa es la skill.
>
> **Dos. El cierre de mes.**
> El que acabo de contar. Todo contable sabe contabilidad. Ninguno sabe **tu** procedimiento de cierre.
>
> **Tres. El protocolo de urgencias del hospital.**
> Todo médico sabe medicina. Eso es el modelo.
> Pero el protocolo de **este** hospital para una parada cardíaca —quién llama, en qué orden, con qué material, quién se queda con la familia— eso es la skill.
> Y fíjense en un detalle: ese protocolo salva vidas **justamente porque no depende de la genialidad de nadie**. Se hace igual siempre.
>
> **Cuatro. La checklist del piloto.**
> El piloto sabe volar. Y aun así, antes de despegar, lee una lista en voz alta.
> La lista no está porque el piloto sea malo. Está **porque es bueno y aun así se le puede pasar algo**.
> Esa lista es una skill.
>
> **Cinco, el nuestro.**
> En nuestro flujo hay una skill que se llama *"cómo se critica un plan aquí"*.
> Dice: leé el plan. Abrí cada archivo que cita y comprobá que existe de verdad. Buscá contradicciones entre las fases. Comprobá que los criterios se puedan medir, no opinar. Y emití un veredicto: aprobado o rechazado.
> Ese procedimiento **se escribió una vez**. Ahora lo ejecuta cualquiera de nuestros agentes, igual, todas las veces, sin cansarse. Y en la segunda parte les voy a mostrar lo que encuentra.

**[PANTALLA]** Cuatro líneas, una debajo de otra. Esta es **la diapositiva que la gente fotografía**.

**[DIGO]**

> Y ahora la distinción que quiero que se lleven, porque estas cuatro cosas se confunden todo el tiempo:
>
> > **Contexto** = los papeles de la mesa · **el QUÉ**
> > **Skill** = el procedimiento de la casa · **el CÓMO**
> > **Herramienta** = las llaves y los accesos · **el PODER** *(ahora lo vemos)*
> > **Agente** = quien usa las tres cosas hasta terminar · **el QUIÉN**
>
> Si retienen solo estas cuatro líneas de los 45 minutos, ya valió la pena venir.
>
> `→ Para qué te sirve:` esto es para todos, programen o no.
> **Elegí una cosa que hacés siempre igual y que hoy está solo en tu cabeza. Escribí el procedimiento. Media hora.**
> Te sirve para la IA, te sirve para el próximo compañero que entre, y te sirve el día que estés de vacaciones.
> Y ojo con esto, que es importante: **si no lo podés escribir, tampoco lo vas a poder automatizar.** Nunca. Con ninguna tecnología.

### Momento 5 — 11:00. Las llaves y los accesos

**[PANTALLA]** Un llavero. Título: **De opinar a hacer.**

**[DIGO]**

> Once de la mañana. El fichaje ya sabe qué queremos, cómo son las normas y cuál es el procedimiento.
> Y todavía **no puede hacer nada**, porque no tiene acceso a ningún sistema.
>
> Lo único que puede hacer es **darte consejos**. Muy buenos, quizás. Pero consejos.
>
> Entonces le das los accesos. El usuario del ERP. La llave del archivo. Permiso para lanzar la consulta.
>
> **Eso son las herramientas.** En IA se llaman *tools*.
> Es la capacidad del modelo de decir: *"para contestarte esto necesito abrir este fichero"*. Y abrirlo de verdad.
>
> Y acá pasa **el salto más grande de los últimos dos años**:
>
> > Un modelo **sin** herramientas te explica cómo se arregla el problema.
> > Un modelo **con** herramientas te lo arregla.
>
> **Lo segundo se llama agente.** Y ya está: esa es toda la definición. Es la palabra que todo el mundo usa y casi nadie define.
>
> Un **agente** es tres cosas juntas:
> un modelo, con herramientas para actuar, y **un bucle**.
> El bucle es lo que lo cambia todo: mira cómo está la cosa, decide, actúa, **mira el resultado**, ve que salió mal, corrige, y vuelve a empezar. Hasta terminar o hasta rendirse.
>
> Exactamente lo que hace una persona trabajando.
>
> Un ejemplo de los nuestros: *"el proceso de anoche terminó con error, averigua por qué"*.
> Y el agente abre los registros, los cruza con el código, se da cuenta de en qué punto murió, lanza una consulta a la base para confirmarlo, y vuelve con el diagnóstico y la línea exacta.
> No te contestó una pregunta. **Te hizo la investigación.**
>
> Dos palabras más y cierro el momento:
> **Subagente**: cuando le pide a un compañero que se encargue de una parte. *"Tú revisa las facturas de proveedores mientras yo sigo con lo demás."*
> **Multiagente**: un equipo con roles. Uno propone, otro revisa, otro ejecuta, otro audita. Esto es literalmente lo que les voy a mostrar en la segunda parte.
>
> `→ Para qué te sirve:` antes de pedirle algo, preguntate **si tiene acceso a lo que hace falta para saberlo**.
> Porque si no lo tiene, **te va a contestar igual**. Y esa respuesta va a ser inventada.
> Es la causa número uno de las respuestas malas.

### Momento 6 — 13:00. Te trae el trabajo

**[PANTALLA]** Dos frases: *"¿De dónde sacaste esto?"* / *"Yo firmo."*

**[DIGO]**

> Una de la tarde. Te trae el informe. Y hacés lo que harías con cualquiera: **le pedís que lo justifique.**
>
> *"Este número de aquí, ¿de dónde salió? Enséñame el expediente."*
>
> **Eso se llama grounding.** Anclaje.
> Es obligar a la IA a apoyarse en algo verificable, en vez de responder de memoria.
>
> Y tiene dos formas prácticas:
> **Una:** dejarle consultar el archivador en vez de responder de cabeza. Cuando eso se hace con documentos, se llama **RAG**, y es lo que hay debajo de todos los "chatbots que responden sobre nuestra documentación".
> **Dos:** exigirle que **cite**. Que te señale el documento, la página, la línea.
>
> Retengan esta palabra —**grounding**— porque **la segunda parte de la charla es entera sobre esto**.
>
> Y lo último del día. El informe lo firmás **vos**.
> Él lo prepara. La firma es de una persona.
> Eso se llama **human-in-the-loop**, "humano en el bucle", y es el principio de diseño más importante de todo lo que voy a mostrar.
>
> > **El agente prepara. La persona firma.**
>
> Y como la firma es tuya, **la responsabilidad también**. Las dos caras van juntas.
>
> `→ Para qué te sirve:` incorporá una sola pregunta a tu rutina: **"¿de dónde sacaste esto?"**. Si no te lo puede señalar, no lo sabe. Lo está sonando bien.

### Y al día siguiente…

**[DIGO]**

> Martes, nueve de la mañana. Llega otra vez.
>
> Y **no se acuerda de nada**. Ni de vos, ni del informe, ni de lo que le corregiste.
>
> Ahí está la memoria de la que hablábamos. Si querés que se acuerde, **tenés que darle un cuaderno**. Y el cuaderno no es él: **se lo ponemos nosotros por fuera**.
>
> Todas las herramientas serias de IA hoy son, en el fondo, un modelo más un cuaderno bien organizado.

---

## 5. Dónde se rompe la comparación — 3 min · ⏱ 0:25 → 0:28

**[NOTA]** ⚠️ **No te saltees esta sección jamás.** La analogía del fichaje es tan cómoda que si la dejás correr sin frenarla, la sala sale pensando "es como un compañero nuevo" — y ese modelo mental lleva a **confiar por defecto**, que es justo lo contrario de lo que buscamos. Va aquí, en el pico de simpatía de la comparación. Ahí es donde pega.

**[PANTALLA]** Título: **"Dónde se rompe la comparación"** — tres puntos.

**[DIGO]**

> Ahora tengo que frenar la comparación, porque me gusta demasiado y es peligrosa.
>
> El fichaje nuevo se parece a una IA en muchas cosas. Y hay **tres** donde no se parece en nada. Y son justo las tres que te pueden costar caro.
>
> **Una. Tu compañero nuevo dice "no lo sé". La IA no.**
> Una persona que no sabe algo, duda. Se le nota. Pregunta.
> La IA, cuando no sabe, **completa**. Y lo hace con el mismo tono de seguridad que cuando acierta.
> No te está mintiendo, ojo. **No tiene ni idea de que no sabe.** Es peor.
>
> **Dos. Tu compañero aprende de lo que le corregís. La IA no.**
> Le explicás algo el lunes y el martes ya lo sabe. Una persona acumula.
> La IA arranca de cero cada vez, salvo que alguien haya construido el cuaderno por fuera.
> Corregirla no la mejora. Solo mejora **esa** conversación.
>
> **Tres. Tu compañero tiene sentido de la responsabilidad. La IA no tiene ninguno.**
> Una persona sabe que si se equivoca hay consecuencias, y eso le hace ir con cuidado en lo importante.
> La IA pone exactamente **el mismo cuidado** en corregirte una coma que en tocar el sistema de producción. Ninguna diferencia.
>
> Por eso las barandillas y la firma humana no son burocracia. **Son el único sentido de la responsabilidad que hay en el sistema, y se lo ponemos nosotros desde fuera.**
>
> Con esas tres roturas en la cabeza, la comparación del fichaje es utilísima. Sin ellas, es una trampa.

---

## 6. La escalera: de chat a agente — 4 min · ⏱ 0:28 → 0:32

**[PANTALLA]** Cuatro escalones dibujados.

**[DIGO]**

> Vamos a ordenar todo esto en una escalera de cuatro escalones. Con un ejemplo en cada uno.
>
> **Escalón 1 — Chat.**
> Le pregunto algo, me contesta, yo copio, yo pego, yo pruebo.
> Todo el trabajo y toda la responsabilidad siguen siendo míos.
> **Esto es el noventa por ciento de lo que la gente usa hoy.**
>
> **Escalón 2 — Asistente integrado.**
> El modelo está **dentro** de la herramienta donde ya trabajo y ve lo que estoy haciendo.
> En el correo, ve el hilo y me redacta la respuesta.
> Menos copiar y pegar. Y mucho mejores respuestas, porque ya no tengo que explicarle dónde estoy parado.
>
> **Escalón 3 — Agente.**
> Ya tiene llaves. Le pido un objetivo y él da todas las vueltas necesarias.
> No me contesta una pregunta: **me hace el trabajo**.
>
> **Escalón 4 — Sistema agéntico.**
> Varios agentes con roles distintos. Y —esto es lo importante— **con desconfianza incorporada entre ellos**.
> Uno propone. Otro, cuya única misión es encontrarle los agujeros, lo critica. Un tercero lo implementa. Un cuarto audita que lo hecho sea de verdad lo que decía el plan.
>
> Y ese cuarto escalón es el que les voy a contar con un caso real dentro de un rato.
>
> `→ Para qué te sirve:` la mayoría de la gente está en el escalón 1 y cree que eso es "usar IA". **Pasar del 1 al 2 es gratis y es el salto de calidad más grande que vas a notar.** Es simplemente usar la IA que ya está metida en la herramienta donde trabajás, en vez de abrir una pestaña aparte.

---

## 7. Modelos y tecnologías — 5 min · ⏱ 0:32 → 0:37

**[NOTA]** ⚠️ Refrescá nombres el 04/08. Este mercado cambia cada dos meses. Lo que **no** cambia es lo de los tres tamaños: anclá el mensaje ahí.
Si vas mal de tiempo, **esta es la sección que se recorta**, no la 4.

**[PANTALLA]** Tres cajas enormes: **Pequeño · Medio · Grande**. Los nombres comerciales, en letra chica debajo.

**[DIGO]**

> Del mercado les voy a contar lo único que no caduca.
>
> Hay cinco o seis familias grandes. **Claude**, de Anthropic — fuerte en código y en trabajo agéntico, es la que usamos nosotros. **GPT**, de OpenAI — la más generalista y la más conocida. **Gemini**, de Google — muy integrada con Word, correo y Drive. Y las abiertas: **Llama**, **Mistral**, **DeepSeek**, que te las podés descargar y correr en tu propia casa.
>
> Ahora lo importante. **Todas las familias tienen exactamente los mismos tres tamaños.** Cambia el nombre comercial, no la idea.
>
> Volvamos a la oficina, que se entiende mejor:
>
> **El pequeño es el becario.** Rápido, baratísimo. Para tareas masivas y simples: clasificar diez mil registros, sacar datos de un formulario, resumir.
>
> **El mediano es el analista.** Es **el caballo de batalla**. El noventa por ciento del trabajo real se hace acá.
>
> **El grande es el socio del despacho.** Para problemas de verdad difíciles: diseñar algo desde cero, diagnosticar lo que nadie entiende. Es más lento y bastante más caro.
>
> **Y la regla es una sola frase: no mandes al socio a hacer fotocopias, y no le pidas al becario que diseñe la estrategia.**
>
> En la práctica: **empezá siempre por el mediano. Bajá si la tarea es masiva y repetitiva. Subí solo cuando el mediano ya te falló.**
>
> El error clásico del que empieza es usar siempre el más caro por las dudas. El error contrario es peor: usás el más barato, te da respuestas flojas, y concluís que la IA no sirve.

**[PANTALLA]** Dos columnas: *En la nube · En nuestra casa*

**[DIGO]**

> Y una decisión que va a salir sí o sí: **nube o local**.
>
> **En la nube**: mejor calidad, cero infraestructura, pagás por uso.
> La pregunta que hay que hacer siempre es qué pasa con nuestros datos. Y acá una aclaración que resuelve la mitad de las discusiones sobre confidencialidad:
> **en los planes de empresa, el contrato dice explícitamente que no entrenan con tus datos. En las versiones gratuitas, sí pueden.**
> **No son el mismo producto, aunque se llamen igual.**
>
> **En nuestra casa**: te bajás un modelo abierto y lo corrés en nuestros servidores. El dato no sale nunca. A cambio, hace falta hardware, alguien que lo mantenga, y la calidad está un escalón por debajo. Para lo verdaderamente sensible, es el camino.

**[NOTA]** Si te sobran 60 segundos, agregá aquí las herramientas concretas: para quien programa, Copilot / Cursor / agentes de terminal. Para quien no, Copilot 365, Gemini en Workspace, NotebookLM y transcripción de reuniones. Si no sobran, está todo en la chuleta.

---

## 8. Buenas prácticas — 5 min · ⏱ 0:37 → 0:42

**[PANTALLA]** La matriz. Dejala fija mientras hablás. Es la que la gente fotografía.

| Lo que necesito hacer | Lo que uso | Lo que NO uso |
|---|---|---|
| Redactar, reformular, resumir | Chat normal (el mediano) | Nada más caro |
| Preguntar sobre **nuestros** documentos | Herramienta que lea los documentos y **cite** | El chat pelado: te lo inventa |
| Trabajar sobre el fichero que tengo abierto | Asistente dentro de la herramienta | Copiar y pegar a una pestaña aparte |
| Hacer lo mismo en 40 sitios | Un agente | El chat: 40 veces copiar y pegar |
| Clasificar 10.000 registros | Modelo pequeño | El grande: 50× el precio, mismo resultado |
| Diagnosticar algo raro, diseñar desde cero | Modelo grande | El pequeño: te da algo plausible y flojo |
| Que cuadren las cifras | Excel, una consulta, una calculadora | **Cualquier IA** |
| Datos de clientes o personales | Plan de empresa, o modelo local | La versión gratuita |

**[DIGO]**

> Esta es la tabla para fotografiar. Dos filas que quiero comentar.
>
> La de **cuadrar cifras** es la que más sorprende. **La IA es mala en aritmética.**
> Piénsenlo: está prediciendo texto, no calculando. Si necesitás que cuadre, que la IA escriba la fórmula o la consulta, y que el cálculo lo haga el Excel o la base. **Que sume ella, nunca.**
>
> Y la de **datos sensibles**. La regla mental más simple que conozco:
> **"¿esto lo pondría en un correo a un proveedor de fuera?"** Si la respuesta es no, no lo pegues en un chat gratuito.

**[PANTALLA]** Las 6 reglas, numeradas, sin adornos.

**[DIGO]**

> Y seis reglas. Valen igual para técnicos y no técnicos.
>
> **Uno. Contexto antes que astucia.** Pegale el documento. El correo entero. El error completo, no tu resumen. La frase mágica no existe.
>
> **Dos. Pedí el formato.** *"Devolvémelo como tabla con estas cuatro columnas."* Vale mil veces más que "hacelo bien". Si no se lo decís, elige uno cualquiera.
>
> **Tres. Dale un ejemplo.** Uno o dos ejemplos de cómo se ve una respuesta buena. Es lo que mejor funciona y casi nadie lo hace.
>
> **Cuatro. Por pasos, no de un salto.** Primero que analice. Lo mirás. Después que proponga. Lo mirás. Después que ejecute.
> **Cada revisión intermedia es un error que no llegó a producción.**
>
> **Cinco. Verificá lo verificable.** Si te da un número, un archivo, una norma: pedile la fuente. Suena obvio, y es lo que menos se hace — precisamente porque la respuesta *suena* muy bien.
>
> **Seis. Nada irreversible sin firma humana.** Borrar, enviar, tocar producción, contestarle a un cliente. Que lo prepare todo. La firma es tuya.

**[PANTALLA]** *Cuándo NO usar IA*

**[DIGO]**

> Y para equilibrar, porque una charla de IA donde todo es maravilloso no hay que creérsela. **Cuándo no usarla:**
>
> - Cuando la decisión tiene **responsabilidad legal**. Te ayuda a preparar. No decide.
> - Cuando necesitás **exactitud numérica**.
> - Cuando **no vas a poder verificar** el resultado. Si no tenés forma de saber si está bien, no lo uses. Estás delegando a ciegas.
> - Cuando **explicarle la tarea cuesta más que hacerla**. Pasa, y más de lo que parece.

---

## 9. Cierre del bloque 1 — 2 min · ⏱ 0:42 → 0:44

**[PANTALLA]** Tres frases.

**[DIGO]**

> Si se olvidan de todo, quédense con tres frases.
>
> **Una. No busca, predice.** Por eso alucina. Por eso suena seguro. Por eso hay que anclarlo a hechos.
>
> **Dos. El contexto vale más que el prompt.** Dale material. No busques la frase mágica.
>
> **Tres. La IA no duda.** La duda la ponés vos. Y mejor todavía si la ponés en el proceso, y no en tu fuerza de voluntad.

**[PANTALLA]** *"El lunes"* — dos líneas.

**[DIGO]**

> Y una cosa para hacer esta semana, según lo que hagan.
>
> **Si escribís código:** usá el asistente **dentro** del editor, no en una pestaña aparte. Es el escalón 2, es gratis, y es el salto de calidad más grande que vas a notar.
>
> **Si no escribís código:** agarrá los documentos con los que trabajás y metelos en una herramienta que te deje preguntarles **con citas**. Una semana de preguntas reales. Es, de lejos, lo de mayor impacto para quien no programa.
>
> Y los dos: **elegí un procedimiento que hoy está solo en tu cabeza y escribilo.** Media hora. Eso es una skill, y sirve con IA y sin IA.
>
> Ahora les muestro cómo se ve todo esto en un proyecto real. Con producción real. Y con lo que salió mal, que es la parte que más se aprende.

**[NOTA]** ✅ **Checkpoint:** si llegás acá pasados los 44 minutos, arrancá el bloque 2 igual. No recuperes tiempo hablando más rápido — recortá del *Plan B*.

---
---

# BLOQUE 2 — CASO DE ÉXITO TECH (20 min)

**[NOTA]** ⚠️ Este es el bloque donde más fácil te pasás. Regla dura: **si a los 9 minutos no arrancaste con el batch de Pacífico, saltá lo que sea.**
Y regla de vocabulario: **todo término técnico se traduce en el momento, en media frase.** La mitad de la sala no sabe qué es un rollback, y ese es justo el dato que tiene que impresionar.

## 1. El punto de partida — 2 min · ⏱ 0:00 → 0:02

**[PANTALLA]** Foto del problema.

**[DIGO]**

> Contexto para los que no están en el día a día de estos proyectos.
>
> RS es un producto con muchos años encima, funcionando en varios clientes.
> Tiene una parte web, y tiene procesos que corren **de noche** —lo que llamamos *batch*— moviendo millones de registros contra bases de datos enormes.
>
> Y tiene una base de datos con cientos de tablas, con convenciones propias que **no están escritas en ningún lado**. Están en la cabeza de la gente que lleva tiempo.
>
> El escenario típico: entra alguien nuevo, le dan una tarea, y tarda **semanas** en poder tocar algo con confianza. Y el que lleva tiempo es cuello de botella de todo el mundo.
>
> El encargo no fue "usemos ChatGPT". Fue bastante más incómodo:
> **¿podemos meter agentes dentro del ciclo real de desarrollo, sobre nuestras tareas y nuestro código, sin romper nada y sin que nadie firme a ciegas?**
>
> Adelanto la conclusión: se puede. Pero **el trabajo no está donde uno cree.**
> No está en el modelo. Está en todo lo que hay que construir **alrededor** del modelo. Que es, exactamente, lo que vimos en la primera parte.

---

## 2. El flujo agéntico: dos bucles — 4 min · ⏱ 0:02 → 0:06

**[PANTALLA]** Bucle 1: la cadena de agentes.

**[DIGO]**

> El flujo tiene **dos bucles**. Me interesa que se distingan, porque hacen cosas distintas.
>
> **Bucle 1: el ciclo de vida de una tarea.**
> Una cadena de agentes especializados. Cada uno con su rol, sus normas de la casa y su acceso a la documentación.
>
> - El de **Negocio** toma el texto libre del cliente —un correo, una nota de reunión— y produce la especificación de negocio.
> - El **Funcional** la convierte en análisis funcional, con casos de uso y criterios.
> - El **Técnico** baja eso a qué módulos se tocan, qué tablas, qué procesos.
> - El de **Desarrollo** propone el cambio de código.
> - El de **Calidad** diseña y ejecuta la verificación.
> - Y el **Revisor** revisa el cambio antes de que entre.
>
> Todo esto corre **sobre el gestor de tareas que el equipo ya usa** —Azure DevOps, Jira, Mantis— y el resultado vuelve ahí, como tarea o como comentario.
> No es un chat aparte del que después hay que copiar y pegar. **Entra y sale por donde el equipo ya trabaja.**
> Eso suena a detalle y **es la mitad de la adopción**.
>
> Y en cada salto entre agentes, **hay una persona que aprueba**.

**[PANTALLA]** Bucle 2, grande: **Proponer → Criticar → Implementar → Supervisar**

**[DIGO]**

> **Bucle 2.** Y este es el que da la calidad. Cuatro pasos, y cada paso lo hace **un agente distinto**.
>
> **Proponer.** Un agente escribe un plan detallado, por fases. Y cada afirmación tiene que estar **anclada a un archivo y una línea reales**.
> No vale "hay que tocar la capa de datos". Vale "hay que tocar este archivo, línea 122".
>
> **Criticar.** Acá está el corazón de todo.
> **Otro** agente, que arranca de cero y no vio nada de lo anterior, con una única misión: **ser el juez**.
> Abre cada archivo citado y comprueba que exista y diga lo que el plan dice. Busca contradicciones entre fases. Comprueba que los criterios se puedan medir en vez de opinar.
> Y da un veredicto binario: **aprobado o rechazado**.
>
> **Implementar.** Recién ahí se toca código. Fase por fase, con pruebas.
>
> **Supervisar.** Un cuarto agente audita que lo implementado sea de verdad lo que decía el plan. Y **ejecuta las pruebas él mismo**, en vez de leer que alguien escribió "todo correcto".
>
> Fíjense que esto es exactamente el momento 4 de la primera parte: **es una skill**. El procedimiento de criticar un plan, escrito una vez, ejecutado siempre igual.

**[PANTALLA]** Enorme: **7 de 7 planes rechazados en su primera versión.**

**[DIGO]**

> Y les doy el dato que mejor resume por qué esto funciona.
>
> En una de las series de trabajo, **el juez rechazó siete de siete planes en su primera versión.**
> Y en la serie en la que estoy ahora, un mismo plan lleva **dos rechazos seguidos**. El segundo, de un juez independiente que encontró siete puntos bloqueantes.
>
> La primera vez que conté esto, alguien me dijo: "entonces el que los escribe es malo".
> No. **El que los escribe es normal.** Un primer borrador de cualquiera de nosotros también tiene agujeros.
>
> La diferencia es que el borrador de una persona se revisa **a veces**, con prisa, y lo revisa alguien que ya está mentalmente casado con la solución.
>
> > **El valor no está en que la IA escriba. Está en que otra IA le encuentre los agujeros antes que vos. Todas las veces. Sin cansarse y sin ego.**

**[PANTALLA]** Tres pilares: *Grounding · Evidencia obligatoria · Puertas binarias*

**[DIGO]**

> Tres cosas hacen que esto no sea humo. Y las tres son **caras**. Esta es la parte que no sale en las demos.
>
> **Uno: grounding.** La palabra de la primera parte.
> Se reconstruyó un manual del proyecto: unos **cuarenta documentos** técnicos y funcionales, con un índice, que el agente está **obligado a leer antes de tocar nada**.
> Sin eso, adivina. Y adivina de forma muy convincente.
>
> **Dos: evidencia obligatoria.** Nada se afirma sin señalar archivo y línea.
> Y va más lejos: los documentos llevan **marcas de fiabilidad**. Esto está verificado contra el código. Esto es una deducción. Esto no se pudo comprobar.
> **Que la documentación diga en voz alta qué parte de sí misma no es fiable** es una idea que me robaría para cualquier proyecto, con IA o sin ella.
>
> **Tres: puertas binarias.** Compila o no compila. La prueba pasa o no pasa. El número sale o no sale.
> **Nada de "quedó mejor".** Si el criterio es una opinión, el agente siempre te va a poder convencer de que lo cumplió.

---

## 3. Pacífico, en concreto — 7 min · ⏱ 0:06 → 0:13

### Frente A — La documentación que no existía · 1 min

**[DIGO]**

> Tres frentes. El primero, rápido.
>
> El proyecto **no tenía documentación técnica utilizable**. Había cosas sueltas, viejas, y que se contradecían entre sí.
>
> Se reconstruyó desde el código: arquitectura, capas, procesos de noche, base de datos, referencias de tablas y de pantallas. Con las marcas de fiabilidad que decía.
>
> El beneficio obvio es que ahora alguien nuevo se orienta.
> El beneficio real es otro: **esa documentación es el combustible de todos los agentes**.
>
> Y esto lo digo para los responsables que estén escuchando: **documentar dejó de ser un gasto de conciencia y pasó a ser una inversión con retorno medible.** Es la primera vez que veo ese argumento funcionar de verdad.

### Frente B — El fallo que nos enseñó todo · 2 min

**[PANTALLA]** La frase equivocada, con un tachón rojo.

**[DIGO]**

> El segundo frente es un **error**. Y lo cuento porque enseña más que los aciertos.
>
> Un agente generó una especificación que decía que el proceso de carga **empezaba** en un módulo concreto. Y usaba nombres de tabla con un formato que aquí no se usa.
>
> Las dos cosas estaban mal. El proceso empieza **antes**, en otro módulo. Ese que citaba es el **segundo** paso.
>
> ¿Se lo inventó de la nada? **No.** Y acá está lo interesante.
> Fue a buscarlo a nuestra documentación funcional. Y ahí había una frase que decía, textual, que ese módulo era *"el punto de entrada principal"*.
> **El agente la tomó literal.**
>
> O sea: **no fue una alucinación aleatoria. Fue nuestra propia documentación ambigua, repetida con una seguridad que nosotros nunca le habríamos puesto.**
>
> Y la solución tampoco fue tocar el modelo. Fue exactamente lo de la primera parte:
> escribir el **catálogo** de los procesos —cuáles son, qué hace cada uno, cuál va primero—;
> escribir la **regla de nombres** de forma explícita;
> y **recortarle el alcance a cada agente**: el de negocio ya no puede decidir cuestiones técnicas, porque no es su trabajo. El técnico sí, pero **leyendo el catálogo**.
>
> La moraleja, y para mí es la frase más importante del caso:
>
> > **La IA amplifica la calidad de tu documentación. Para bien y para mal.**
>
> Si tu documentación es ambigua, no vas a tener un agente confundido.
> Vas a tener un agente **muy convincente** repitiendo tu ambigüedad, a escala.

### Frente C — El proceso de noche que no terminaba · 4 min

**[PANTALLA]** Línea de tiempo: **95 min → ERROR**

**[DIGO]**

> Y el tercero, que es el que más me gusta contar, porque no es "me escribió un formulario".
>
> **El problema.** Uno de los procesos que corre de noche en producción **terminaba en error**.
> Noventa y cinco minutos. Y al fallar, la base de datos tenía que **deshacer todo el trabajo ya hecho** —eso es un *rollback*—: **veintisiete millones de registros** deshaciéndose. Cuarenta minutos de espera muerta.
>
> Y ya era la **tercera** vez que aparecía la misma familia de fallo. Con dos intentos previos de arreglarlo que no habían llegado al fondo.
>
> **Qué hizo el flujo.**
>
> Primero, **medir**. Antes de tocar nada, instrumentar el proceso para saber dónde se va el tiempo de verdad.
> Con una regla de oro: **la medición no puede convertirse en el atasco que está midiendo.** Si por medir lo hacés más lento, ya no estás midiendo nada.
>
> Después, con los datos en la mano, el plan. Y estos son los hallazgos, todos con evidencia real:
>
> **Uno.** La fase que fallaba murió a los **2.400.057 milisegundos**. Y el tiempo máximo de espera configurado era de 2.400.000.
> O sea: **no murió trabajando. Murió esperando.**
> Cuando el número coincide al milisegundo con un valor de configuración, no estás mirando un problema de rendimiento. Estás mirando un tope que alguien puso.
>
> **Dos. ¿Esperando qué?** La base de datos estaba esperándose **a sí misma**: más de novecientos segundos acumulados de espera interna, **con el procesador al cero por ciento**.
> No estaba bloqueada por nadie —los bloqueos sumaban 123 milisegundos en total—. **Estaba quieta.**
>
> **Tres. Y de paso, apareció trabajo directamente inútil.**
> Treinta y seis minutos de borrados evitables.
> Una actualización de casi **veintiocho minutos** sobre treinta y seis millones de registros.
> Y una inserción de **seis minutos que insertaba cero registros**. Seis minutos. Todas las noches. Para no hacer nada.
>
> **Y después vino el juez.**
> El plan se criticó contra los registros y los datos reales. **Trece hallazgos. Dos de ellos bloqueantes.**
> Uno: un script que el propio plan proponía **estaba roto**.
> Dos: una de las fases propuestas **volvía a provocar el mismo error que decía arreglar**.
> Las dos cosas se corrigieron **antes** de tocar producción.

**[PANTALLA]** Grande: **"El baseline está incompleto."**

**[DIGO]**

> Y ahora la parte que más orgullo me da, aunque suene raro.
>
> El propio plan lleva escrita, en mayúsculas, una advertencia: **la medición de referencia está incompleta.**
>
> ¿Por qué? Porque las tres corridas que se instrumentaron **murieron antes de llegar al final**. Así que hay un tramo del proceso cuya duración con volumen real **nunca se midió**.
>
> Y por lo tanto, la previsión de bajar de noventa y cinco minutos a unos cuarenta y cinco es **una previsión, no un compromiso**. Hasta que haya una primera corrida completa que fije la referencia de verdad.
>
> Ese cartel **no lo puse yo. Lo puso el juez**, revisando el trabajo.
>
> Un consultor os habría enseñado una diapositiva con una flecha verde y "reducción del 50%".
>
> Y esa es exactamente la diferencia entre un sistema con IA que sirve y uno que te mete en un problema dentro de seis meses:
>
> > **el que sirve te dice qué parte de lo que te está contando todavía no está probada.**

**[NOTA]** ⚠️ **[COMPLETAR antes del 04/08]** — estado actual del plan, si ya hubo corrida completa en verde, y el número real de la ventana hoy contra los 95 minutos iniciales.
Si tenés número real: **ese es tu mejor cierre del bloque.**
Si no lo tenés: la honestidad del "baseline incompleto" cierra igual de bien. Pero decilo **como decisión**, no como excusa.

---

## 4. Lo que salió mal — 4 min · ⏱ 0:13 → 0:17

**[PANTALLA]** Título: **"Lo que salió mal"**. Que se note que es un bloque entero, no una nota al pie.

**[DIGO]**

> Me pidieron que hablara de las dificultades de la adopción, y me alegra, porque es la parte útil. Siete. Rápidas.
>
> **Uno: el falso verde. Es el problema número uno, con diferencia.**
> El agente te dice "hecho, y las pruebas pasan"… y la prueba **no estaba probando nada**.
> Dos casos reales, y son buenísimos:
> - Una orden de ejecutar pruebas filtrando por un nombre que **no coincidía con ninguna**. Cero pruebas ejecutadas. ¿Y el resultado del comando? **Correcto.** Verde perfecto sobre la nada.
> - Un control automático de calidad que contaba coincidencias de texto y que, por cómo estaba escrito, **premiaba exactamente el error que decía cazar**. Cuanto peor estaba el código, más subía el marcador hacia el objetivo.
>
> La contramedida es una regla simple, y **funciona igual sin IA**:
> > **El control se prueba contra el defecto. Si no lo viste fallar, no sabés si funciona.**
>
> **Dos: "corregido" no es evidencia.**
> De catorce correcciones declaradas en un listado de cambios, **tres cerraban el síntoma y dejaban vivo el defecto**.
> No leas el resumen de lo que hizo. Andá al cambio.
>
> **Tres: la confianza es asimétrica.**
> Un error espectacular te cuesta veinte aciertos.
> Por eso el **orden** importa muchísimo. Empezá por lo **reversible**: documentación, análisis, planes, revisiones. Y sólo después lo irreversible: código, base de datos, producción.
> **El que empieza al revés quema la confianza del equipo la primera semana y ya no la recupera.**
>
> **Cuatro: la fricción del primer día.** Y esto no es un problema técnico.
> Alguien abre la herramienta, **no entiende qué hacer en los primeros tres minutos**, la cierra, y vuelve a trabajar como siempre.
> Así mueren todas las herramientas internas. Todas.
> **Si alguien no saca algo útil en su primera sesión, no hay segunda sesión.** Y lo que falta ahí no es funcionalidad: es diseño del primer día.
>
> **Cinco: el entorno miente.** Muy nuestro y nada glamuroso.
> La carpeta que editás no siempre es la que lee el agente. Hay copias, hay rutas distintas.
> Cambiás algo, no llega, y parece un fallo de la IA. **No lo es. Es fontanería.** Y te come días.
>
> **Seis: los costes.**
> Sin techo, alguien lanza cincuenta veces el modelo más caro y llega la factura.
> Hace falta gobierno: modelo por defecto, tope por proyecto, aviso al ochenta por ciento.
> Sin eso, o gastás de más, o —lo más probable— alguien se asusta y lo prohíbe todo.
>
> **Siete: la resistencia. Y es legítima.**
> *"Esto me va a sustituir."* *"Yo lo hago más rápido a mano."*
> Lo que funcionó no fue un discurso. Fue un hecho:
> > **El agente no cierra la tarea. La prepara. La firma sigue siendo tuya.**
>
> Y como la firma es tuya, la responsabilidad también. Dicho así, la amenaza se convierte en herramienta. Y de paso, es verdad.

---

## 5. Lecciones y cierre — 2 min · ⏱ 0:17 → 0:19

**[PANTALLA]** Cinco lecciones numeradas.

**[DIGO]**

> Cinco lecciones y termino.
>
> **Una. El grounding es el ochenta por ciento del resultado.**
> El modelo lo compra cualquiera. **Tu documentación no.** Ahí está la ventaja, y ahí está el trabajo.
>
> **Dos. Un agente que escribe sin otro que lo critique es una máquina de generar problemas, muy rápido.**
> El crítico no es un lujo. Es lo que hace que el sistema sirva.
>
> **Tres. Exigí evidencia.** Si no puede señalarte de dónde lo sacó, no lo sabe: lo está sonando bien.
> Y esto vale para la IA y —dicho con cariño— para las personas también.
>
> **Cuatro. Automatizá el juicio, no la decisión.**
> Que el sistema junte la evidencia, la contraste y te la ponga delante. La decisión la firma alguien.
>
> **Cinco. Medí antes de optimizar. Y desconfiá de tu propia medición.**
> El caso del proceso nocturno enseñó que el número más peligroso no es el que está mal.
> **Es el que nunca se midió y todos damos por bueno.**

**[PANTALLA]** Última. Solo texto.

**[DIGO]**

> Y el cierre.
>
> Esto **no sustituyó a nadie**.
> Lo que hizo fue mover el trabajo del equipo. Desde *escribir la primera versión*, hacia *juzgar la primera versión*.
>
> Y resulta que **juzgar es exactamente donde alguien con experiencia vale más**.
>
> El primer borrador lo puede hacer un fichaje brillante con memoria de pez.
> Pero saber que la medición está incompleta, que esa prueba no prueba nada, y que esa frase de la documentación es ambigua…
>
> **eso todavía no lo hace ninguna máquina.**
>
> Gracias. Ahora sí, den la vuelta al papel. Preguntas.

---
---

# ANEXOS

## A. Preguntas que te van a hacer

**"¿Y yo, que no programo, esto para qué lo uso?"**
> *(La más probable en una sala mixta. No la contestes con condescendencia.)*
> Para tres cosas, hoy mismo. **Una:** preguntarle a tus propios documentos. Metés los contratos, los procedimientos, los informes, y preguntás en lenguaje normal, con citas. Para quien no programa, esto es de lejos lo de mayor impacto. **Dos:** primeros borradores — informes, actas, correos difíciles. Nunca la versión final; siempre el borrador que después trabajás. **Tres:** transcribir y resumir reuniones. Eso ya está resuelto, es baratísimo y devuelve horas cada semana.

**"¿Esto nos va a sustituir?"**
> No a corto plazo, y te digo por qué en concreto. La IA es buenísima produciendo el primer borrador y malísima sabiendo si ese borrador está bien. En nuestro caso, **el cien por cien de los primeros planes fue rechazado** por el revisor.
> Lo que sí cambia es en qué parte del trabajo pasás el día: menos escribir desde cero, más juzgar y decidir. **El que sabe juzgar, gana. El que solo sabe teclear, tiene que aprender a juzgar.**

**"¿Y si mete un error en producción?"**
> Por eso ninguna acción irreversible pasa sin firma humana. El agente prepara, propone y justifica. Lo que toca producción lo autoriza una persona. Y las puertas de calidad son binarias: compila o no compila, la prueba pasa o no pasa. No hay "quedó mejor".

**"¿Cuánto cuesta?"**
> Depende del modelo y del volumen, y es bastante menos de lo que la gente imagina. Pero sin tope se puede ir de las manos. Se controla con tres cosas: modelo por defecto sensato, tope mensual por proyecto, y ver el coste de cada ejecución.
> **[NOTA] Si tenés cifras reales de coste por tarea o por mes, este es EL momento. Si no las tenés, decilo y no improvises un número.**

**"¿Nuestros datos van a entrenar al modelo?"**
> En los planes de empresa, no: el contrato lo prohíbe explícitamente. En las versiones gratuitas, sí pueden. No son el mismo producto aunque se llamen igual. Y para lo verdaderamente sensible existe la opción de modelo local, donde el dato no sale nunca de casa.

**"¿Qué modelo es el mejor?"**
> Es la pregunta equivocada, y no lo digo por soberbia: cambia cada dos meses. La pregunta correcta es **de qué tamaño lo necesitás**. Empezá por el mediano. Bajá si es masivo. Subí solo si el mediano te falló.

**"¿Por dónde empiezo mañana?"**
> Por algo **reversible** y que ya estés haciendo. Si programás: el asistente dentro del editor, esta semana. Si no: cargá tus documentos y hacé una semana de preguntas reales.
> Y aplicá dos reglas de las seis: la cuatro (por pasos) y la cinco (verificá lo verificable).

**"¿Cuánto tiempo llevó montar el flujo de Pacífico?"**
> **[NOTA] Completá con el dato real. Y si el número es grande, no lo escondas: refuerza el mensaje de "el trabajo no está en el modelo, está alrededor". Un número honesto y grande es más creíble que uno pequeño y sospechoso.**

---

## B. Plan B de recortes

**Bloque 1** — en este orden:
1. **Sección 7 (modelos)** → de 5 min a 2. Decís solo los tres tamaños y la regla del becario/analista/socio. Los nombres están en la chuleta.
2. **Sección 6 (la escalera)** → contá solo el escalón 1 y el 3. Se entiende igual.
3. **"Cuándo NO usar IA"** → de cuatro puntos a dos: cálculo exacto y "si no lo podés verificar".
4. **NUNCA recortes:** la sección 4 (el fichaje nuevo), la sección 5 (dónde se rompe), la alucinación, la matriz y las 6 reglas. Es todo lo que la gente se lleva a la oficina.

**Bloque 2** — en este orden:
1. **Frente A (documentación)** → de 1 min a 20 segundos: "no había documentación utilizable, se reconstruyó, y esa documentación es el combustible de todo".
2. **El detalle del bucle 1** → nombrá los seis agentes rápido y salta al pipeline de cuatro pasos.
3. **De las siete dificultades, contá cuatro:** falso verde, confianza asimétrica, fricción del primer día, resistencia.
4. **NUNCA recortes:** el fallo del punto de entrada, el "7 de 7 rechazados", el falso verde, el "baseline incompleto" y el cierre.

---

## C. Checklist previo (hacer el 04/08)

- [ ] Refrescar nombres y versiones de modelos (bloque 1, sección 7).
- [ ] **Actualizar el estado del proceso de Pacífico:** ¿hubo corrida completa en verde? ¿número real hoy?
- [ ] Conseguir, si existe, una cifra de coste real.
- [ ] Conseguir el tiempo real de montaje del flujo.
- [ ] **Imprimir la chuleta** (`CHULETA_1_PAGINA.md`), una por asistente. Repartir **boca abajo** al entrar.
- [ ] Ensayar el bloque 2 con cronómetro. Es el que se pasa.
- [ ] Ensayar la sección 4 en voz alta. Es la más larga hablada y la más importante.
- [ ] **Decidir si hacés demo en vivo. Recomendación: no, o solo un vídeo corto ya grabado.** Una demo que falla delante de treinta personas te destruye los veinte minutos, y el mensaje no necesita demo.
- [ ] Llevar las cifras del caso apuntadas, no de memoria: 95 min · 27 M registros · 2.400.057 ms · 13 hallazgos · 2 bloqueantes · 7 de 7 rechazados.

---

## D. Frases-ancla

Las que querés oír repetidas en el pasillo:

1. *"No busca. Predice."*
2. *"La IA nunca suena insegura."*
3. *"El contexto vale más que el prompt."*
4. *"Saber cocinar es el modelo. La receta de tu casa es la skill."*
5. *"Si no lo podés escribir, tampoco lo vas a poder automatizar."*
6. *"La IA amplifica la calidad de tu documentación. Para bien y para mal."*
7. *"El control se prueba contra el defecto: si no lo viste fallar, no sabés si funciona."*
8. *"El agente prepara. La persona firma."*
9. *"Juzgar es exactamente donde el senior vale más."*
