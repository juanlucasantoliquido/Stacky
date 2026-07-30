# Crítica v1 → v2 — Guion Sesión IA 05/08/2026

**Objeto:** `_historial/GUION_v1.md`
**Criterio de evaluación:** ¿lo entiende alguien que no sabe **nada** de IA, y cumple el encargo del correo?
**Veredicto: RECHAZADO.** 3 bloqueantes · 5 importantes · 3 menores.

---

## Bloqueantes

### C1 — El pedido explícito no está cubierto: no hay ejemplos humanos de los conceptos
El operador pidió, textual: *"ejemplos de cómo sería una skill en un humano, con ejemplos prácticos para que se entienda bien para qué sirve cada cosa"*.

v1 define `skill` así:
> *"la diferencia con el conocimiento del modelo: lo que aprendió en internet es como una carrera universitaria; una skill es el manual de procedimientos de la empresa"*

Eso es **una** analogía, de una línea, y sin ejemplo. Para el resto de los ~25 términos no hay ningún paralelo humano: `contexto`, `herramienta`, `agente`, `RAG`, `fine-tuning`, `guardrails` y `memoria` se explican en términos de sí mismos o con jerga de segundo nivel ("ventana", "inferencia", "vectorial").

Es el defecto más grave porque es **exactamente lo que se pidió**, y porque para la mitad no técnica de la sala es la única vía de entrada.

**Corrección:** tabla de equivalencias humano ↔ IA con ejemplo concreto por fila, y tratamiento extendido de `skill` con **cinco** ejemplos humanos + la distinción explícita frente a `herramienta`, `contexto` y `agente`, que en v1 se solapan.

---

### C2 — Sobrecarga: 25 términos en 9 minutos son 21 segundos por término
La sección 3 de v1 lista unos 25 conceptos en un bloque de 9 minutos. Para una audiencia de nivel cero es inasimilable: se entienden los tres primeros y el resto pasa como ruido. Peor, genera el efecto contrario al buscado — la gente sale convencida de que la IA es complicada.

Además hay términos que **no aportan nada** a esta audiencia y ocupan lugar: `zero-shot`, `drift`, `embeddings` y `base vectorial` a nivel de definición técnica, `chain of thought` como nombre propio.

**Corrección:** recortar a ~14 conceptos hablados, colgarlos todos del mismo hilo narrativo, y sacar el resto a una **chuleta impresa de una página** que se reparte. Lo que no se dice no se pierde: se entrega en papel.

---

### C3 — El presupuesto de tiempo no cierra en la práctica
Sumando las secciones de v1: 3+5+6+9+4+8+8+2 = **45 minutos exactos**. Eso significa cero margen para: la gente que reacciona, la pregunta que interrumpe, el proyector que tarda, y el propio expositor que respira.

Un guion que suma exactamente el tiempo disponible **siempre** se pasa. Y el correo del encargo dice, subrayado, *"es importante cumplir con la duración de cada tema"*.

**Corrección:** presupuestar **38-40 min de contenido** en el bloque de 45, y **18 min** en el de 20. El colchón es parte del guion, no un accidente.

---

## Importantes

### C4 — El bloque 2 está escrito para técnicos y la sala es mixta
Aparecen sin traducir: *rollback, baseline, CommandTimeout, CXPACKET, MAXDOP, commit, rama principal, pull request, IDE, repositorio, batch, producción, CRUD*.

La frase *"un rollback de 27 millones de filas"* no significa nada para quien no sabe qué es un rollback — y es justo el dato que tiene que impresionar. El impacto del caso se pierde con la mitad de la sala.

**Corrección:** cada término técnico del bloque 2 lleva traducción de media frase, **en el momento**, sin nota al pie. Ejemplo: *"un rollback —o sea, la base deshaciendo el trabajo ya hecho— de 27 millones de filas"*.

---

### C5 — `skill`, `herramienta` y `contexto` se confunden entre sí
En v1 los tres se presentan seguidos, en la misma familia, con definiciones que se solapan. Un asistente que salga de la charla no va a poder distinguirlos, y son de las tres cosas más útiles de entender.

**Corrección:** contraponerlos explícitamente en una sola línea memorizable, con el mismo ejemplo humano recorriendo los tres.

---

### C6 — No hay un hilo conductor: cada sección usa un ejemplo distinto
v1 salta de spam → póliza de seguro → SQL Server → batch → ticket. Cada ejemplo es correcto en sí mismo, pero el oyente tiene que reconstruir el mapa mental desde cero en cada sección. Los conceptos no se **apilan**.

**Corrección:** un caso único que atraviese toda la charla. El mejor candidato es **"contratamos a alguien nuevo"**: todos, técnicos y no técnicos, han incorporado a alguien alguna vez, y el paralelo es exacto en los ~14 conceptos que importan.

---

### C7 — La apertura pide admitir una negligencia delante de los jefes
Pregunta 3 de v1: *"¿quién se fio del resultado sin revisarlo?"*. En una reunión presencial de equipo, con responsables en la sala, **nadie levanta la mano**: hacerlo es reconocer que trabajó mal.

El arranque queda muerto y el expositor tiene que remontar.

**Corrección:** reformular a una pregunta que sea **seguro** contestar afirmativamente y que aterrice el mismo concepto (alucinación): *"¿a quién le dio alguna vez una respuesta que sonaba perfecta y resultó estar mal?"*. Ahí levanta la mano todo el mundo, y encima con una sonrisa.

---

### C8 — Las frases habladas son demasiado largas para decirlas de un tirón
Ejemplo real de v1 (sección 1):

> *"Solo que este fue entrenado con prácticamente todo el texto público que hay en internet, y es tan enorme que, para poder predecir bien la palabra siguiente, tuvo que aprender de paso gramática, lógica, estructura de argumentos, algo parecido al razonamiento, y una cantidad brutal de conocimiento del mundo."*

Son 52 palabras y cinco subordinadas. Leída en voz alta se pierde el hilo a la mitad — el que la dice y el que la escucha.

**Corrección:** barrido de todo el guion cortando en frases de ≤ 20 palabras. El guion tiene que sonar a alguien hablando, no a alguien leyendo.

---

## Menores

### C9 — Los nombres de modelo caducan y ocupan demasiada slide
v1 nombra siete productos comerciales. Para agosto puede haber cambiado la mitad. Ya hay una nota que avisa, pero la estructura de la slide sigue premiando los nombres sobre el concepto de los **tres tamaños**, que es lo único que no caduca.

**Corrección:** invertir el peso — los tres tamaños en grande, los nombres como letra chica ilustrativa.

---

### C10 — La metáfora del becario aparece una vez y se abandona
Es la mejor imagen del guion (brillante · memoria de pez · nunca dice "no sé" · baratísimo) y aparece en la sección 4 y no vuelve nunca.

**Corrección:** que reaparezca al menos dos veces más, y que sea la misma persona del hilo conductor.

---

### C11 — El bloque 2 reparte 7 minutos entre tres frentes por igual
Los tres frentes de Pacífico ocupan 2+2+3. El frente C (el batch) es el único que impresiona a una sala mixta y es el que menos tiempo tiene.

**Corrección:** A y B se cuentan como preparación del terreno (1 + 2 min), C es el protagonista (4 min).

---

## Resumen de cambios aplicados en v2

| # | Cambio |
|---|---|
| C1 | Nueva sección: *"Todo esto ya lo conocés: es contratar a alguien"* — tabla de 16 equivalencias + skill con 5 ejemplos humanos |
| C2 | Diccionario hablado recortado de 25 a 14 conceptos; el resto pasa a chuleta de 1 página |
| C3 | Re-presupuesto: 40 min de contenido en 45; 18 en 20 |
| C4 | 13 términos técnicos del bloque 2 traducidos en línea |
| C5 | Línea de contraste skill / herramienta / contexto / agente |
| C6 | Hilo conductor único: el fichaje nuevo, presente en las 8 secciones |
| C7 | Apertura reformulada |
| C8 | Barrido de frases largas en todo el guion |
| C9 | Slide de modelos invertida: tamaños en grande |
| C10 | El becario vuelve 3 veces y se funde con el hilo conductor |
| C11 | Reparto del bloque 2: 1 + 2 + 4 |
