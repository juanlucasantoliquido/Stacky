# Guion — Sesión de IA · Reunión presencial de equipo
**Fecha:** miércoles 05/08/2026 · **Expositor:** Juan Luca Santoliquido
**Bloque 1:** Conceptos básicos de IA — 45 min
**Bloque 2:** Caso de éxito Tech (flujo agéntico RS + Pacífico) — 20 min
**Audiencia:** mixta técnica / no técnica. **Supuesto de trabajo: nadie sabe nada de IA.**

> Cómo leer este documento
> - **[HABLADO]** = lo que decís, en lenguaje hablado. No es para leer palabra por palabra, es para que tengas el tono y el orden.
> - **[SLIDE]** = qué se ve en pantalla mientras decís eso.
> - **[NOTA]** = recordatorio para vos, no se dice.
> - **⏱** = marca de tiempo acumulada. Si vas atrasado, mirá el bloque "Plan B de recortes" al final.

---

# BLOQUE 1 — CONCEPTOS BÁSICOS DE IA (45 min)

## 0. Apertura y contrato de la sesión — 3 min ⏱ 0:00 → 0:03

**[SLIDE]** Solo el título: *"IA: de qué estamos hablando realmente"*. Nada más.

**[HABLADO]**

> Antes de arrancar quiero hacer tres preguntas y les pido que levanten la mano de verdad, aunque dé un poco de vergüenza.
>
> Primera: ¿quién usó alguna herramienta de IA esta semana? ChatGPT, Copilot, Gemini, lo que sea.
> *(esperar, contar con la vista)*
>
> Segunda: ¿quién la usó para algo del trabajo, no para una receta de cocina o un mail personal?
> *(esperar)*
>
> Tercera, y esta es la importante: ¿quién se fio del resultado sin revisarlo?
> *(esperar — normalmente bajan casi todas las manos)*
>
> Bueno. Esa diferencia entre la segunda y la tercera mano levantada es exactamente de lo que vamos a hablar hoy.
>
> Les hago un contrato para estos 45 minutos. **No los voy a convertir en expertos en IA.** No se puede y además no hace falta. Lo que quiero es que salgan de acá con tres cosas:
>
> 1. Que puedan entrar a cualquier conversación donde se hable de IA y **entender todas las palabras**. Que nadie diga "agente", "RAG" o "contexto" y ustedes tengan que asentir sin saber.
> 2. Que sepan **elegir la herramienta correcta** para lo que necesitan hacer. Porque hoy hay veinte, y usar la equivocada es la forma más rápida de concluir que "la IA no sirve".
> 3. Que sepan **cuándo desconfiar**. Esta es la más importante de las tres.
>
> Y una aclaración: voy a explicar todo como si nadie supiera nada. Si a alguien le parece básico, que tenga paciencia diez minutos, porque después subimos. Y si en algún momento digo una palabra que no se entiende, **me frenan ahí mismo**. No al final. Ahí mismo. Si una palabra no se entiende, todo lo que viene después tampoco.

**[NOTA]** Si el grupo es tímido y no levanta la mano, no insistas: seguí con "por lo que veo, la respuesta es la de siempre". No pierdas 40 segundos ahí.

---

## 1. ¿Qué es "la IA"? Las muñecas rusas — 5 min ⏱ 0:03 → 0:08

**[SLIDE]** Círculos concéntricos: **IA ⊃ Machine Learning ⊃ Deep Learning ⊃ IA Generativa ⊃ LLM**

**[HABLADO]**

> Cuando alguien dice "IA" hoy, en el 95% de los casos está hablando de una cosa muy específica, pero el término es enorme. Vamos de afuera hacia adentro, como muñecas rusas.
>
> **Inteligencia Artificial** es el círculo grande, y es un campo académico que tiene setenta años. Es de los años 50. La definición es simple: que una máquina haga algo que, si lo hiciera una persona, diríamos que hace falta inteligencia. El corrector ortográfico del Word es IA. El GPS que te calcula la ruta más rápida es IA. El filtro de spam es IA. Nada de eso es nuevo ni impresionante.
>
> Adentro está el **Machine Learning**, aprendizaje automático. Y acá está el primer cambio de mentalidad importante. La programación de toda la vida es: yo escribo las reglas, la máquina las ejecuta. "Si el importe es mayor a mil, pedí autorización." Yo escribí esa regla.
> El Machine Learning da vuelta la cosa: yo **no** escribo las reglas. Le muestro diez mil ejemplos de correos que son spam y diez mil que no lo son, y el programa **deduce solo** cuáles son las reglas. Nadie le dijo "si dice VIAGRA en mayúsculas, es spam". Lo dedujo.
>
> Más adentro, **Deep Learning**: es machine learning hecho con redes neuronales de muchas capas. La palabra "neuronal" está inspirada en el cerebro pero muy de lejos — no es un cerebro, es matemática con muchas capas. Lo que importa: es la técnica que hizo que esto empezara a funcionar en serio, más o menos desde 2012.
>
> Más adentro todavía, la **IA Generativa**. Toda la IA anterior *clasificaba* o *predecía*: esto es spam / no es spam, esta casa vale tanto. La IA generativa **crea contenido nuevo**: texto, imágenes, código, voz, video. Esto es lo que explotó públicamente a fines de 2022 con ChatGPT.
>
> Y en el centro, el **LLM**: *Large Language Model*, modelo grande de lenguaje. Es el motor que está detrás de ChatGPT, de Claude, de Gemini, de Copilot. Y de esto vamos a hablar el resto de la sesión, porque es el 90% de lo que hoy nos afecta en el trabajo.

**[SLIDE]** Frase sola, grande: **"No busca. Predice."**

**[HABLADO]**

> Ahora la parte que quiero que se lleven aunque se olviden de todo lo demás.
>
> Un LLM, en el fondo, es un **autocompletar**. El mismo del teclado del móvil, ese que te sugiere la palabra siguiente. Solo que este fue entrenado con prácticamente todo el texto público que hay en internet, y es tan enorme que, para poder predecir bien la palabra siguiente, tuvo que aprender de paso gramática, lógica, estructura de argumentos, algo parecido al razonamiento, y una cantidad brutal de conocimiento del mundo.
>
> Pero sigue siendo eso: **una máquina de predecir qué viene después**.
>
> Y de acá se desprende la frase más importante de toda la charla: **un LLM no busca información, la predice.** No es Google. No tiene una base de datos adentro donde va a buscar el dato y te lo trae. Genera la respuesta que le parece más probable dada tu pregunta.
>
> Esa sola frase explica el 90% de las cosas raras que hace la IA, y las vamos a ir viendo una por una.

---

## 2. Cómo funciona por dentro, sin matemática — 6 min ⏱ 0:08 → 0:14

**[SLIDE]** Seis conceptos en lista, se van revelando de a uno: Token · Entrenamiento vs. Uso · Ventana de contexto · Sin memoria · Fecha de corte · No es determinista.

**[HABLADO]**

> Seis cosas de cómo funciona. Son seis y son todas cortas.
>
> **Uno: el token.** El modelo no ve palabras, ve *tokens*, que son pedacitos de palabra. Más o menos cuatro caracteres, o tres cuartos de una palabra. "Inteligencia" pueden ser tres tokens. Es un detalle técnico, pero importa por una razón muy práctica: **todo se mide y se cobra en tokens**. Cuando alguien dice "esta ejecución costó cuarenta céntimos", está contando tokens de entrada y de salida. Y cuando alguien dice "un millón de tokens de contexto", está diciendo unas 750.000 palabras, que son siete u ocho libros.
>
> **Dos: entrenar no es lo mismo que usar.** Entrenar un modelo grande cuesta cientos de millones de euros, tarda meses, y lo hacen cinco empresas en el mundo. Usarlo cuesta céntimos y tarda segundos. Es como la diferencia entre la carrera de medicina y la consulta de veinte minutos. Nosotros nunca vamos a entrenar un modelo. Nosotros lo *usamos*. Esa parte se llama **inferencia**, por si la escuchan.
>
> **Tres: la ventana de contexto.** Es la memoria de trabajo de la conversación. Todo lo que le pasás —tu pregunta, los documentos que le pegás, lo que él va escribiendo— entra en una ventana de tamaño fijo. Cuando se llena, se empieza a olvidar del principio. Hoy los modelos van desde ventanas chiquitas hasta uno o dos millones de tokens. Por eso a veces, en una conversación larguísima, el modelo "se olvida" de algo que le dijiste al principio. No se distrajo: se le cayó de la ventana.
>
> **Cuatro, y esta sorprende a todo el mundo: no tiene memoria.** Cada conversación arranca de cero. El modelo no se acuerda de vos, no se acuerda de la charla de ayer, no aprende de lo que le corregiste. Cuando ChatGPT "recuerda" tu nombre, es porque hay un sistema alrededor que guardó una nota en un archivo y se la vuelve a pegar al principio de cada charla. **La memoria no es del modelo, es de la aplicación que lo envuelve.** Esto va a ser importante después.
>
> **Cinco: fecha de corte.** El modelo se entrenó hasta cierta fecha y de ahí en adelante no sabe nada. Si le preguntás por algo de la semana pasada, o te dice que no sabe, o —peor— **te lo inventa**. Salvo que la herramienta que estás usando tenga acceso a internet o a tus documentos, que es otra cosa que vemos enseguida.
>
> **Seis: no es determinista.** Le hacés dos veces la misma pregunta y te da dos respuestas distintas. No es un error, es de diseño: hay algo de azar controlado en cómo elige cada palabra. El parámetro que controla eso se llama **temperatura**: baja, respuestas más predecibles y aburridas; alta, más creativas y más impredecibles. Para código y datos querés temperatura baja. Para lluvia de ideas, alta.

**[SLIDE]** Grande, en rojo: **"ALUCINACIÓN"** — subtítulo: *decir algo falso con total seguridad*

**[HABLADO]**

> Y ahora el concepto que más les va a servir en la vida real: **la alucinación**.
>
> Un modelo alucina cuando dice algo que es falso, pero lo dice con una seguridad absoluta. Te inventa una función que no existe en la librería. Te inventa una tabla que no está en la base. Te inventa un artículo de una ley. Te inventa una cita de un paper con autor y año.
>
> ¿Por qué pasa? Volvemos a la frase de antes: **su trabajo es que suene bien, no que sea cierto.** Está prediciendo qué texto es más probable. Y una función que no existe pero que *podría* existir, encaja perfecto en la predicción.
>
> Y acá está lo peligroso, y quiero que se lo lleven grabado: **la IA nunca suena insegura.** Cuando tiene razón y cuando se la está inventando, el tono es exactamente el mismo. Un compañero que no sabe algo duda, se le nota en la cara, dice "creo que...". La IA no. Va a decir la barbaridad más grande con la misma calma con la que te dice dos más dos.
>
> **Toda la duda la tenés que poner vos.** Ese va a ser el hilo conductor de la segunda parte de la charla.

---

## 3. El diccionario: los términos que hay que conocer — 9 min ⏱ 0:14 → 0:23

**[NOTA]** Este es el bloque que pidieron explícitamente. No lo recites como lista: agrupá en cuatro familias y decí para qué sirve cada término. Si alguna pregunta te lleva demasiado tiempo, decí "eso lo vemos en el bloque de buenas prácticas".

**[SLIDE]** Cuatro columnas: *Cómo le hablás · Cómo le das conocimiento · Cómo le das manos · Cómo lo medís*

**[HABLADO]**

> Vamos con el diccionario. Son unos veinte términos, pero los voy a agrupar en cuatro familias para que no sea una lista suelta. Las cuatro familias son: cómo le hablás, cómo le das conocimiento, cómo le das manos, y cómo lo medís.

### Familia 1 — Cómo le hablás

> **Prompt.** La instrucción que le das. Nada más que eso. "Prompt" quedó como palabra de moda pero significa "lo que le pediste".
>
> **Ingeniería de prompt.** Suena grandilocuente. Es aprender a pedir bien: dar contexto, ser específico, decir el formato que querés. Es el 90% de la diferencia entre "esto no sirve" y "esto es una máquina".
>
> **System prompt** o instrucciones de sistema. Son las reglas permanentes que no ves: quién es el asistente, cómo se comporta, qué no puede hacer. Es la diferencia entre un modelo pelado y "el asistente de atención al cliente de la empresa". El usuario escribe el prompt; la empresa escribe el system prompt.
>
> **Contexto.** Todo el material que le pasás junto con la pregunta: el documento, el código, el ticket, la conversación anterior. **Regla de oro de toda la charla: el contexto vale más que la astucia del prompt.** No existe la frase mágica. Existe darle el material correcto.
>
> **Few-shot.** Darle uno, dos o tres ejemplos de cómo se ve una respuesta buena. "Mirá, cuando te doy esto, quiero que me devuelvas esto." Es la técnica más barata y más efectiva que hay, y casi nadie la usa. Su opuesto es **zero-shot**: pedirle sin ningún ejemplo.
>
> **Razonamiento** o *chain of thought*. Pedirle que piense paso a paso antes de responder. Hay modelos que ya hacen esto por diseño: se toman unos segundos "pensando" antes de contestar. Son mejores en matemática, lógica y problemas difíciles, y son más lentos y más caros. Se los llama **modelos razonadores**.

### Familia 2 — Cómo le das conocimiento (que no tiene)

**[SLIDE]** Tres cajas comparadas: *Fine-tuning · RAG · Grounding*

> Este es el bloque donde se equivoca más gente, incluida gente técnica. El problema a resolver es: el modelo no conoce nuestros datos. ¿Cómo se los damos? Hay tres caminos y **no son intercambiables**.
>
> **Fine-tuning** (afinado). Agarrás un modelo ya entrenado y le hacés un entrenamiento extra con tus datos. Suena a la solución obvia y casi siempre **no lo es**: es caro, es lento, y en el momento en que cambian tus datos, se te desactualizó y hay que volver a hacerlo. Sirve para enseñarle **estilo y formato** —"quiero que escribas como escribimos nosotros"—, no para enseñarle **hechos**.
>
> **RAG.** Se lee "rag", es *Retrieval Augmented Generation*. La idea es sencillísima: cuando el usuario pregunta algo, primero **buscás** en tus documentos los pedazos relevantes, y esos pedazos se los **pegás al prompt** junto con la pregunta. El modelo responde leyendo eso, no de memoria. Es lo que hay debajo del 95% de los "chatbots que responden sobre nuestra documentación". Es barato, se actualiza al instante y —clave— **puede citar de dónde sacó cada cosa**.
> La analogía: fine-tuning es mandarlo a estudiar cinco años; RAG es dejarlo dar el examen con los apuntes abiertos. Para hechos, casi siempre querés los apuntes abiertos.
>
> **Embeddings** y **base vectorial**. Es la maquinaria que hace posible el RAG. Un embedding convierte un texto en una lista de números —una coordenada— de forma que dos textos que *significan* lo mismo quedan cerca en el espacio, aunque no compartan una sola palabra. Por eso "cómo doy de baja mi póliza" encuentra el documento que habla de "cancelación de contrato". Busca por significado, no por palabra exacta. La base vectorial es donde se guardan esas coordenadas.
>
> **Grounding** (anclaje). Es el término paraguas y **el más importante de esta familia**: obligar al modelo a apoyarse en hechos verificables en vez de en lo que recuerda. RAG es una forma de grounding. Darle acceso a la base de datos es grounding. Obligarlo a citar archivo y línea es grounding.
> Se los subrayo ahora porque **el caso que voy a contar en la segunda parte es, entero, una historia sobre grounding.**

### Familia 3 — Cómo le das manos (acá empieza lo interesante)

**[SLIDE]** Escalera de 4 peldaños: *Modelo → + Herramientas → + Bucle = Agente → Multiagente*

> Hasta acá el modelo solo habla. Ahora le damos manos.
>
> **Herramienta**, *tool*, o *function calling*. Es la capacidad del modelo de decir "che, para contestar esto necesito que ejecutes esta función y me devuelvas el resultado". Y el sistema la ejecuta de verdad: lee un archivo, consulta una base, llama a una API, corre un test. En ese momento deja de ser un chat y empieza a poder **hacer cosas**. Este es el salto conceptual más grande de los últimos dos años.
>
> **MCP** (*Model Context Protocol*). Un estándar para enchufar modelos con herramientas y con fuentes de datos. La analogía es el USB: antes cada aparato traía su cable propio; ahora hay un enchufe estándar. Sin esto, cada combinación de modelo y herramienta hay que programarla a mano.
>
> **Skill** (habilidad). Un procedimiento empaquetado que el modelo carga cuando hace falta. No es conocimiento general: es **cómo se hace algo acá adentro**. "Cómo redactamos NOSOTROS un changelog." "Cómo se critica un plan en este equipo." "Cuáles son los pasos de nuestro despliegue."
> La diferencia con el conocimiento del modelo: lo que aprendió en internet es como una carrera universitaria; una skill es el manual de procedimientos de la empresa. Nadie espera que un fichaje nuevo, por muy bueno que sea, adivine el procedimiento interno. Se lo das escrito. Con la IA es idéntico.
>
> **Agente.** Acá está la palabra que todo el mundo usa y casi nadie define. Un agente es tres cosas juntas:
> 1. un modelo,
> 2. con **herramientas** para actuar sobre el mundo real,
> 3. y un **bucle**: mira el estado, decide, actúa, mira el resultado, corrige y vuelve a empezar, hasta que termina el objetivo o se rinde.
>
> **La diferencia entre un chatbot y un agente es que el chatbot te contesta y el agente te lo hace.** Un chatbot te explica cómo arreglar el bug. Un agente abre el repositorio, encuentra el archivo, hace el cambio, corre los tests, ve que fallan, corrige y vuelve a correrlos.
>
> **Subagente.** Un agente que lanza a otro agente para una parte del trabajo, con su propio contexto limpio. Sirve para dos cosas: no ensuciar la ventana de contexto del principal, y poder hacer cosas en paralelo.
>
> **Sistema multiagente** u **orquestación**. Varios agentes especializados trabajando en cadena o en paralelo, cada uno con su rol. Uno propone, otro critica, otro implementa, otro verifica. Esto es exactamente lo que vamos a ver en la segunda parte.
>
> **Guardrails** (barandillas). Los límites duros del sistema. Qué no puede tocar, qué necesita aprobación, qué está directamente prohibido. Sin barandillas no hay agente en producción, hay una ruleta.
>
> **Human-in-the-loop.** "Humano en el bucle". Que haya una persona que aprueba antes de que pase algo irreversible. Es el principio de diseño más importante de todo lo que voy a mostrar después, y no es negociable: **el agente prepara, la persona firma.**
>
> **Autonomía.** El eje que ordena todo esto. Va de "me sugiere y yo hago" hasta "lo hace solo y me avisa". Y quiero que quede clarísimo: **es una perilla, no un interruptor**. La pregunta correcta nunca es "¿le doy autonomía o no?". Es "¿cuánta autonomía, para qué tarea, y con qué red de seguridad?".

### Familia 4 — Cómo lo medís

> **Benchmark.** Exámenes estandarizados para comparar modelos. Sirven para orientarse, pero ojo: los modelos nuevos salen entrenados apuntando a esos exámenes, así que se saturan y se "gamean". **El único benchmark que importa de verdad es el tuyo, con tus casos reales.**
>
> **Evals** (evaluaciones). Justamente eso: tu propio banco de casos, con la respuesta correcta conocida, para poder medir si un cambio mejoró o empeoró las cosas. Si van a meter IA en un proceso serio, esto no es opcional.
>
> **Drift** (deriva). Que la calidad se te vaya moviendo con el tiempo, porque cambió el modelo, cambiaron tus datos o cambió el uso. Por eso hay que medir de forma continua, no una sola vez el primer día.

**[NOTA]** Si el reloj aprieta, la Familia 4 se puede contar en 40 segundos: "hay benchmarks públicos, no te fíes del todo, armá los tuyos". Nadie te lo va a reclamar.

---

## 4. De chatbot a agente: la escalera — 4 min ⏱ 0:23 → 0:27

**[SLIDE]** Cuatro escalones con un ejemplo concreto en cada uno.

**[HABLADO]**

> Voy a poner los conceptos anteriores en una escalera con un ejemplo real, para que se vea el salto.
>
> **Escalón 1 — Chat.** Le pregunto "¿cómo hago un DELETE con JOIN en SQL Server?". Me contesta. Yo copio, yo pego, yo pruebo. Toda la responsabilidad y todo el trabajo siguen siendo míos. Esto es el 90% de lo que la gente usa hoy.
>
> **Escalón 2 — Asistente integrado.** El modelo está metido dentro de la herramienta donde trabajo y **ve mi contexto**. En el IDE ve el archivo abierto y me completa la función. En el correo ve el hilo y me redacta la respuesta. Menos copiar y pegar, y mucho mejores respuestas, porque ya no tengo que explicarle dónde estoy parado.
>
> **Escalón 3 — Agente.** Le digo: "el proceso batch de anoche terminó en error, averigua por qué". Y él: abre los logs, cruza contra el código, se da cuenta de en qué fase murió, corre una consulta contra la base para confirmar, y vuelve con el diagnóstico y la línea exacta. No me contestó una pregunta: **me hizo el trabajo de investigación**.
>
> **Escalón 4 — Sistema agéntico.** Varios agentes con roles distintos, y —esto es lo importante— **con desconfianza incorporada entre ellos**. Uno propone la solución, otro cuya única misión es encontrarle los agujeros la critica, un tercero la implementa, un cuarto audita que lo implementado sea de verdad lo que decía el plan.
>
> Y ese cuarto escalón es el que quiero contarles con un caso real en la segunda parte.

**[SLIDE]** La metáfora, con las cuatro líneas en pantalla.

**[HABLADO]**

> Antes de seguir, la metáfora que a mí me sirvió para explicarle esto a gente no técnica. Piensen en un becario:
>
> - **brillantísimo**: leyó más que cualquiera de nosotros y lee 500 páginas en tres segundos;
> - **con memoria de pez**: mañana no se acuerda de nada de hoy;
> - **que nunca dice "no sé"**: si no sabe, se lo inventa con una seguridad pasmosa;
> - **y que cobra veinte céntimos la hora**.
>
> Todo lo que se hace bien y todo lo que se hace mal con la IA sale de aceptar esas cuatro cosas **a la vez**. Si te olvidás de que es brillante, lo desaprovechás. Si te olvidás de que nunca dice "no sé", te comés un error en producción.

---

## 5. Tecnologías y modelos disponibles hoy — 8 min ⏱ 0:27 → 0:35

**[NOTA]** ⚠️ Refrescá nombres y versiones el día antes de la sesión. Este mercado cambia cada dos meses y quedar desactualizado en esta slide te resta credibilidad justo antes del caso. Lo que **no** cambia es la estructura de "tres tamaños" — anclá el mensaje ahí, no en los nombres.

**[SLIDE]** Tabla de familias: proveedor · nombre · para qué destaca · abierto/cerrado.

**[HABLADO]**

> Vamos al mapa del mercado. Lo importante no es memorizar nombres —cambian cada dos meses— sino entender **cómo está organizado**.
>
> Los grandes de propósito general:
>
> - **Anthropic — Claude.** Fuerte en código, en seguir instrucciones largas y complejas sin desviarse, y en trabajo agéntico. Es el que usamos en el flujo que voy a mostrar.
> - **OpenAI — GPT.** El más generalista y el de ecosistema más grande. Es el que casi todos conocen porque ChatGPT fue el que abrió la puerta.
> - **Google — Gemini.** Ventanas de contexto enormes y muy integrado con Workspace: Docs, Gmail, Drive.
> - **Meta — Llama.** Abierto: te lo podés descargar y correrlo en tu propia infraestructura. Menos potente que los cerrados de primera línea, pero **tus datos no salen de tu casa**.
> - **Mistral** (europeo), **DeepSeek** y **Qwen**: abiertos o muy baratos, y sorprendentemente buenos. Presionan los precios hacia abajo de todo el mercado.
>
> Y los especializados, que no son modelos de texto:
> - **Imagen**: Midjourney, DALL·E, Stable Diffusion, Flux.
> - **Voz**: Whisper para transcribir —esto está resuelto y es baratísimo—, ElevenLabs para generar voz.
> - **Video**: existe, mejora rápido, todavía no es una herramienta de trabajo estable.

**[SLIDE]** Grande, tres cajas: **Pequeño/rápido · Medio · Grande/razonador**

**[HABLADO]**

> Ahora, la parte que sí quiero que se lleven, porque es la que no caduca.
>
> **Todas las familias tienen exactamente los mismos tres tamaños**, cambia el nombre comercial:
>
> **Pequeño y rápido y barato.** Los que se llaman Haiku, mini, Flash, Lite. Sirven para tareas masivas y simples: clasificar diez mil registros, extraer campos de un documento, resumir. Cuestan una fracción y responden al instante.
>
> **Medio.** Sonnet, GPT estándar, Pro. Es **el caballo de batalla**. El 90% del trabajo real se hace acá y es donde está la mejor relación calidad-precio.
>
> **Grande / razonador.** Opus, las series de razonamiento, Ultra. Para problemas genuinamente difíciles: diseñar una arquitectura, diagnosticar algo que nadie entiende, escribir un plan de cambio complejo. Son más lentos y bastante más caros.
>
> **La regla práctica, que es una sola frase: empezá siempre por el del medio. Bajá al pequeño si la tarea es masiva y repetitiva. Subí al grande solo cuando el del medio ya te falló.**
>
> El error típico de todo el que empieza es usar siempre el más caro "por las dudas". Es como ir a comprar el pan en un camión. Y el error contrario, usar siempre el más barato, es peor todavía: te da respuestas de peor calidad y te hace pensar que la IA no sirve.

**[SLIDE]** Dos columnas: *En la nube · En nuestra casa*

**[HABLADO]**

> Otra decisión: nube o local.
>
> **Nube.** Mejor calidad, cero infraestructura, pagás por uso. La pregunta que hay que hacer siempre es **qué pasa con nuestros datos**. Y acá una aclaración importante porque genera mucho miedo: en los planes **de empresa** de los grandes proveedores, el contrato dice explícitamente que **no entrenan con tus datos**. En las versiones gratuitas de consumidor, sí pueden hacerlo. **No son el mismo producto aunque se llamen igual.** Esa distinción sola resuelve la mitad de las discusiones sobre confidencialidad.
>
> **Local.** Te bajás un modelo abierto y lo corrés en tus servidores. Los datos no salen nunca, no pagás por uso. A cambio necesitás GPU, alguien que lo mantenga, y la calidad está uno o dos escalones por debajo. Para datos verdaderamente sensibles, es el camino.

**[SLIDE]** Herramientas concretas, agrupadas por perfil.

**[HABLADO]**

> Y las herramientas concretas, que es lo que se van a encontrar el lunes:
>
> **Si escribís código:**
> - **GitHub Copilot**: autocompletado y chat dentro del IDE. Es el escalón 2 de la escalera.
> - **Cursor / Windsurf**: editores enteros construidos alrededor de la IA.
> - **Claude Code / Codex CLI**: agentes de terminal que trabajan sobre el repositorio completo. Esto es el escalón 3, y es de otra categoría: no te completa una línea, te hace un cambio de veinte archivos.
>
> **Si no escribís código:**
> - **Copilot 365 / Gemini en Workspace**: la IA metida en Word, Excel, correo, reuniones.
> - **NotebookLM** o similares: le das tus documentos y le preguntás sobre ellos, con citas. Es RAG servido en bandeja, sin programar nada, y para gente no técnica es probablemente **la herramienta de mayor impacto inmediato** que existe hoy.
> - **Transcripción automática de reuniones**: resuelto, barato, y ahorra horas todas las semanas.

---

## 6. Buenas prácticas: qué usar para qué — 8 min ⏱ 0:35 → 0:43

**[SLIDE]** La matriz. Que quede en pantalla mientras hablás — es la slide que la gente fotografía.

| Lo que necesito hacer | Lo que uso | Lo que NO uso |
|---|---|---|
| Redactar, reformular, resumir un texto | Chat genérico (el del medio) | Nada más caro |
| Preguntar sobre **nuestros** documentos | RAG / chat con documentos + citas | El chat pelado: te lo inventa |
| Escribir código en el archivo que tengo abierto | Asistente de IDE (Copilot) | Un agente: es matar moscas a cañonazos |
| Cambiar 40 archivos con un mismo criterio | Agente sobre el repositorio | El chat: copiar y pegar 40 veces |
| Clasificar o extraer datos de 10.000 registros | Modelo pequeño por API | El razonador: 50× el precio, mismo resultado |
| Diseñar arquitectura, diagnosticar algo raro | Modelo razonador | El pequeño: te va a dar algo plausible y flojo |
| Cálculo exacto, cuadrar cifras | SQL, Excel, una calculadora | **Cualquier LLM** |
| Datos personales o de cliente | Plan de empresa con contrato, o modelo local | La versión gratuita de consumo |

**[HABLADO]**

> Esta tabla es la que les recomiendo fotografiar. Un par de comentarios sobre las filas que más se equivocan:
>
> La fila de **cálculo exacto** es la que más sorprende. Los LLM son **malos en aritmética**. Piénsenlo: están prediciendo texto, no calculando. Si necesitás que cuadren cifras, que el modelo escriba la consulta o la fórmula, y que el cálculo lo haga la base de datos o el Excel. Nunca le pidas que sume él.
>
> Y la fila de **datos sensibles**: la regla mental más simple que conozco es *"¿esto lo pondría en un correo a un proveedor externo?"*. Si la respuesta es no, no lo pegues en un chat de IA de consumo.

**[SLIDE]** Las 7 reglas, numeradas y sin adornos.

**[HABLADO]**

> Y ahora siete reglas prácticas. Son siete frases y valen para técnicos y para no técnicos por igual.
>
> **1. Contexto antes que astucia.** El prompt mágico no existe. Lo que cambia el resultado de forma brutal es el **material** que le das. Pegale el documento. Pegale el correo del cliente. Pegale el error completo, no el resumen que hiciste vos.
>
> **2. Pedí el formato.** "Devolvémelo como tabla con estas cuatro columnas" vale infinitamente más que "hacelo bien". El modelo no adivina qué formato querés, y si no se lo decís, elige uno cualquiera.
>
> **3. Dale ejemplos.** Uno o dos ejemplos de cómo se ve una respuesta buena. Es la técnica de mejor relación esfuerzo-resultado que existe y casi nadie la usa.
>
> **4. Trabajá en pasos, no en un salto.** No le pidas el resultado final de una. Primero que analice. Lo revisás. Después que proponga. Lo revisás. Después que ejecute. **Cada revisión intermedia es una alucinación que no llegó a producción.**
>
> **5. Verificá lo verificable.** Si te da un número, un nombre de archivo, una tabla, una función, una ley — pedile la fuente y comprobala. Suena obvio y es lo que menos se hace, justamente porque la respuesta *suena* muy bien.
>
> **6. Nada irreversible sin firma humana.** Borrar, enviar, tocar producción, subir a la rama principal, contestarle a un cliente. Que el agente lo prepare todo. La firma es tuya. Y la responsabilidad también, que es la otra cara de lo mismo.
>
> **7. Cuidá qué le das de comer.** Datos personales, credenciales, código de cliente. Ver la regla del correo al proveedor.

**[SLIDE]** *Cuándo NO usar IA* — cuatro puntos.

**[HABLADO]**

> Y para equilibrar, porque una charla de IA donde todo es maravilloso no hay que creérsela. **Cuándo no usar IA:**
>
> - Cuando la decisión tiene **responsabilidad legal o regulatoria**. Puede ayudarte a preparar, no puede decidir.
> - Cuando necesitás **exactitud numérica**. Ya lo dijimos.
> - Cuando **no vas a poder verificar** el resultado. Si no tenés forma de saber si está bien, no lo uses: estás delegando a ciegas.
> - Cuando **explicarle la tarea cuesta más que hacerla**. Existe y es más frecuente de lo que parece.

**[SLIDE]** Solo: *"La IA no duda. La duda la pones tú, en el proceso."*

**[HABLADO]**

> Y termino esta primera parte con el mito que quiero matar, porque me lo dicen todo el tiempo: *"la IA se equivoca, entonces no sirve"*.
>
> El compañero de al lado también se equivoca. Todos nos equivocamos. **La diferencia es que la persona duda, y avisa que duda.** La IA no. Va a estar igual de segura cuando acierta que cuando se lo inventa.
>
> Entonces la duda hay que ponerla en otro lado: en el **proceso**. Y eso es exactamente lo que vamos a ver en el caso: no un truco para que el modelo no se equivoque —eso no existe—, sino un **sistema diseñado para atrapar los errores del modelo antes de que lleguen a producción.**

---

## 7. Cierre del bloque 1 y transición — 2 min ⏱ 0:43 → 0:45

**[SLIDE]** Tres frases, una debajo de otra.

**[HABLADO]**

> Si de estos 45 minutos se olvidan de todo, quédense con tres frases:
>
> **Uno. No busca, predice.** Por eso alucina, por eso suena seguro, por eso hay que anclarlo a hechos.
>
> **Dos. El contexto vale más que el prompt.** Dale material, no busques la frase mágica.
>
> **Tres. La IA no duda. La duda la ponés vos, y mejor todavía si la ponés en el proceso y no en tu fuerza de voluntad.**
>
> Ahora les voy a mostrar cómo se ve todo esto cuando lo llevás a un proyecto real, con código real, con producción real, y con las cosas que salieron mal, que son las que más se aprenden.

---
---

# BLOQUE 2 — CASO DE ÉXITO TECH (20 min)

**[NOTA]** Tenés 20 minutos y es el bloque donde más fácil te pasás. Marcá con el reloj: si a los 10 minutos no arrancaste con Pacífico, saltá el detalle del pipeline y andá al caso.

## 1. El punto de partida — 2 min ⏱ 0:00 → 0:02

**[SLIDE]** Foto del problema: proyecto legacy, muchos años, documentación dispersa.

**[HABLADO]**

> Contexto para los que no están en el día a día de estos proyectos.
>
> RS es un producto con años encima, desplegado en varios clientes. Hay una capa web, hay procesos batch pesados que corren de noche contra bases enormes, y hay una base de datos con cientos de tablas y convenciones propias que no están escritas en ningún lado: están en la cabeza de la gente que lleva tiempo.
>
> El escenario típico: alguien nuevo entra, le dan un ticket, y tarda **semanas** en poder tocar algo con confianza. Y quien lleva tiempo, es cuello de botella de todo el mundo.
>
> El encargo no fue "usemos ChatGPT". El encargo fue mucho más incómodo: **¿podemos meter agentes dentro del ciclo real de desarrollo —sobre nuestros tickets, nuestra documentación y nuestro código— sin romper nada y sin que nadie firme a ciegas?**
>
> Spoiler: se puede, pero **el trabajo no está donde uno cree**. No está en el modelo. Está en lo que hay que construir alrededor del modelo.

---

## 2. El flujo agéntico de RS: dos bucles — 5 min ⏱ 0:02 → 0:07

**[SLIDE]** Bucle 1, la cadena de agentes sobre el ticket.

**[HABLADO]**

> El flujo tiene **dos bucles** y me interesa que se distingan, porque hacen cosas distintas.
>
> **Bucle 1: el ciclo de vida del ticket.** Una cadena de agentes especializados, cada uno con su rol, sus reglas y su acceso a la documentación y al código:
>
> - **Agente de Negocio**: toma el texto libre del cliente —un correo, una nota de reunión— y produce una épica estructurada.
> - **Agente Funcional**: la convierte en análisis funcional, con casos de uso y criterios.
> - **Agente Técnico**: baja eso a análisis técnico: qué módulos toca, qué tablas, qué procesos.
> - **Agente Desarrollador**: propone el cambio de código.
> - **Agente QA**: diseña y ejecuta la verificación.
> - **Agente Revisor**: revisa la pull request.
>
> Todo esto corre **sobre el gestor de tickets real** —Azure DevOps, Jira o Mantis— y el resultado vuelve al ticket como tarea o comentario. No es un chat aparte donde después hay que copiar y pegar: **entra y sale por donde el equipo ya trabaja**. Eso, que suena a detalle, es la mitad de la adopción.
>
> Y en cada salto entre agentes **hay una persona que aprueba**. El agente prepara, la persona firma.

**[SLIDE]** Bucle 2, el pipeline de planes: **Proponer → Criticar → Implementar → Supervisar**

**[HABLADO]**

> **Bucle 2**, y este es el que de verdad da la calidad. Es un pipeline de cuatro pasos, y cada paso lo hace **un agente distinto**:
>
> **Proponer.** Un agente escribe un plan detallado, dividido en fases, y cada afirmación tiene que estar **anclada a archivo y línea reales**. No vale "hay que tocar la capa de datos". Vale "hay que tocar tal archivo, línea 122".
>
> **Criticar.** Y acá está el corazón de todo. **Otro** agente, arrancando con contexto limpio, cuya única misión es ser **el juez adversarial**: abre los archivos citados y comprueba que existan y digan lo que el plan dice; busca contradicciones entre fases; comprueba que los criterios de aceptación sean binarios y no opiniones. Y emite un **veredicto binario**: aprobado o rechazado.
>
> **Implementar.** Recién ahí se toca código, fase por fase, con tests.
>
> **Supervisar.** Un cuarto agente audita que lo que se implementó sea realmente lo que decía el plan, y **corre los tests de verdad**, no lee que alguien escribió "tests OK".

**[SLIDE]** Grande: **7 de 7 planes rechazados en su primera versión.**

**[HABLADO]**

> Y les voy a dar el dato que mejor resume por qué esto funciona.
>
> En una de las series de trabajo, **el juez rechazó 7 de 7 planes en su primera versión**. Y en la serie en la que estoy ahora, un mismo plan lleva **dos rechazos consecutivos**, el segundo de un juez independiente que encontró siete puntos bloqueantes.
>
> Cuando conté esto la primera vez, alguien me dijo "entonces el generador es malo". No: **el generador es normal**. Un primer borrador de cualquier persona también tiene agujeros. La diferencia es que el borrador de una persona se revisa a veces, con prisa, y por alguien que ya está mentalmente comprometido con la solución.
>
> **El valor no está en que la IA escriba. Está en que otra IA le encuentre los agujeros antes que vos, sistemáticamente, todas las veces, sin cansarse y sin ego.**

**[SLIDE]** Tres pilares: *Grounding · Evidencia obligatoria · Puertas binarias*

**[HABLADO]**

> Tres cosas hacen que esto no sea humo. Y son tres cosas **caras**, esta es la parte que no se cuenta en las demos:
>
> **Uno, grounding.** Se reconstruyó un "manual agéntico" del proyecto: unos **40 documentos** técnicos y funcionales —arquitectura, capa web, capa de datos, batch, motor, base de datos, referencia de tablas, referencia de clases, referencia de páginas— con un índice maestro que el agente está **obligado a leer antes de tocar nada**. Sin eso, adivina. Y adivina muy convincentemente.
>
> **Dos, evidencia obligatoria.** Nada se afirma sin archivo y línea. Y va más lejos: los documentos llevan **marcas de confianza** — esto está verificado contra el código, esto es una inferencia, esto no se pudo verificar. **Que la documentación diga en voz alta qué parte de sí misma no es fiable** es una idea que me robaría para todos los proyectos, con IA o sin IA.
>
> **Tres, puertas binarias.** Compila o no compila. El test pasa o no pasa. La consulta devuelve el número esperado o no lo devuelve. **Nada de "quedó mejor".** Si el criterio de aceptación es una opinión, el agente siempre va a poder convencerte de que la cumplió.

---

## 3. Pacífico, en concreto — 7 min ⏱ 0:07 → 0:14

**[SLIDE]** Título: *Pacífico — tres frentes*

**[HABLADO]**

> Vamos a Pacífico. Tres frentes, del más barato al más difícil.

### Frente A — Reconstruir la documentación (2 min)

**[HABLADO]**

> El proyecto **no tenía documentación técnica utilizable**. Había cosas sueltas, viejas y contradictorias entre sí.
>
> Se reconstruyó desde el código: arquitectura, capa online, capa de datos, capa de negocio, sistema batch, motor, seguridad, convenciones de base y de código, y las referencias de tablas, clases y páginas. Con las marcas de confianza que decía antes.
>
> El beneficio obvio es que ahora una persona nueva se puede orientar. Pero el beneficio real, el que no se ve, es otro: **esa documentación es el combustible de todos los agentes.** Cada análisis funcional, cada análisis técnico, cada plan, sale de ahí.
>
> Y de paso —esto lo digo para los responsables de proyecto que estén escuchando— **documentar dejó de ser un gasto de conciencia y pasó a ser una inversión con retorno medible**, porque la calidad de la documentación se traduce directamente en la calidad de lo que produce el agente. Es la primera vez que veo ese argumento funcionar de verdad.

### Frente B — El fallo que nos enseñó todo (2 min)

**[SLIDE]** El error, tal cual: *"El punto de entrada de la carga es IncHost"* — con un tachón rojo.

**[HABLADO]**

> Ahora el error, porque es más instructivo que los aciertos.
>
> Una épica generada por el agente afirmaba que el punto de entrada del proceso de carga era **IncHost**, y usaba nombres de tabla con guiones bajos.
>
> Las dos cosas estaban mal. El punto de entrada real es **Mul2Bane**, que es el que toma los archivos del mandante. IncHost es el **segundo** paso. Y la convención de nombres de las tablas productivas no lleva guiones bajos.
>
> ¿Se lo inventó de la nada? **No.** Y esto es lo interesante. Fue a buscarlo a la documentación funcional, y ahí había una frase que decía, textualmente, que IncHost era "el punto de entrada principal". El agente la tomó **literal**.
>
> O sea: **no fue una alucinación aleatoria. Fue nuestra propia documentación ambigua, repetida con una seguridad que nosotros nunca le habríamos puesto.**
>
> Y la corrección tampoco fue tocar el modelo. Fue:
> - crear un **catálogo canónico de procesos** —los cuatro procesos, qué hace cada uno, cuál va primero— dentro del perfil del proyecto;
> - escribir la **regla de nomenclatura** de tablas de forma explícita;
> - y **recortar el alcance de los agentes**: el agente de negocio ya no puede fijar procesos técnicos ni tablas —no es su trabajo—, y el funcional sí puede, pero **leyendo el catálogo**, e identificando los procesos por su propósito, no por su nombre.
>
> La moraleja, y me parece la frase más importante de todo el caso: **la IA amplifica la calidad de tu documentación. Para bien y para mal.** Si tu documentación es ambigua, no vas a tener un agente confundido: vas a tener un agente **muy convincente** repitiendo tu ambigüedad a escala.

### Frente C — El caso duro: el batch en producción (3 min)

**[SLIDE]** Una línea de tiempo: *95 min → ERROR*, y debajo, los hallazgos.

**[HABLADO]**

> Y el frente que a mí más me gusta contar, porque no es "me hizo un CRUD".
>
> **El problema.** La corrida diaria del batch de carga en producción **terminaba en error**. 95 minutos, un rollback de **27 millones de filas** y 40 minutos de espera muerta. Y ya era la tercera vez que aparecía la misma familia de fallo, con dos intentos previos de arreglo que no habían llegado al fondo.
>
> **Qué hizo el flujo.**
>
> Primero, **instrumentación forense**. Antes de optimizar nada: medir. Con una regla que me parece de oro y que se la robo a quien la haya inventado: **la instrumentación no puede convertirse en el cuello de botella que está midiendo**. Nada de una escritura por fila; contadores en memoria y un volcado por fase.
>
> Segundo, con los datos ya medidos, el plan. Y acá los hallazgos, todos con evidencia de log y de CSV real:
>
> - La fase que fallaba murió a **exactamente 2.400.057 milisegundos**. Y el tiempo de espera configurado era de 2.400.000. Es decir: **no murió trabajando. Murió esperando.** Cuando el número que ves coincide al milisegundo con un valor de configuración, no estás mirando un problema de rendimiento, estás mirando un tope.
> - ¿Esperando qué? Espera por **paralelismo interno del motor** —más de 900 segundos acumulados— **con la base al 0% de CPU**. No era un bloqueo: los bloqueos sumaban 123 milisegundos en total. Estaba parada, esperándose a sí misma.
> - Y de paso, trabajo directamente inútil: **36 minutos** de borrados por lotes evitables, un UPDATE de casi **28 minutos** sobre 36 millones de filas, y un INSERT de **6 minutos que insertaba cero filas**. Seis minutos, todas las noches, para no hacer nada.
>
> **Y después vino el juez.** El plan se criticó de forma adversarial contra los logs y los CSV reales: **trece hallazgos, dos de ellos bloqueantes**. Uno: un script que el propio plan proponía estaba roto. Dos: una de las fases propuestas **volvía a sembrar el error que decía arreglar**. Las dos cosas se corrigieron **antes** de tocar producción.

**[SLIDE]** Grande: *"El baseline está incompleto."*

**[HABLADO]**

> Y ahora la parte que más orgullo me da, aunque suene raro.
>
> El propio plan lleva escrito, en mayúsculas, una advertencia: **el baseline está incompleto**. Porque las tres corridas instrumentadas murieron **antes** de llegar al final del proceso, así que hay un tramo cuya duración con volumen real **nunca se midió**. Y por lo tanto la proyección de bajar la ventana a unos 45 minutos es **una proyección, no un compromiso**, hasta que haya una primera corrida completa en verde que fije el baseline de verdad.
>
> Ese cartel no lo puse yo. **Lo puso el juez**, revisando el trabajo. Un consultor os habría vendido "reducción del 50%" en una diapositiva con una flecha verde.
>
> Y esa es exactamente la diferencia entre un sistema con IA que sirve y uno que te mete en un problema dentro de seis meses: **el que sirve te dice qué parte de lo que te está contando todavía no está probada.**

**[NOTA]** ⚠️ **Actualizá esto antes del 05/08:** estado actual del plan, si ya hubo corrida completa en verde, y el número real de la ventana hoy vs. los 95 min iniciales. Si hay número real, es tu mejor cierre del bloque. Si no lo hay, la honestidad del "baseline incompleto" también cierra muy bien — pero decilo como decisión, no como excusa.

---

## 4. Las dificultades de adopción (la parte honesta) — 4 min ⏱ 0:14 → 0:18

**[SLIDE]** Título: *Lo que salió mal*. Que se note que es un bloque entero, no una nota al pie.

**[HABLADO]**

> Me pidieron que hablara de las dificultades de la adopción y me alegra, porque es la parte útil. Siete, rápidas.

> **Uno: el falso verde. Este es el problema número uno, con diferencia.**
> El agente te dice "implementado, tests en verde"… y el test no estaba probando nada. Dos ejemplos reales, y son buenísimos:
> - Una orden de correr tests filtrando por un nombre que **no coincidía con ningún test**. Cero tests ejecutados. Y el resultado del comando es: **éxito**. Verde perfecto sobre la nada.
> - Un control automático de calidad que contaba coincidencias de texto en el código y que, por cómo estaba escrito, **premiaba exactamente el error que decía cazar**: cuanto peor estaba el código, más subía el contador hacia el objetivo.
>
> La contramedida que nos funcionó es una regla simple y **se aplica igual sin IA**: **el control se prueba contra el defecto.** Antes de creerle un verde, hay que **verlo en rojo** con el error presente. Si no lo viste fallar, no sabés si funciona.
>
> **Dos: "corregido" no es evidencia.** De catorce correcciones declaradas en un registro de cambios, **tres cerraban el síntoma y dejaban vivo el defecto**. La lección: no leas el resumen de lo que hizo, andá al cambio.
>
> **Tres: la confianza es asimétrica.** Un error espectacular te cuesta veinte aciertos. Por eso el **orden** de adopción importa muchísimo: empezar por lo **reversible** —documentación, análisis, planes, revisiones— y sólo después ir a lo irreversible —código, base de datos, producción—. El que empieza al revés quema la confianza del equipo en la primera semana y ya no la recupera.
>
> **Cuatro: la fricción del primer día.** Y esto no es un problema técnico. Una persona abre la herramienta, **no entiende qué hacer en los primeros tres minutos**, la cierra y vuelve a trabajar como siempre. Así es como mueren las herramientas internas, todas. **Si alguien no obtiene algo útil en su primera sesión, no hay segunda sesión.** Y lo que falta ahí no es funcionalidad: es diseño del primer día.
>
> **Cinco: el entorno miente.** Cosa muy nuestra y muy poco glamurosa: el repositorio que editás no siempre es el que lee el agente —hay copias, rutas distintas, despliegues congelados—. Cambiás algo, no llega, y parece un fallo del modelo. **No lo es. Es fontanería.** Y te come días.
>
> **Seis: los costes.** Sin techo, alguien corre cincuenta veces el modelo más caro y aparece la factura. Hace falta gobierno: modelo por defecto, tope por proyecto, aviso al 80%, y visibilidad de **por qué** se eligió ese modelo. Sin eso, o gastás de más, o —lo más probable— alguien se asusta y prohíbe todo.
>
> **Siete: la resistencia, que es legítima.** "Esto me va a sustituir." "Yo lo hago más rápido a mano." Lo que funcionó, y no fue un discurso sino un hecho: **el agente no cierra el ticket, lo prepara. La firma sigue siendo tuya.** Y como la firma es tuya, la responsabilidad también. Eso, dicho así, convierte la amenaza en herramienta. Y de paso es verdad.

---

## 5. Lecciones y cierre — 2 min ⏱ 0:18 → 0:20

**[SLIDE]** Las cinco lecciones, numeradas.

**[HABLADO]**

> Cinco lecciones y termino.
>
> **Uno. El grounding es el 80% del resultado.** El modelo es un producto de mercado, lo tiene cualquiera. **Tu documentación no.** Ahí está la ventaja y ahí está el trabajo.
>
> **Dos. Un agente que escribe sin otro que lo critique es una máquina de generar deuda técnica a gran velocidad.** El crítico no es un lujo: es lo que hace que el sistema sirva.
>
> **Tres. Exigí evidencia citable.** Si no puede señalarte el archivo y la línea, no lo sabe: lo está sonando bien. Y esto vale para la IA y —dicho con cariño— para las personas también.
>
> **Cuatro. Automatizá el juicio, no la decisión.** Que el sistema junte la evidencia, la contraste y te la ponga delante. La decisión la firma una persona.
>
> **Cinco. Medí antes de optimizar, y desconfía de tu propio baseline.** El caso del batch nos enseñó que el número más peligroso no es el que está mal: es el que **nunca se midió** y todos damos por bueno.

**[SLIDE]** Última, solo texto.

**[HABLADO]**

> Y el cierre.
>
> Esto **no sustituyó a nadie**. Lo que hizo fue mover el trabajo del equipo desde *escribir la primera versión* hacia *juzgar la primera versión*.
>
> Y resulta que **juzgar es exactamente donde alguien con experiencia vale más**. Escribir el primer borrador lo puede hacer un becario brillante con memoria de pez. Saber que el baseline está incompleto, que ese test no prueba nada y que esa frase de la documentación es ambigua — **eso todavía no lo hace ninguna máquina**.
>
> Gracias. Preguntas.

---
---

# ANEXOS PARA VOS

## A. Preguntas que te van a hacer (y respuestas preparadas)

**"¿Esto nos va a sustituir?"**
> No a corto plazo, y les digo por qué en concreto: la IA es muy buena produciendo el primer borrador y muy mala sabiendo si ese borrador está bien. En nuestro caso, el 100% de los primeros planes fueron rechazados por el revisor. Lo que sí cambia es **en qué parte del trabajo pasás el día**: menos escribiendo desde cero, más juzgando y decidiendo. Quien sabe juzgar, gana. Quien solo sabe teclear, tiene que aprender a juzgar.

**"¿Y si mete un error en producción?"**
> Por eso ninguna acción irreversible pasa sin firma humana. El agente prepara, propone y justifica; el despliegue, el commit a la rama principal y cualquier cosa contra producción las autoriza una persona. Y las puertas de calidad son binarias: compila o no compila, el test pasa o no pasa.

**"¿Cuánto cuesta?"**
> Depende del modelo y del volumen, y es órdenes de magnitud menos de lo que la gente imagina — pero sin tope de gasto puede irse. Se controla con: modelo por defecto sensato, tope mensual por proyecto y visibilidad del coste por ejecución.
> **[NOTA] Si tenés cifras reales de coste por ticket o por mes, este es EL momento de darlas. Si no las tenés, decí exactamente eso y no improvises un número.**

**"¿Nuestros datos van a entrenar al modelo?"**
> En los planes de empresa, no: el contrato lo prohíbe explícitamente. En las versiones gratuitas de consumo, sí pueden. No son el mismo producto aunque se llamen igual. Y para lo verdaderamente sensible existe la opción de modelo local, donde el dato no sale nunca.

**"¿Por dónde empiezo yo, mañana?"**
> Por algo **reversible** y que ya estés haciendo. Si escribís código: el asistente en el IDE, esta semana. Si no escribís código: cargá tus documentos en una herramienta de preguntas sobre documentos y probá una semana de preguntas reales. Y aplicá las siete reglas, sobre todo la 4 (por pasos) y la 5 (verificá lo verificable).

**"¿Qué modelo es el mejor?"**
> Es la pregunta equivocada, y no lo digo por soberbia: cambia cada dos meses. La pregunta correcta es de qué **tamaño** lo necesitás. Empezá por el del medio. Bajá si es masivo. Subí solo si el del medio te falló.

**"¿Cuánto tiempo llevó montar el flujo de Pacífico?"**
> **[NOTA] Completá con tu dato real. Y si el número es grande, no lo escondas: refuerza el mensaje de "el trabajo no está en el modelo, está alrededor del modelo". Un número honesto grande es más creíble que uno pequeño y sospechoso.**

---

## B. Plan B de recortes (si vas atrasado)

**Bloque 1** — en orden de qué sacrificar primero:
1. **Familia 4 del diccionario** (benchmarks/evals/drift) → 40 segundos en vez de 1:30.
2. **La escalera de 4 escalones** (sección 4) → contá solo el escalón 1 y el 3, se entiende igual.
3. **Los modelos especializados** (imagen, voz, video) → una frase: "también hay para imagen, voz y video; la transcripción de reuniones está resuelta y es baratísima".
4. **No recortes nunca:** alucinación, la matriz "qué uso para qué", y las 7 reglas. Es lo que la gente se lleva a la oficina.

**Bloque 2** — en orden:
1. **Frente A (documentación)** → de 2 min a 40 segundos.
2. **El detalle del bucle 1** (la cadena de agentes) → nómbralos rápido y salta al pipeline de 4 pasos.
3. **No recortes nunca:** el fallo del punto de entrada (frente B), el falso verde, y el cierre de "juzgar es donde el senior vale más".

---

## C. Checklist previo (hacer el 04/08)

- [ ] Actualizar nombres y versiones de modelos (bloque 1, sección 5).
- [ ] Actualizar el estado del batch de Pacífico: ¿hubo corrida completa en verde? ¿número real de la ventana hoy?
- [ ] Conseguir, si existe, un número de coste real (por ticket o mensual).
- [ ] Conseguir el tiempo real de montaje del flujo.
- [ ] Ensayar el bloque 2 con cronómetro: es el que se pasa.
- [ ] Decidir si vas a mostrar algo en vivo. **Recomendación: no, o solo un vídeo corto grabado.** Una demo en vivo que falla delante de 30 personas te destruye los 20 minutos, y el mensaje de la charla no necesita demo.
- [ ] Tener las cifras del batch a mano en una nota, no de memoria: 95 min · 27 M filas · 2.400.057 ms · 13 hallazgos · 2 bloqueantes.

---

## D. Frases-ancla (las que querés que se repitan en el pasillo)

1. *"No busca. Predice."*
2. *"La IA nunca suena insegura."*
3. *"El contexto vale más que el prompt."*
4. *"La IA amplifica la calidad de tu documentación. Para bien y para mal."*
5. *"El control se prueba contra el defecto: si no lo viste fallar, no sabés si funciona."*
6. *"El agente prepara, la persona firma."*
7. *"Juzgar es exactamente donde el senior vale más."*
