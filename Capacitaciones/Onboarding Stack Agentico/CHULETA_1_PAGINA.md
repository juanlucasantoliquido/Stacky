# IA en una página

*Sesión de nivelación · 05/08/2026 · Juan Luca Santoliquido*
**No hace falta tomar notas: está todo acá.**

---

## Las 3 frases

> **1. No busca. Predice.** No va a buscar la respuesta a ningún archivo: la **escribe**, eligiendo la palabra más probable. Por eso a veces escribe algo perfecto, y por eso a veces escribe algo perfectamente falso.
>
> **2. El contexto vale más que el prompt.** La frase mágica no existe. Pegarle el documento sí funciona.
>
> **3. La IA no duda.** Suena igual de segura cuando acierta que cuando se lo inventa. La duda la ponés vos.

---

## Todo el vocabulario, como si contrataras a alguien

| Palabra que vas a oír | Qué es, en la oficina | Ejemplo |
|---|---|---|
| **Modelo / LLM** | Lo que la persona trae puesto: su carrera, su oficio | Sabe contabilidad, redactar, inglés. **No sabe nada de nosotros** |
| **Prompt** | Lo que le pedís | *"Prepárame el informe de morosidad de julio"* |
| **Contexto** | Los papeles que le dejás en la mesa | El fichero de julio, el informe anterior, el correo del cliente |
| **Ventana de contexto** | El tamaño de la mesa | Si le apilás 400 carpetas, las de abajo no las mira |
| **Instrucciones de sistema** | Las normas de la casa | *"Eres analista. Escribes en formato informe. No hablas con clientes"* |
| **Guardrails** | Lo que no puede hacer **nunca** | No autoriza pagos, no escribe al cliente, no toca producción |
| **Skill** ⭐ | **El procedimiento de la casa, escrito** | *"El cierre se hace el día 3, primero bancos, Marta valida provisiones"* |
| **Herramienta** *(tool)* | Las llaves y los accesos | Usuario del ERP, llave del archivo, permiso para lanzar la consulta |
| **Agente** | El que además de opinar, **hace** — y repite hasta terminar | Mira, decide, actúa, comprueba, corrige, vuelve a empezar |
| **Subagente** | Pedirle a un compañero que se encargue de una parte | *"Tú revisa las facturas mientras yo sigo"* |
| **Multiagente** | Un equipo con roles | Uno propone, otro revisa, otro ejecuta, otro audita |
| **Grounding** | *"No me lo digas de memoria: enséñame dónde lo pone"* | Exigir el expediente, la página, la línea |
| **RAG** | Dejarle consultar el archivador antes de responder | Los "chatbots sobre nuestra documentación" son esto |
| **Fine-tuning** | Mandarlo a un máster | Caro y lento. Sirve para el **estilo**, no para saber el dato de ayer |
| **Memoria** | Su cuaderno de notas | Sin cuaderno, mañana no se acuerda de nada. **El cuaderno se lo damos nosotros** |
| **Alucinación** | El que nunca dice "no lo sé" | Le preguntás por una norma que no conoce y te la inventa, con total seguridad |
| **Temperatura** | Cuánto le dejás improvisar | Baja para cerrar el mes. Alta para una lluvia de ideas |
| **Human-in-the-loop** | La firma del responsable | **El agente prepara. La persona firma** |
| **Benchmark / evals** | El título vs. la prueba con casos reales | El título dice algo. La prueba con **tus** expedientes dice más |

**Las cuatro que más se confunden:**

> **Contexto** = los papeles de la mesa · *el QUÉ*
> **Skill** = el procedimiento de la casa · *el CÓMO*
> **Herramienta** = las llaves y los accesos · *el PODER*
> **Agente** = quien usa las tres hasta terminar · *el QUIÉN*

---

## Dónde se rompe la comparación ⚠️

Un compañero nuevo se parece a una IA en casi todo. **Menos en tres cosas, y son las que cuestan caro:**

1. **Tu compañero dice "no lo sé". La IA no.** Cuando no sabe, **completa**. Y no tiene ni idea de que no sabe.
2. **Tu compañero aprende de lo que le corregís. La IA no.** Corregirla mejora **esa** conversación, nada más.
3. **Tu compañero tiene sentido de la responsabilidad. La IA no tiene ninguno.** Pone el mismo cuidado en corregir una coma que en tocar producción.

---

## Qué uso para qué

| Lo que necesito hacer | Lo que uso | Lo que NO uso |
|---|---|---|
| Redactar, reformular, resumir | Chat normal (el mediano) | Nada más caro |
| Preguntar sobre **nuestros** documentos | Algo que lea los documentos y **cite** | El chat pelado: te lo inventa |
| Trabajar sobre el fichero que tengo abierto | El asistente dentro de la herramienta | Copiar y pegar a otra pestaña |
| Hacer lo mismo en 40 sitios | Un agente | El chat, 40 veces |
| Clasificar 10.000 registros | Modelo pequeño | El grande: 50× el precio, mismo resultado |
| Diagnosticar algo raro, diseñar desde cero | Modelo grande | El pequeño: algo plausible y flojo |
| Que cuadren las cifras | Excel, una consulta, una calculadora | **Cualquier IA** |
| Datos de clientes o personales | Plan de empresa, o modelo local | La versión gratuita |

**Los tres tamaños, en cualquier familia:**
🟢 **Pequeño = el becario** (masivo y simple) · 🔵 **Mediano = el analista** (el 90% del trabajo) · 🟣 **Grande = el socio** (lo difícil de verdad)
> **No mandes al socio a hacer fotocopias. No le pidas al becario que diseñe la estrategia.**
> Empezá por el mediano. Bajá si es masivo. Subí solo si el mediano te falló.

---

## Las 6 reglas

1. **Contexto antes que astucia.** Pegale el documento, el correo entero, el error completo. No tu resumen.
2. **Pedí el formato.** *"Como tabla, con estas cuatro columnas"* vale más que *"hacelo bien"*.
3. **Dale un ejemplo.** Uno o dos de cómo se ve una respuesta buena. Es lo que mejor funciona.
4. **Por pasos, no de un salto.** Que analice → mirás → que proponga → mirás → que ejecute.
5. **Verificá lo verificable.** *"¿De dónde sacaste esto?"* Si no lo puede señalar, no lo sabe.
6. **Nada irreversible sin firma humana.** Borrar, enviar, tocar producción, contestar a un cliente.

**Cuándo NO usarla:** responsabilidad legal · exactitud numérica · cuando no vas a poder verificar el resultado · cuando explicarla cuesta más que hacerla.

---

## Para hacer esta semana

- **Si escribís código:** usá el asistente **dentro** del editor, no en una pestaña aparte. Es gratis y es el mayor salto de calidad que vas a notar.
- **Si no escribís código:** meté tus documentos en una herramienta que te deje preguntarles **con citas**, y hacé una semana de preguntas reales.
- **Los dos:** elegí un procedimiento que hoy está solo en tu cabeza y **escribilo**. Media hora.
  Eso es una skill — y sirve con IA, sin IA, y el día que estés de vacaciones.

> **Si no lo podés escribir, tampoco lo vas a poder automatizar.**
