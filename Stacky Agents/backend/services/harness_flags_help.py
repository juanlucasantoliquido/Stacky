"""Plan 86 — Ayuda en lenguaje llano ("para mortales") por flag del arnés.

Reglas de diseño:
- PURO: sin flask, sin config, sin IO. Solo datos + 1 función de lookup.
- Keyed por FlagSpec.key. Cobertura 100% del FLAG_REGISTRY (test centinela).
- SEPARADO de harness_flags.py a propósito: los planes 82/83/84/85 editan las
  specs; este archivo solo contiene contenido → conmutatividad.
- Redacción: prohibida la jerga de la denylist de tests/test_harness_flags_help.py.
  on_effect/off_effect son frases COMPLETAS que empiezan con "Si " (el panel
  las pinta tal cual, sin lógica de redacción en el frontend).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlainHelp:
    what: str        # qué hace, en 1 frase sin jerga (≤200 chars)
    on_effect: str   # "Si la activás: ..." / "Si subís el número: ..." (≤240)
    off_effect: str  # "Si la apagás: ..." / "Si lo dejás vacío: ..." (≤240)
    example: str     # ejemplo concreto para un no-experto (≤300)


PLAIN_HELP: dict[str, PlainHelp] = {
    # ── runtimes_cli ──────────────────────────────────────────────────────
    "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": PlainHelp(
        what="Un control de calidad automático que revisa el trabajo del agente antes de darlo por bueno.",
        on_effect="Si la activás: cuando el resultado tiene errores graves, el trabajo queda marcado 'para revisar' en vez de figurar como terminado.",
        off_effect="Si la apagás: el trabajo se da por terminado aunque tenga errores graves, y los descubrís vos después.",
        example="Es como la inspección final de una fábrica: si la pieza sale fallada, no se despacha al cliente.",
    ),
    "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED": PlainHelp(
        what="Hace que el agente de Claude revise y corrija su propio trabajo automáticamente antes de terminar.",
        on_effect="Si la activás: el agente intenta corregir solo los errores que detecta antes de entregar el resultado.",
        off_effect="Si la apagás: el agente no se autocorrige; entrega el resultado tal cual salió.",
        example="Como un redactor que relee su texto una vez antes de mandarlo, en vez de mandarlo a la primera.",
    ),
    "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES": PlainHelp(
        what="Cuántas veces como máximo el agente de Claude puede intentar corregirse a sí mismo en un mismo trabajo.",
        on_effect="Si subís el número: el agente tiene más oportunidades de corregirse antes de entregar, pero el trabajo puede tardar más.",
        off_effect="Si lo bajás: menos intentos de autocorrección; si lo dejás en cero, la autocorrección no llega a intentar nada.",
        example="Como darle a un alumno hasta 2 intentos de revisar su examen antes de entregarlo.",
    ),
    "CLAUDE_CODE_CLI_HOOKS_ENABLED": PlainHelp(
        what="Activa una revisión automática de los archivos que el agente de Claude va creando o modificando durante el trabajo.",
        on_effect="Si la activás: cada archivo tocado por el agente pasa por una validación automática mientras trabaja.",
        off_effect="Si la apagás: los archivos no se revisan sobre la marcha; solo se ve el resultado final.",
        example="Como un control de calidad en cada etapa de una línea de producción, no solo al final.",
    ),
    "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED": PlainHelp(
        what="Le da al agente de Claude el conocimiento acumulado del proyecto: decisiones tomadas, cosas a evitar y el glosario propio del cliente.",
        on_effect="Si la activás: el agente arranca cada trabajo ya sabiendo las reglas y decisiones previas de ese proyecto.",
        off_effect="Si la apagás: el agente empieza cada trabajo sin ese conocimiento previo del proyecto.",
        example="Como darle a un empleado nuevo el manual de la empresa antes de su primer día, en vez de que aprenda a los golpes.",
    ),
    "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica el conocimiento acumulado del proyecto para el agente de Claude.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "CLAUDE_CODE_CLI_RESUME_ENABLED": PlainHelp(
        what="Cuando se vuelve a lanzar un trabajo ya empezado, retoma la conversación anterior con el agente de Claude en vez de arrancar de cero.",
        on_effect="Si la activás: un reintento continúa donde quedó el trabajo anterior, ahorrando tiempo y repetición.",
        off_effect="Si la apagás: cada reintento arranca desde cero, sin memoria del intento anterior.",
        example="Como retomar una llamada telefónica cortada en vez de volver a explicar todo desde el principio.",
    ),
    "CLAUDE_CODE_CLI_RESUME_PROJECTS": PlainHelp(
        what="En qué proyectos vale retomar la conversación anterior con el agente de Claude en un reintento.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una llave que abre solo las oficinas que vos elijas; sin lista, abre todas.",
    ),
    "CLAUDE_CODE_CLI_MCP_ENABLED": PlainHelp(
        what="Conecta al agente de Claude con herramientas extra de Stacky (por ejemplo, consultar la memoria del proyecto) durante el trabajo.",
        on_effect="Si la activás: el agente puede usar estas herramientas adicionales mientras trabaja.",
        off_effect="Si la apagás: el agente trabaja solo con sus capacidades básicas, sin las herramientas extra.",
        example="Como darle a un empleado acceso a una caja de herramientas adicional además de las que ya tenía.",
    ),
    "CLAUDE_CODE_CLI_MCP_PROJECTS": PlainHelp(
        what="En qué proyectos vale la conexión de herramientas extra del agente de Claude.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una llave que abre solo las oficinas que vos elijas; sin lista, abre todas.",
    ),
    "CODEX_CLI_CONTRACT_GATE_ENABLED": PlainHelp(
        what="Un control de calidad automático que revisa el trabajo del agente de Codex antes de darlo por bueno.",
        on_effect="Si la activás: cuando el resultado tiene errores graves, el trabajo queda marcado 'para revisar' en vez de figurar como terminado.",
        off_effect="Si la apagás: el trabajo se da por terminado aunque tenga errores graves, y los descubrís vos después.",
        example="Es como la inspección final de una fábrica: si la pieza sale fallada, no se despacha al cliente.",
    ),
    "CODEX_CLI_AUTOCORRECT_ENABLED": PlainHelp(
        what="Hace que el agente de Codex revise y corrija su propio trabajo automáticamente antes de terminar.",
        on_effect="Si la activás: el agente intenta corregir solo los errores que detecta antes de entregar el resultado.",
        off_effect="Si la apagás: el agente no se autocorrige; entrega el resultado tal cual salió.",
        example="Como un redactor que relee su texto una vez antes de mandarlo, en vez de mandarlo a la primera.",
    ),
    "CODEX_CLI_AUTOCORRECT_MAX_RETRIES": PlainHelp(
        what="Cuántas veces como máximo el agente de Codex puede intentar corregirse a sí mismo en un mismo trabajo.",
        on_effect="Si subís el número: el agente tiene más oportunidades de corregirse antes de entregar, pero el trabajo puede tardar más.",
        off_effect="Si lo bajás: menos intentos de autocorrección; si lo dejás en cero, la autocorrección no llega a intentar nada.",
        example="Como darle a un alumno hasta 2 intentos de revisar su examen antes de entregarlo.",
    ),
    "CODEX_CLI_MODEL_DENYLIST": PlainHelp(
        what="Lista de modelos de Codex que no se pueden usar; si el sistema iba a usar uno de la lista, usa otro permitido en su lugar.",
        on_effect="Si escribís nombres de modelos separados por coma: esos modelos quedan prohibidos para los trabajos de Codex.",
        off_effect="Si lo dejás vacío: no hay modelos prohibidos, se puede usar cualquiera de los disponibles.",
        example="Como decirle a un delivery 'nunca me traigas de tal marca'; si tocaba esa, te trae otra permitida.",
    ),
    "CODEX_CLI_RESUME_ENABLED": PlainHelp(
        what="Cuando se vuelve a lanzar un trabajo ya empezado, retoma la conversación anterior con el agente de Codex en vez de arrancar de cero.",
        on_effect="Si la activás: un reintento continúa donde quedó el trabajo anterior, ahorrando tiempo y repetición.",
        off_effect="Si la apagás: cada reintento arranca desde cero, sin memoria del intento anterior.",
        example="Como retomar una llamada telefónica cortada en vez de volver a explicar todo desde el principio.",
    ),
    "CODEX_CLI_RESUME_PROJECTS": PlainHelp(
        what="En qué proyectos vale retomar la conversación anterior con el agente de Codex en un reintento.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una llave que abre solo las oficinas que vos elijas; sin lista, abre todas.",
    ),
    # ── contexto_memoria ──────────────────────────────────────────────────
    "STACKY_CONTEXT_BUDGET_ENABLED": PlainHelp(
        what="Recorta la información que recibe el agente para que no se pase de un límite manejable, priorizando lo más importante.",
        on_effect="Si la activás: el sistema ordena la información por importancia y descarta lo que sobra para no saturar al agente.",
        off_effect="Si la apagás: el agente recibe toda la información disponible, sin recorte ni prioridad.",
        example="Como armar una mochila con lo esencial primero cuando hay poco espacio, en vez de llevar todo sin criterio.",
    ),
    "STACKY_CONTEXT_BUDGET_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica el recorte de información entregada al agente.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_CONTEXT_BUDGET_TOKENS": PlainHelp(
        what="Cuánta información como máximo se le entrega al agente en cada trabajo, medida en unidades de texto.",
        on_effect="Si subís el número: el agente recibe más información de contexto, pero el trabajo puede costar más.",
        off_effect="Si lo bajás: el agente recibe menos información, lo que ahorra costo pero puede dejar afuera detalles útiles.",
        example="Como decidir cuántas páginas de un informe le das a alguien para leer antes de una reunión.",
    ),
    "STACKY_CONTEXT_DEDUP_ENABLED": PlainHelp(
        what="Evita mandarle al agente la misma información repetida dos veces.",
        on_effect="Si la activás: las líneas repetidas se eliminan antes de armar el paquete de información del agente.",
        off_effect="Si la apagás: puede llegar información duplicada, ocupando espacio de más sin sumar valor.",
        example="Como sacar las hojas repetidas de una carpeta antes de fotocopiarla entera.",
    ),
    "STACKY_CONTEXT_DEDUP_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica la eliminación de información repetida en el contexto del agente.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_CONTEXT_RERANK_ENABLED": PlainHelp(
        what="Cuando hay que recortar la información del agente, prioriza la que se parece más al pedido concreto.",
        on_effect="Si la activás: al recortar, se conserva primero lo más relacionado con el pedido puntual.",
        off_effect="Si la apagás: al recortar se sigue el orden de prioridad fijo de siempre, sin mirar qué tan relacionado está con el pedido.",
        example="Como elegir qué libros llevarte de la biblioteca según el tema que estás estudiando, no por orden alfabético.",
    ),
    "STACKY_PARALLEL_INJECTORS_ENABLED": PlainHelp(
        what="Hace que dos búsquedas de información de contexto (tickets parecidos y datos del tablero) se hagan al mismo tiempo.",
        on_effect="Si la activás: esas dos búsquedas de información corren a la vez, y el trabajo arranca un poco más rápido.",
        off_effect="Si la apagás: esas búsquedas se hacen una después de la otra, un poco más lento pero igual de completo.",
        example="Como que dos empleados busquen datos distintos al mismo tiempo, en vez de que uno espere a que el otro termine.",
    ),
    "STACKY_RETRIEVAL_EXPANSION_ENABLED": PlainHelp(
        what="Hace que las búsquedas internas encuentren información aunque la escritura tenga acentos distintos o se usen sinónimos del rubro.",
        on_effect="Si la activás: una búsqueda encuentra resultados aunque falten acentos o se use una palabra parecida del mismo tema.",
        off_effect="Si la apagás: la búsqueda es literal; una palabra distinta o sin acento puede no encontrar nada relacionado.",
        example="Como que buscar 'facturacion' también encuentre 'facturación', en vez de exigir la tilde exacta.",
    ),
    "STACKY_MEMORY_INJECTION_ENABLED": PlainHelp(
        what="Le muestra al agente los aprendizajes y observaciones guardados de trabajos anteriores del mismo proyecto.",
        on_effect="Si la activás: el agente arranca cada trabajo con los aprendizajes previos ya guardados a la vista.",
        off_effect="Si la apagás: el agente no ve esos aprendizajes previos; empieza cada trabajo sin ese historial.",
        example="Como darle a un médico la ficha con el historial del paciente antes de la consulta, en vez de empezar de cero.",
    ),
    "STACKY_MEMORY_INJECTION_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica la inyección de recuerdos guardados en el trabajo del agente.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_MEMORY_CAPS_JSON": PlainHelp(
        what="Límites de cuánta memoria acumulada se le muestra al agente en cada trabajo.",
        on_effect="Si escribís una configuración: acotás cuántos recuerdos de cada tipo recibe el agente, para que no se distraiga ni encarezca.",
        off_effect="Si lo dejás vacío: se usan los límites estándar del sistema.",
        example="Como decirle a un asesor 'traeme máximo 3 antecedentes por tema', en vez de que llegue con la biblioteca entera.",
    ),
    "STACKY_MEMORY_REVIEW_SWEEP_HOURS": PlainHelp(
        what="Cada cuántas horas el sistema revisa si hay recuerdos guardados que ya deberían ser chequeados de nuevo por un humano.",
        on_effect="Si le ponés un número de horas: cada tanto, los recuerdos vencidos se marcan para que un humano los revise.",
        off_effect="Si lo dejás en cero: esa revisión periódica no se hace, ningún recuerdo se marca automáticamente para revisar.",
        example="Como una alarma que te recuerda cada tanto revisar si tus notas viejas siguen siendo válidas.",
    ),
    "STACKY_MEMORY_DIRECTIVE_MAX_CHARS": PlainHelp(
        what="Cuánto espacio de texto como máximo ocupan las instrucciones obligatorias dentro del paquete de memoria del agente.",
        on_effect="Si subís el número: las instrucciones obligatorias pueden ocupar más espacio y ser más detalladas.",
        off_effect="Si lo bajás: las instrucciones obligatorias se acortan más; si lo dejás en cero, se usa el límite estándar del sistema.",
        example="Como el largo máximo permitido para las instrucciones de uso de un producto en el empaque.",
    ),
    "STACKY_MEMORY_INJECT_SCOPES": PlainHelp(
        what="Qué grupos de recuerdos guardados se le muestran al agente: los del proyecto, del equipo, generales o personales.",
        on_effect="Si escribís los grupos separados por coma: solo se usan esos grupos de recuerdos guardados.",
        off_effect="Si lo dejás vacío: se usan los grupos estándar (proyecto, equipo y generales).",
        example="Como elegir qué carpetas de archivador mostrarle a alguien: solo las del proyecto, o también las personales.",
    ),
    "STACKY_SKILLS_ENABLED": PlainHelp(
        what="Les da a los agentes acceso a procedimientos guardados (recetas de trabajo) relevantes para la tarea que están haciendo.",
        on_effect="Si la activás: los agentes reciben los procedimientos guardados que apliquen a su tarea, en los tres tipos de agente.",
        off_effect="Si la apagás: los agentes no reciben esos procedimientos guardados; trabajan solo con lo que ya saben.",
        example="Como darle a un cocinero la receta exacta del plato que va a preparar, en vez de que improvise.",
    ),
    "STACKY_SKILLS_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica el uso de procedimientos guardados por los agentes.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_CLI_FEWSHOT_ENABLED": PlainHelp(
        what="Le muestra al agente ejemplos de trabajos anteriores que ya fueron aprobados, del mismo tipo y proyecto.",
        on_effect="Si la activás: el agente ve algunos ejemplos de trabajos aprobados antes de hacer el suyo.",
        off_effect="Si la apagás: el agente no ve ejemplos previos aprobados; hace el trabajo sin esa referencia.",
        example="Como mostrarle a un alumno un par de exámenes ya corregidos con nota alta antes de que rinda el suyo.",
    ),
    "STACKY_CLI_FEWSHOT_K": PlainHelp(
        what="Cuántos ejemplos de trabajos aprobados como máximo se le muestran al agente.",
        on_effect="Si subís el número: el agente ve más ejemplos previos aprobados antes de empezar.",
        off_effect="Si lo bajás: el agente ve menos ejemplos; si lo dejás en cero, no ve ninguno.",
        example="Como decidir si le mostrás a alguien 2 o 5 modelos de referencia antes de que haga el suyo.",
    ),
    "STACKY_CLI_FEWSHOT_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica mostrarle al agente ejemplos de trabajos aprobados.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_INJECT_PROCESS_CATALOG": PlainHelp(
        what="Le muestra al agente el listado de procesos y sistemas propios del cliente, para que ubique el pedido dentro de ese contexto.",
        on_effect="Si la activás: el agente recibe el catálogo de procesos del cliente antes de empezar a trabajar.",
        off_effect="Si la apagás: el agente no recibe ese catálogo; trabaja sin ese mapa de procesos del cliente.",
        example="Como darle a un técnico nuevo el plano de la fábrica antes de mandarlo a arreglar una máquina.",
    ),
    "STACKY_CAPS_ADVISOR_ENABLED": PlainHelp(
        what="Analiza el historial de uso y sugiere límites de memoria más adecuados para cada tipo de agente, sin aplicarlos solo.",
        on_effect="Si la activás: aparece una sugerencia de límites de memoria basada en el historial, que el operador puede aplicar a mano.",
        off_effect="Si la apagás: no aparecen esas sugerencias automáticas de límites.",
        example="Como un asesor que te recomienda cuánto presupuesto asignar según gastos pasados, pero la decisión final es tuya.",
    ),
    "STACKY_RAG_CATALOG_ENABLED": PlainHelp(
        what="Cuando el catálogo de procesos es largo, le muestra al agente solo las partes que se parecen a tu pedido.",
        on_effect="Si la activás: el agente recibe solo los procesos del catálogo relacionados con lo que pediste — menos ruido y menos gasto.",
        off_effect="Si la apagás: el agente recibe el catálogo completo, aunque la mayoría no tenga que ver con tu pedido.",
        example="En vez de darle la guía telefónica entera, le das la página donde está el apellido que busca.",
    ),
    "STACKY_RAG_CATALOG_TOP_K": PlainHelp(
        what="Cuántos procesos del catálogo como máximo se le muestran al agente cuando la búsqueda inteligente de procesos está activada.",
        on_effect="Si subís el número: el agente ve más procesos parecidos al pedido, con el riesgo de sumar información de más.",
        off_effect="Si lo bajás: el agente ve menos procesos parecidos, más enfocado pero con menos opciones.",
        example="Como decidir si le das a alguien las 5 páginas más relevantes de un manual, o las 15 más relevantes.",
    ),
    "STACKY_PROCESS_DISCIPLINE_ENABLED": PlainHelp(
        what="Ayuda al agente a decidir si conviene reusar un proceso ya existente del catálogo del cliente en vez de inventar uno nuevo.",
        on_effect="Si la activás: el agente recibe una recomendación explícita de reusar procesos existentes cuando se parecen al pedido.",
        off_effect="Si la apagás: el agente decide por su cuenta sin esa guía explícita de reutilización.",
        example="Como recordarle a un empleado 'fijate si ya existe una plantilla parecida antes de crear una nueva'.",
    ),
    # ── calidad_verificacion ──────────────────────────────────────────────
    "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED": PlainHelp(
        what="Le muestra al agente, como lista de tareas obligatoria, los criterios que el ticket exige cumplir.",
        on_effect="Si la activás: el agente recibe esa lista de criterios obligatorios y no se le puede recortar de la información.",
        off_effect="Si la apagás: el agente no recibe esa lista destacada; los criterios quedan mezclados en el texto del ticket.",
        example="Como entregarle a alguien una checklist aparte de lo que tiene que cumplir, en vez de un párrafo suelto.",
    ),
    "STACKY_ACCEPTANCE_CRITERIA_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica la lista de criterios obligatorios que recibe el agente.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una lista de invitados: sin lista, entra cualquiera; con lista, solo los nombrados.",
    ),
    "STACKY_CRITERIA_REPAIR_ENABLED": PlainHelp(
        what="Si el trabajo no cumple algún criterio exigido, le da al agente una única oportunidad de corregirlo antes de darlo por terminado.",
        on_effect="Si la activás: cuando falta cumplir un criterio, el agente recibe un aviso puntual para corregirlo antes de cerrar.",
        off_effect="Si la apagás: si falta cumplir un criterio, el trabajo se cierra igual sin darle esa oportunidad de corrección.",
        example="Como devolverle una vez el trabajo a un proveedor señalando lo que falta, antes de aceptarlo.",
    ),
    "STACKY_CRITERIA_REPAIR_MAX_RETRIES": PlainHelp(
        what="Cuántas veces como máximo se le da al agente la oportunidad de corregir criterios incumplidos en un mismo trabajo.",
        on_effect="Si subís el número: el agente tiene más oportunidades de corregir criterios incumplidos.",
        off_effect="Si lo bajás: menos oportunidades de corrección; si lo dejás en cero, no hay ninguna.",
        example="Como definir si un proveedor tiene 1 o 2 vueltas para corregir un pedido antes de que se lo rechace.",
    ),
    "STACKY_SELF_REVIEW_MODE": PlainHelp(
        what="Define qué tan estricta es la autorrevisión del agente contra los criterios exigidos: apagada, solo anotando, o bloqueando si no cumple.",
        on_effect="Si elegís el modo intermedio: solo queda anotado si cumple o no. Si elegís el modo más estricto: el trabajo se bloquea si no cumple.",
        off_effect="Si lo dejás apagado o vacío: no hay autorrevisión contra los criterios.",
        example="Como elegir entre que un corrector solo comente los errores, o que directamente rechace el trabajo si hay errores.",
    ),
    "STACKY_SELF_REVIEW_MIN_SCORE": PlainHelp(
        what="Qué tan bien tiene que salir la autorrevisión (en una escala de 0 a 1) para que el trabajo pase cuando el modo estricto está activo.",
        on_effect="Si subís el número, más cerca de 1: la exigencia para aprobar es mayor y más trabajos quedan para revisar.",
        off_effect="Si lo bajás, más cerca de 0: la exigencia es menor y pasan más trabajos sin marcar para revisar.",
        example="Como subir o bajar la nota mínima para aprobar un examen.",
    ),
    "STACKY_EXEC_VERIFICATION_ENABLED": PlainHelp(
        what="Prende un control automático que realmente ejecuta y prueba el código que el agente cambió, no solo lo lee.",
        on_effect="Si la activás: el código cambiado se compila y se prueba de verdad antes de dar el trabajo por bueno.",
        off_effect="Si la apagás: no se ejecuta ni prueba nada automáticamente; solo se confía en lo que el agente dice haber hecho.",
        example="Como probar de verdad que el auto arranca antes de entregarlo, en vez de confiar en la palabra del mecánico.",
    ),
    "STACKY_EXEC_VERIFICATION_MODE": PlainHelp(
        what="Qué tan estricta es esta prueba real del código: apagada, solo anotando resultados, o bloqueando el trabajo si falla.",
        on_effect="Si elegís el modo intermedio: se anota el resultado de la prueba sin bloquear. Si elegís el modo más estricto: un fallo grave bloquea el trabajo.",
        off_effect="Si lo dejás apagado o vacío: no se hace esta prueba real del código.",
        example="Como decidir si un fallo de calidad solo se anota en una planilla, o directamente frena la producción.",
    ),
    "STACKY_EXEC_VERIFICATION_TIMEOUT_S": PlainHelp(
        what="Cuánto tiempo como máximo, en segundos, se espera a que termine cada prueba individual del código.",
        on_effect="Si subís el número: cada prueba tiene más tiempo para terminar antes de darse por vencida.",
        off_effect="Si lo bajás: las pruebas se cortan antes si tardan demasiado, lo que puede dejar pruebas lentas sin completar.",
        example="Como poner un cronómetro a cada examen: si se pasa del tiempo, se corta ahí.",
    ),
    "STACKY_EXEC_VERIFICATION_BUDGET_S": PlainHelp(
        what="Cuánto tiempo total, en segundos, se le permite a todas las pruebas del código juntas en un mismo trabajo.",
        on_effect="Si subís el número: hay más tiempo total disponible para completar todas las pruebas del trabajo.",
        off_effect="Si lo bajás: el tiempo total para todas las pruebas es más corto, y pueden quedar pruebas sin correr.",
        example="Como el tiempo total de un examen con varias partes, sin importar cuánto dure cada una por separado.",
    ),
    "STACKY_EXEC_VERIFICATION_PROJECTS": PlainHelp(
        what="En qué proyectos se aplican las pruebas reales del código cuando esa función está activada en general.",
        on_effect="Si escribís nombres de proyectos separados por coma: la prueba real del código se hace solo en esos proyectos.",
        off_effect="Si lo dejás vacío: se aplica a todos los proyectos, siempre que la función esté activada en general.",
        example="Como elegir en qué sucursales aplicar un nuevo control de calidad antes de expandirlo a todas.",
    ),
    "STACKY_EXEC_REPAIR_ENABLED": PlainHelp(
        what="Si la prueba real del código encuentra un fallo grave, le da al agente una única oportunidad de arreglarlo.",
        on_effect="Si la activás: ante un fallo grave de la prueba real, el agente recibe un intento de corrección dirigido a ese fallo.",
        off_effect="Si la apagás: ante un fallo grave, el trabajo queda directamente marcado para revisar, sin intento de corrección.",
        example="Como darle a un mecánico una oportunidad más de arreglar la falla detectada antes de rechazar el auto.",
    ),
    "STACKY_EXEC_REPAIR_MAX_RETRIES": PlainHelp(
        what="Cuántas veces como máximo se intenta corregir un fallo grave detectado por la prueba real del código.",
        on_effect="Si subís el número: más intentos de corrección ante un fallo grave del código.",
        off_effect="Si lo bajás: menos intentos; si lo dejás en cero, no hay ninguno.",
        example="Como definir cuántas vueltas de arreglo se le dan a un desperfecto antes de rendirse.",
    ),
    "STACKY_FAKE_GREEN_GUARD_ENABLED": PlainHelp(
        what="Detecta pruebas de software que parecen exitosas pero en realidad no verifican nada de verdad.",
        on_effect="Si la activás: el sistema avisa cuando una prueba está vacía o no comprueba realmente nada, aunque figure como exitosa.",
        off_effect="Si la apagás: esas pruebas vacías o falsas no se detectan; podrían pasar como si estuviera todo bien.",
        example="Como detectar que un guardia de seguridad marcaba presente sin haber hecho la ronda.",
    ),
    "STACKY_FAKE_GREEN_GUARD_HARD": PlainHelp(
        what="Decide si una prueba falsa detectada solo se avisa, o directamente bloquea el trabajo.",
        on_effect="Si la activás: detectar una prueba falsa bloquea el trabajo en vez de solo avisar.",
        off_effect="Si la apagás: detectar una prueba falsa solo genera un aviso, sin bloquear nada.",
        example="Como decidir si una alarma de humo solo suena, o además corta la corriente del edificio.",
    ),
    "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED": PlainHelp(
        what="Muestra en el resultado del trabajo un resumen de cómo salió la prueba real del código.",
        on_effect="Si la activás: el resultado del trabajo incluye ese resumen de la prueba real, para que lo veas sin buscarlo.",
        off_effect="Si la apagás: ese resumen no se muestra en el resultado, aunque la prueba real siga corriendo si está activada.",
        example="Como agregar un sello de 'control de calidad aprobado' visible en el paquete, en vez de tenerlo solo archivado.",
    ),
    "STACKY_ACCEPTANCE_CONTRACT_ENABLED": PlainHelp(
        what="Convierte automáticamente el pedido del ticket en una serie de pruebas concretas que el trabajo debe cumplir.",
        on_effect="Si la activás: antes de empezar, se arma un examen concreto derivado del propio pedido, para chequear el resultado al final.",
        off_effect="Si la apagás: no se arma ese examen automático; se confía solo en la revisión general del trabajo.",
        example="Como convertir el pedido de un cliente en una lista de pruebas de aceptación concretas antes de empezar a fabricar.",
    ),
    "STACKY_ACCEPTANCE_CONTRACT_MODE": PlainHelp(
        what="Qué tan estricto es el examen automático derivado del pedido: apagado, solo informativo, o bloqueante.",
        on_effect="Si elegís el modo intermedio: se arma el examen y se informa el resultado sin bloquear. Si elegís el modo más estricto: el examen se usa para bloquear el cierre si no se cumple.",
        off_effect="Si lo dejás apagado o vacío: no se arma ese examen automático.",
        example="Como decidir si el examen de aceptación de un proveedor es solo informativo o condición para pagarle.",
    ),
    "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS": PlainHelp(
        what="Cuántas pruebas concretas como máximo se derivan automáticamente de un pedido, según su complejidad.",
        on_effect="Si subís el número: se pueden derivar más pruebas concretas del pedido, cubriendo más casos.",
        off_effect="Si lo bajás: se derivan menos pruebas concretas, cubriendo menos casos del pedido.",
        example="Como limitar a 4 preguntas el examen de aceptación de un pedido chico, en vez de hacerlo interminable.",
    ),
    "STACKY_ACCEPTANCE_CONTRACT_PROJECTS": PlainHelp(
        what="En qué proyectos se aplica el examen automático derivado del pedido, cuando esa función está activada en general.",
        on_effect="Si escribís nombres de proyectos separados por coma: ese examen automático se arma solo en esos proyectos.",
        off_effect="Si lo dejás vacío: se aplica a todos los proyectos, siempre que la función esté activada en general.",
        example="Como elegir en qué sucursales aplicar un nuevo control de calidad antes de expandirlo a todas.",
    ),
    "STACKY_ACCEPTANCE_GATE_ENABLED": PlainHelp(
        what="Corre el examen automático derivado del pedido al final del trabajo, y decide si se puede dar por terminado.",
        on_effect="Si la activás: si el examen se cumple completo, el trabajo se da por terminado; si falla algo, se corrige o se marca para revisar.",
        off_effect="Si la apagás: ese examen final no se corre; el trabajo se cierra sin ese chequeo automático.",
        example="Como tomar el examen de aceptación recién al final, antes de entregar el pedido al cliente.",
    ),
    "STACKY_ACCEPTANCE_REPAIR_ENABLED": PlainHelp(
        what="Si el examen final detecta algo que no se cumple, le da al agente una única oportunidad de corregir justo eso.",
        on_effect="Si la activás: ante un punto del examen no cumplido, el agente recibe un intento de corrección dirigido a ese punto.",
        off_effect="Si la apagás: ante un punto no cumplido, el trabajo pasa directo a revisión, sin intento de corrección.",
        example="Como devolverle a un alumno solo la pregunta mal respondida para que la corrija, no todo el examen.",
    ),
    "STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES": PlainHelp(
        what="Cuántas veces como máximo se intenta esa corrección dirigida del examen final.",
        on_effect="Si subís el número: más intentos de corrección del examen final.",
        off_effect="Si lo bajás: menos intentos; si lo dejás en cero, no hay ninguno.",
        example="Como definir cuántas vueltas de corrección se permiten antes de mandar el pedido a revisión manual.",
    ),
    "STACKY_ACCEPTANCE_INTEGRITY_ENABLED": PlainHelp(
        what="Protege el examen automático para que el agente no pueda alterarlo y hacer trampa para aprobar.",
        on_effect="Si la activás: si el agente modifica el examen generado, el sistema lo restaura a su versión original antes de calificar.",
        off_effect="Si la apagás: el examen se corre desde donde esté, sin esa protección contra manipulación.",
        example="Como imprimir el examen desde una copia que el alumno no puede tocar, para que no se lo modifique.",
    ),
    "STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED": PlainHelp(
        what="Muestra en el resultado del trabajo un resumen de cómo salió el examen automático derivado del pedido.",
        on_effect="Si la activás: el resultado del trabajo incluye ese resumen del examen, con el detalle de qué se cumplió.",
        off_effect="Si la apagás: ese resumen no se muestra en el resultado del trabajo.",
        example="Como adjuntar la planilla de corrección del examen junto con el trabajo entregado.",
    ),
    "STACKY_QUALITY_CONVERGENCE_ENABLED": PlainHelp(
        what="Hace que, al generar una ficha grande de trabajo, el sistema insista corrigiendo hasta que quede bien o se agoten los intentos.",
        on_effect="Si la activás: si la primera versión no queda bien, se vuelve a intentar corregirla varias veces hasta lograrlo o agotar los intentos.",
        off_effect="Si la apagás: se hace un solo intento de corrección, sin insistir más allá de eso.",
        example="Como pedirle a alguien que reescriba un informe varias veces hasta que quede bien, en vez de conformarse con el primer intento.",
    ),
    "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS": PlainHelp(
        what="Cuántas vueltas de corrección como máximo se le dan a una ficha grande de trabajo hasta que quede bien.",
        on_effect="Si subís el número: se permiten más vueltas de corrección antes de rendirse.",
        off_effect="Si lo bajás (mínimo 1): se permiten menos vueltas de corrección; con 1 alcanza un solo intento.",
        example="Como poner un tope de 2 correcciones a un borrador antes de aceptarlo como está.",
    ),
    "STACKY_ADAPTIVE_EFFORT_ENABLED": PlainHelp(
        what="Ajusta automáticamente cuánto esfuerzo de pensamiento le pide al agente según lo difícil que parezca el pedido.",
        on_effect="Si la activás: pedidos simples piden menos esfuerzo, más rápido y barato, y pedidos difíciles piden más esfuerzo; si vos elegís el esfuerzo a mano, tu elección manda.",
        off_effect="Si la apagás: se usa siempre el mismo nivel de esfuerzo fijo, sin ajustarlo según la dificultad.",
        example="Como pedirle a un empleado que se tome más tiempo en una tarea difícil y menos en una simple, en vez de dedicarle siempre lo mismo.",
    ),
    "STACKY_EFFORT_FLOOR": PlainHelp(
        what="El nivel de esfuerzo más bajo permitido, aunque el ajuste automático quiera bajarlo más.",
        on_effect="Si escribís un nivel más alto: se garantiza al menos ese nivel de esfuerzo, incluso en pedidos simples.",
        off_effect="Si lo dejás vacío: se usa el piso estándar (nivel medio).",
        example="Como poner un mínimo de dedicación garantizado a cualquier tarea, por simple que parezca.",
    ),
    # ── integridad_grounding ──────────────────────────────────────────────
    "STACKY_RUN_PREFLIGHT_GATE_ENABLED": PlainHelp(
        what="Antes de lanzar un trabajo, chequea que estén dadas las condiciones básicas para que pueda terminar bien.",
        on_effect="Si la activás: si falta algo básico para que el trabajo funcione, se avisa y se bloquea el lanzamiento antes de arrancar.",
        off_effect="Si la apagás: el trabajo se lanza igual aunque falte algo básico, y el problema aparece recién durante la ejecución.",
        example="Como chequear que el auto tenga nafta y las llaves antes de salir de viaje, en vez de descubrirlo en la ruta.",
    ),
    "STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED": PlainHelp(
        what="Después de que el agente dice haber creado una tarea en el tablero, chequea que esa tarea realmente exista antes de darla por hecha.",
        on_effect="Si la activás: se confirma en el tablero que la tarea existe de verdad antes de cerrar el trámite; si no existe, queda en espera para revisión.",
        off_effect="Si la apagás: se confía en la palabra del agente sin volver a chequear que la tarea exista realmente en el tablero.",
        example="Como llamar al restaurante para confirmar que la reserva quedó anotada, en vez de confiar solo en que alguien dijo que sí.",
    ),
    "STACKY_OUTPUT_GROUNDING_ENABLED": PlainHelp(
        what="Chequea que los archivos y datos que el agente dice haber tocado en su resultado realmente existan.",
        on_effect="Si la activás: cada referencia a un archivo o dato que el agente mencionó se verifica que exista de verdad.",
        off_effect="Si la apagás: no se verifica esa referencia; se confía en lo que el agente cuenta sobre lo que tocó.",
        example="Como comprobar que el número de expediente que te dan corresponde a un expediente real, y no a uno inventado.",
    ),
    "STACKY_OUTPUT_GROUNDING_REPAIR": PlainHelp(
        what="Si se detectan referencias inventadas o rotas en el resultado, le da al agente una oportunidad de corregirlas.",
        on_effect="Si la activás: ante una referencia rota detectada, el agente recibe un intento de corrección dirigido a arreglarla.",
        off_effect="Si la apagás: una referencia rota detectada solo queda anotada, sin intento de corrección.",
        example="Como devolverle a alguien el informe señalando el dato inventado, para que lo verifique y corrija.",
    ),
    # ── epicas_ado ────────────────────────────────────────────────────────
    "STACKY_EPIC_FROM_BRIEF_ENABLED": PlainHelp(
        what="Permite generar una épica (ficha grande de trabajo) a partir de un texto breve que escribís.",
        on_effect="Si la activás: escribís una idea en pocas líneas y el sistema arma la épica completa y la publica en tu tablero.",
        off_effect="Si la apagás: la opción de crear épicas desde un texto breve desaparece; las épicas se crean a mano.",
        example="Le dictás 'quiero un proceso nocturno que cargue archivos de clientes' y aparece la ficha completa en Azure DevOps.",
    ),
    "STACKY_BRIEF_MODEL_SELECT_ENABLED": PlainHelp(
        what="Permite elegir qué modelo de IA y cuánto esfuerzo usar al generar una épica desde un texto breve.",
        on_effect="Si la activás: podés elegir el modelo y el nivel de esfuerzo al generar la épica, dentro de límites de seguridad.",
        off_effect="Si la apagás: se usa siempre el modelo y esfuerzo por defecto para generar épicas.",
        example="Como elegir entre 'rápido y económico' o 'más cuidadoso y detallado' al pedir un trabajo.",
    ),
    "STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED": PlainHelp(
        what="Antes de publicar una épica, chequea que mencione los procesos y sistemas reales del cliente, y avisa si no lo hace.",
        on_effect="Si la activás: si la épica no menciona procesos reales conocidos, aparece un aviso, pero se publica igual.",
        off_effect="Si la apagás: no se hace ese chequeo antes de publicar.",
        example="Como que un editor te avise 'esto no cita ninguna fuente conocida' antes de publicar una nota, sin impedirte publicarla.",
    ),
    "STACKY_EPIC_SUMMARY_ENABLED": PlainHelp(
        what="Después de publicar una épica, agrega un resumen con los datos clave: requerimientos, módulos citados y confianza.",
        on_effect="Si la activás: después de publicar, aparece ese resumen con los datos clave de la épica.",
        off_effect="Si la apagás: la épica se publica sin ese resumen adicional.",
        example="Como adjuntar una ficha técnica resumida junto con un informe extenso.",
    ),
    "STACKY_GROUNDING_OBSERVATORY_ENABLED": PlainHelp(
        what="Muestra un panel con estadísticas generales sobre qué tan bien las épicas generadas citan procesos reales del cliente.",
        on_effect="Si la activás: podés ver ese panel de estadísticas de calidad de las épicas generadas.",
        off_effect="Si la apagás: ese panel no está disponible.",
        example="Como un tablero de control que te muestra el promedio de calidad de un proceso, para detectar tendencias.",
    ),
    "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED": PlainHelp(
        what="Detecta procesos que las épicas mencionan pero que todavía no están en el catálogo oficial del cliente, y los sugiere.",
        on_effect="Si la activás: podés ver una lista de procesos sugeridos para sumar al catálogo, sin que se agreguen solos.",
        off_effect="Si la apagás: esas sugerencias no se muestran.",
        example="Como un asistente que te dice 'esta palabra se repite mucho y no está en tu diccionario, ¿la agregamos?'.",
    ),
    "STACKY_EPIC_SANITIZE_ENABLED": PlainHelp(
        what="Prolija automáticamente la presentación del texto de la épica antes de publicarla, sin cambiar el contenido.",
        on_effect="Si la activás: el texto de la épica se prolija automáticamente antes de publicarse.",
        off_effect="Si la apagás: la épica se publica tal cual la generó el agente, sin ese prolijado automático.",
        example="Como pasarle el corrector de formato a un documento antes de imprimirlo, sin tocar lo que dice.",
    ),
    "STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED": PlainHelp(
        what="Avisa si la épica generada tiene problemas de estructura, como requerimientos repetidos o secciones vacías.",
        on_effect="Si la activás: si hay un problema de estructura en la épica, aparece un aviso, pero se publica igual.",
        off_effect="Si la apagás: no se muestran esos avisos de estructura.",
        example="Como un corrector que te marca 'este párrafo está repetido' sin impedirte entregar el texto.",
    ),
    "STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED": PlainHelp(
        what="Avisa cuando la épica menciona un proceso que no está registrado en el catálogo del cliente.",
        on_effect="Si la activás: si se cita un proceso desconocido, aparece un aviso, pero la épica se publica igual.",
        off_effect="Si la apagás: no se muestra ese aviso de proceso desconocido.",
        example="Como que te avisen 'este nombre de área no está en la lista oficial' sin impedirte seguir.",
    ),
    "STACKY_EPIC_GATE_ENABLED": PlainHelp(
        what="Bloquea la publicación de una épica con problemas graves de contenido, e intenta arreglar sola los problemas menores de forma.",
        on_effect="Si la activás: una épica con problemas graves no se publica y queda para revisar; los problemas menores de forma se intentan arreglar solos.",
        off_effect="Si la apagás: la épica se publica igual aunque tenga esos problemas.",
        example="Como un control de calidad que devuelve el producto con fallas graves, pero arregla solo un detalle de etiqueta.",
    ),
    "STACKY_EPIC_CATALOG_GATE_ENABLED": PlainHelp(
        what="Bloquea la publicación de una épica si menciona un proceso que no existe en el catálogo oficial del cliente.",
        on_effect="Si la activás: citar un proceso inventado o desconocido impide que la épica se publique.",
        off_effect="Si la apagás: citar un proceso desconocido solo genera un aviso (si esa opción está activada), pero no bloquea.",
        example="Como rechazar un pedido que menciona un producto que no existe en el catálogo de la tienda, en vez de solo marcarlo con un asterisco.",
    ),
    "STACKY_ADO_PREVIEW_ENABLED": PlainHelp(
        what="Muestra cómo va a quedar publicada la épica en el tablero antes de publicarla de verdad, sin crear nada todavía.",
        on_effect="Si la activás: podés ver esa vista previa antes de confirmar la publicación real.",
        off_effect="Si la apagás: no hay vista previa disponible; se publica directo.",
        example="Como ver la vista previa de un mensaje antes de enviarlo, para chequear que esté bien antes de mandarlo.",
    ),
    "STACKY_EPIC_PORTFOLIO_ENABLED": PlainHelp(
        what="Permite generar varias épicas distintas a la vez a partir de un mismo texto breve, en vez de una sola.",
        on_effect="Si la activás: de un mismo pedido podés obtener varias épicas alternativas o relacionadas a la vez.",
        off_effect="Si la apagás: cada texto breve genera una sola épica.",
        example="Como pedirle a una agencia 3 propuestas de diseño distintas a partir de la misma idea, en vez de una sola.",
    ),
    "STACKY_EPIC_DECOMPOSITION_ENABLED": PlainHelp(
        what="Después de aprobar una épica grande, permite ver y crear automáticamente las tareas más chicas en las que se divide.",
        on_effect="Si la activás: podés previsualizar y crear las tareas hijas de una épica aprobada con un click.",
        off_effect="Si la apagás: la épica queda sola, sin desglose automático en tareas más chicas.",
        example="Como pedirle a un arquitecto el plano general y que además te arme la lista de tareas para los albañiles.",
    ),
    "STACKY_ADAPTIVE_SELECTOR_ENABLED": PlainHelp(
        what="Elige automáticamente un modelo de IA más potente cuando el pedido es ambiguo, y uno más liviano cuando está claro.",
        on_effect="Si la activás: pedidos poco claros usan un modelo más cuidadoso y caro; pedidos claros usan uno más liviano y barato. Si vos elegís el modelo a mano, tu elección manda.",
        off_effect="Si la apagás: se usa siempre el mismo modelo, sin ajustarlo según qué tan claro esté el pedido.",
        example="Como llamar a un especialista para un caso difícil y a alguien más junior para uno simple, en vez de llamar siempre al mismo.",
    ),
    "STACKY_PROJECT_AUTOPROFILE_ENABLED": PlainHelp(
        what="Arma automáticamente un resumen del proyecto leyendo su documentación existente, sin inventar nada que no esté escrito.",
        on_effect="Si la activás: podés pedir ese resumen automático del proyecto basado en su documentación real.",
        off_effect="Si la apagás: esa función no está disponible.",
        example="Como que alguien te arme un resumen del manual de la empresa leyendo los documentos reales, sin inventar nada.",
    ),
    "STACKY_COMMENT_FULL_SCAN_ENABLED": PlainHelp(
        what="Revisa todo el historial de comentarios de un ítem del tablero, no solo los primeros, para evitar publicar lo mismo dos veces.",
        on_effect="Si la activás: se revisan todos los comentarios existentes, aunque sean muchos, antes de decidir si publicar uno nuevo.",
        off_effect="Si la apagás: solo se revisan los primeros comentarios; con ítems muy comentados podría publicarse algo repetido.",
        example="Como revisar toda la carpeta de un expediente antes de agregar un papel nuevo, no solo la primera hoja.",
    ),
    "STACKY_ISSUE_PHASE_COMMENTS_ENABLED": PlainHelp(
        what="Publica el análisis de un pedido chico (funcional, técnico y de implementación) como comentarios dentro del mismo ítem del tablero.",
        on_effect="Si la activás: cada etapa del análisis queda publicada como comentario en el mismo ítem original.",
        off_effect="Si la apagás: esos comentarios de fase no se publican.",
        example="Como ir agregando notas de avance en el mismo expediente, en vez de abrir un expediente nuevo por cada nota.",
    ),
    "STACKY_TICKETS_PROVIDER_ENABLED": PlainHelp(
        what="Hace que las operaciones sobre tickets funcionen igual sea cual sea el tablero que use el proyecto, no solo uno fijo.",
        on_effect="Si la activás: el sistema usa el conector adecuado según el tablero configurado del proyecto, con Azure DevOps como resguardo si algo falla.",
        off_effect="Si la apagás: las operaciones de tickets siempre asumen Azure DevOps, como hasta ahora.",
        example="Como un enchufe universal que se adapta al tomacorriente del país, en vez de andar solo con un tipo de enchufe.",
    ),
    "STACKY_PIPELINE_PROVIDER_ENABLED": PlainHelp(
        what="Hace que la detección del estado de las canalizaciones de integración continua funcione igual en Azure DevOps o en GitLab.",
        on_effect="Si la activás: el estado de la canalización se detecta con el conector adecuado según dónde viva el proyecto.",
        off_effect="Si la apagás: se usa el comportamiento anterior, pensado solo para Azure DevOps.",
        example="Como un traductor que entiende el estado del semáforo sea cual sea el país en el que estés.",
    ),
    "STACKY_PIPELINE_TRIGGER_ENABLED": PlainHelp(
        what="Permite disparar manualmente una canalización de integración continua en GitLab desde Stacky, y ver su avance.",
        on_effect="Si la activás: podés disparar y seguir el progreso de una canalización de GitLab desde acá, confirmando cada vez.",
        off_effect="Si la apagás: esa opción de disparar canalizaciones no está disponible.",
        example="Como un botón de 'iniciar el lavado' del auto que vos apretás a propósito, no algo que arranca solo.",
    ),
    "STACKY_PIPELINE_GENERATOR_ENABLED": PlainHelp(
        what="Genera automáticamente el archivo de configuración de una canalización de integración continua, mostrando antes una vista previa.",
        on_effect="Si la activás: podés generar y previsualizar esa configuración, y aplicarla al repositorio solo si confirmás.",
        off_effect="Si la apagás: esa generación automática de configuración no está disponible.",
        example="Como un generador de contratos que te muestra el borrador antes de firmarlo.",
    ),
    # ── devops ────────────────────────────────────────────────────────────────
    "STACKY_DEVOPS_PANEL_ENABLED": PlainHelp(
        what="Un editor visual para crear y modificar pipelines de integración continua, sin escribir YAML a mano.",
        on_effect="Si la activás: aparece una sección 'DevOps' donde podés armar pipelines con bloques, previsualizar el YAML y aplicarlo al repositorio.",
        off_effect="Si la apagás: esa sección DevOps no aparece.",
        example="Como un editor de diagramas donde cada bloque es una etapa del pipeline, y el YAML se genera solo.",
    ),
    "STACKY_DEVOPS_PUBLICATIONS_ENABLED": PlainHelp(
        what="Genera pipelines de publicación a partir de los procesos ya cargados en el catálogo del cliente, sin armarlos a mano.",
        on_effect="Si la activás: aparece la sección 'Publicaciones' del panel DevOps, donde podés definir presets (selección, agenda o todo el catálogo) y materializarlos como pipeline.",
        off_effect="Si la apagás: esa sección no aparece y la función de materialización queda deshabilitada.",
        example="Como una plantilla que arma el itinerario de entregas a partir de la lista de paquetes que ya tenés cargada, en vez de escribirlo de cero cada vez.",
    ),
    "STACKY_DEVOPS_ENVIRONMENTS_ENABLED": PlainHelp(
        what="Crea la estructura de carpetas que necesita un ambiente nuevo (entrada, procesamiento, salida) a partir del catálogo del cliente, y lanza la primera publicación.",
        on_effect="Si la activás: aparece la sección 'Ambientes' del panel DevOps, donde podés ver qué carpetas faltan (sin tocar nada) y crearlas recién con tu confirmación. Solo crea carpetas nuevas, nunca borra nada.",
        off_effect="Si la apagás: esa sección no aparece y la inicialización de ambientes queda deshabilitada.",
        example="Como armar los cajones vacíos de un mueble nuevo siguiendo el plano del catálogo, antes de guardar la primera caja adentro.",
    ),
    "STACKY_DEVOPS_AGENT_ENABLED": PlainHelp(
        what="Un asistente DevOps con el que podés chatear ida y vuelta desde la solapa DevOps para diagnosticar, revisar configuraciones y preparar despliegues.",
        on_effect="Si la activás: aparece la sección 'Agente DevOps' donde abrís una conversación y le respondés varios turnos; el agente NUNCA ejecuta algo que cambie estado sin que vos escribas CONFIRMO.",
        off_effect="Si la apagás: esa sección no aparece y las conversaciones con el agente quedan deshabilitadas.",
        example="Encendela para chatear con el agente DevOps desde la solapa DevOps; apagala y la sección desaparece.",
    ),
    "STACKY_DEVOPS_SERVERS_ENABLED": PlainHelp(
        what="Una libreta de servidores Windows con alias: guardás host, usuario y contraseña una vez y te conectás por escritorio remoto con un click.",
        on_effect="Si la activás: aparece la sección 'Servidores' del panel DevOps; podés guardar servidores con alias y conectarte por RDP con 1 click. La contraseña se guarda en el Administrador de credenciales de Windows, nunca en archivos de Stacky.",
        off_effect="Si la apagás: no cambia nada; la sección no aparece y la libreta de servidores queda deshabilitada.",
        example="Como una agenda de contactos, pero de servidores: cargás cada uno una vez y después te conectás sin volver a tipear host ni credenciales.",
    ),
    "STACKY_DEVOPS_PREFLIGHT_ENABLED": PlainHelp(
        what="Un botón te dice si el pipeline va a funcionar antes de dispararlo: revisa el YAML contra Azure DevOps o GitLab de verdad, si quedaron pasos de ejemplo sin editar, si hay algún runner disponible y si usás variables que no definiste.",
        on_effect="Si la activás: aparece el botón '¿Va a funcionar?' en Pipelines (y en Publicaciones). Solo lee información, nunca commitea ni dispara nada — el resultado es un semáforo con el problema y cómo arreglarlo.",
        off_effect="Si la apagás: no cambia nada; el botón no aparece y seguís commiteando/disparando igual que siempre.",
        example="Como el chequeo previo al despegue de un avión: revisa todo antes, pero quien decide despegar seguís siendo vos.",
    ),
    "STACKY_DEVOPS_VARIABLES_ENABLED": PlainHelp(
        what="Gestiona variables del pipeline (credenciales, tokens) desde una sección 'Variables' del panel DevOps, marcando cada una como secreta para que se guarde en el tracker (GitLab masked / ADO isSecret) y nunca en el YAML del repo.",
        on_effect="Si la activás: aparece la sección 'Variables' con candado 🔒, y el builder te avisa si una variable 'parece secreto' (PASSWORD/TOKEN/etc.) para moverla a variable segura en un click. Las secretas se crean en el tracker y JAMÁS aparecen en el YAML ni en logs.",
        off_effect="Si la apagás: no cambia nada; las variables siguen viviendo en el YAML commiteado (riesgo de seguridad si son credenciales).",
        example="Como una caja fuerte: las credenciales van al tracker (que ya tiene los mecanismos correctos de inyección en runtime), el YAML queda limpio.",
    ),
    "STACKY_DEVOPS_PRODUCTION_ENABLED": PlainHelp(
        what="Crea el Merge Request (GitLab) o Pull Request (ADO) hacia la rama principal, muestra el estado del pipeline en vivo y permite mergear con confirmación HITL.",
        on_effect="Si la activás: tras commitear el pipeline, aparece el flujo 'Llevar a producción' con 3 pasos: (1) crear MR/PR, (2) ver el pipeline correr en vivo, (3) mergear con checkbox literal. Nunca auto-merge. ADO gana paridad completa con GitLab (commit/trigger/monitor).",
        off_effect="Si la apagás: no hay MR/PR desde el panel, y el commit ADO sigue con la nota 501 (la paridad ADO de commit/trigger/monitor NO depende de esta flag).",
        example="Como un botón 'Publicar' que primero te muestra el resultado del test en staging, te deja revisarlo y recién con tu confirmación explícita lo lleva a producción.",
    ),
    "STACKY_DEVOPS_STACK_DETECT_ENABLED": PlainHelp(
        what="Un botón te sugiere el tipo de proyecto (Python/Node/.NET) para armar el pipeline con los comandos correctos.",
        on_effect="Si la activás: aparece el botón 'Detectar stack de mi proyecto' en el builder de pipelines, que lee (sin modificar nada) los archivos del proyecto y preselecciona el preset más probable.",
        off_effect="Si la apagás: elegís el preset vos mismo de una lista, sin detección automática.",
        example="Como cuando un formulario te sugiere el país según tu número de teléfono, pero siempre podés cambiarlo vos.",
    ),
    # ── migrador_ado_gitlab ───────────────────────────────────────────────
    "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED": PlainHelp(
        what="Permite mover épicas, tareas y comentarios de Azure DevOps hacia GitLab de forma segura, sin duplicar nada si se repite.",
        on_effect="Si la activás: podés simular la migración primero, sin cambiar nada, y después ejecutarla de verdad, siempre con tu confirmación.",
        off_effect="Si la apagás: esa migración no está disponible.",
        example="Como una mudanza que primero te muestra el inventario de lo que se va a mover, y recién después movés las cosas.",
    ),
    "STACKY_MIGRATOR_EPIC_POLICY": PlainHelp(
        what="Cómo se traducen las épicas de Azure DevOps al migrar a GitLab, según si la cuenta de GitLab tiene funciones pagas o no.",
        on_effect="Si escribís un valor: elegís el modo exacto de traducción de épicas (automático, forzar función paga, o siempre la versión compatible con la gratuita).",
        off_effect="Si lo dejás vacío: se usa el modo automático, que detecta solo qué conviene.",
        example="Como elegir si un documento se traduce con el formato de lujo, si el destino lo soporta, o con uno simple que siempre funciona.",
    ),
    # ── gitlab_deep_links ─────────────────────────────────────────────────
    "STACKY_GITLAB_DEEP_LINKS_ENABLED": PlainHelp(
        what="Convierte las referencias a elementos de GitLab (tareas, cambios de código, commits, épicas) en links clickeables.",
        on_effect="Si la activás: esas referencias aparecen como links que te llevan directo a GitLab con un click.",
        off_effect="Si la apagás: esas referencias se muestran como texto simple, sin link, y hay que buscarlas a mano en GitLab.",
        example="Como que el número de un pedido en un mail sea un link que te lleva directo al pedido, en vez de buscarlo vos.",
    ),
    # ── flujo_funcional ───────────────────────────────────────────────────
    "STACKY_TASK_GATE_ENABLED": PlainHelp(
        what="Revisa automáticamente que la información de una tarea funcional esté bien armada antes de crearla en el tablero.",
        on_effect="Si la activás: antes de crear la tarea, se revisan posibles defectos y se informa el resultado de esa revisión.",
        off_effect="Si la apagás: la tarea se crea directamente, sin esa revisión previa.",
        example="Como revisar que un formulario esté completo antes de presentarlo en la ventanilla.",
    ),
    "STACKY_TASK_GATE_BLOCKING": PlainHelp(
        what="Si la revisión previa de la tarea encuentra un defecto serio, impide que la tarea se cree en el tablero.",
        on_effect="Si la activás: un defecto serio detectado bloquea la creación de la tarea hasta que se corrija.",
        off_effect="Si la apagás: la tarea se crea igual aunque la revisión haya encontrado un defecto serio.",
        example="Como que la ventanilla rechace el formulario si falta un dato obligatorio, en vez de aceptarlo incompleto.",
    ),
    "STACKY_DETERMINISTIC_TASK_STATES_ENABLED": PlainHelp(
        what="Hace que el estado de una tarea en el tablero (en curso, terminada) lo decida la configuración del proyecto, no el agente.",
        on_effect="Si la activás: los estados de la tarea siguen siempre la configuración definida del proyecto, sin importar qué diga el agente.",
        off_effect="Si la apagás: el estado de la tarea puede quedar como lo proponga el agente, que podría no coincidir con la configuración del proyecto.",
        example="Como que el semáforo lo maneje siempre el sistema de tránsito, no lo que crea conveniente cada auto.",
    ),
    # ── routing_costo ─────────────────────────────────────────────────────
    "STACKY_COMPLEXITY_ESTIMATION_ENABLED": PlainHelp(
        what="Estima automáticamente qué tan complejo es un pedido, con una fórmula fija, sin usar inteligencia artificial para decidirlo.",
        on_effect="Si la activás: cada trabajo recibe una estimación automática de su complejidad antes de arrancar.",
        off_effect="Si la apagás: los trabajos no reciben esa estimación automática de complejidad.",
        example="Como una balanza que te dice el peso de un paquete antes de decidir qué camión usar para llevarlo.",
    ),
    "STACKY_DIFFICULTY_ROUTING_ENABLED": PlainHelp(
        what="Elige un modelo de IA más económico para pedidos chicos y uno más potente para pedidos grandes, de forma automática.",
        on_effect="Si la activás: los pedidos chicos usan un modelo más liviano y barato, y los grandes uno más potente; si vos elegís el modelo a mano, tu elección manda.",
        off_effect="Si la apagás: se usa siempre el mismo modelo, sin ajustarlo según el tamaño del pedido.",
        example="Como mandar un mandado simple con la bici y una mudanza grande con el camión, en vez de usar siempre el mismo vehículo.",
    ),
    "STACKY_RUN_ADVISOR_ENABLED": PlainHelp(
        what="Sugiere con qué tipo de agente y modelo conviene hacer un trabajo, basándose en cómo salieron trabajos parecidos antes.",
        on_effect="Si la activás: aparece una recomendación de agente y modelo antes de lanzar el trabajo, que podés seguir o no.",
        off_effect="Si la apagás: no aparece esa recomendación automática.",
        example="Como un GPS que te sugiere una ruta según el tránsito, pero vos podés elegir otra si querés.",
    ),
    "STACKY_RUN_ADVISOR_ENFORCE": PlainHelp(
        what="Si no elegís vos con qué agente correr un trabajo, usa automáticamente la recomendación sugerida en vez de dejarlo sin definir.",
        on_effect="Si la activás: cuando no elegís agente a mano, se usa automáticamente el recomendado.",
        off_effect="Si la apagás: sin tu elección manual, no se fuerza ninguna recomendación automática.",
        example="Como que el GPS tome la ruta sugerida si vos no elegiste ninguna, pero respete la tuya si la elegiste.",
    ),
    "STACKY_BUDGET_PER_TICKET_USD": PlainHelp(
        what="El gasto máximo permitido en dólares para trabajar un mismo ticket, sumando todos sus intentos.",
        on_effect="Si le ponés un valor: al acercarse a ese gasto, se pasa a un modelo más económico; si aun así se supera, el trabajo se corta salvo que decidas forzarlo.",
        off_effect="Si lo dejás en cero: no hay tope de gasto por ticket.",
        example="Como un límite de gasto mensual en una tarjeta prepaga para un mismo trámite.",
    ),
    "STACKY_RUN_CACHE_DAYS": PlainHelp(
        what="Durante cuántos días se sugiere reusar el resultado de un trabajo idéntico ya hecho antes, en vez de rehacerlo de cero.",
        on_effect="Si subís el número: se sugiere reusar resultados de trabajos idénticos hechos hasta esa cantidad de días atrás.",
        off_effect="Si lo dejás en cero: no se sugiere reusar ningún resultado anterior.",
        example="Como que te avisen 'ya resolviste esto la semana pasada, ¿querés usar esa respuesta?' antes de repetir el trabajo.",
    ),
    "STACKY_EVALS_INTERVAL_HOURS": PlainHelp(
        what="Cada cuántas horas se corre automáticamente una batería de pruebas de calidad sobre el sistema en general.",
        on_effect="Si le ponés un número de horas: esa batería de pruebas se corre sola, cada tanto, sin que nadie la dispare a mano.",
        off_effect="Si lo dejás en cero: esa batería de pruebas no se corre sola; hay que dispararla a mano.",
        example="Como un chequeo médico de rutina programado cada tantos meses, en vez de ir al médico solo cuando algo duele.",
    ),
    "STACKY_EVAL_GATE_MODE": PlainHelp(
        what="Qué tan estricto es el control de calidad al importar un nuevo agente: apagado, solo avisando, o bloqueando la importación.",
        on_effect="Si elegís el modo de aviso: se avisa si hay un problema de calidad, pero se importa igual. Si elegís el modo estricto: se rechaza la importación si hay un problema.",
        off_effect="Si lo dejás apagado o vacío: no se hace ese control al importar.",
        example="Como un control de aduana que solo anota lo irregular, o que directamente no deja pasar la mercadería.",
    ),
    "STACKY_MAX_CONCURRENT_RUNS": PlainHelp(
        what="Cuántos agentes pueden estar trabajando al mismo tiempo como máximo.",
        on_effect="Si subís el número: más trabajos corren en paralelo, pero la máquina y el gasto suben.",
        off_effect="Si lo bajás: menos trabajos a la vez y la máquina más tranquila; ojo, si lo dejás en cero se quita el tope y vuelve a ser ilimitado.",
        example="Como las cajas abiertas de un supermercado: más cajas = menos fila, pero más cajeros que pagar.",
    ),
    # ── fiabilidad_ciclo_vida ─────────────────────────────────────────────
    "STACKY_RUNNER_REAP_ON_CLOSE_ENABLED": PlainHelp(
        what="Se asegura de cerrar bien el proceso de un agente cuando su trabajo termina, para que no quede consumiendo recursos.",
        on_effect="Si la activás: al terminar un trabajo, su proceso se cierra prolijamente y se fuerza el cierre si no responde.",
        off_effect="Si la apagás: el proceso puede quedar sin cerrarse explícitamente al terminar el trabajo.",
        example="Como apagar la estufa después de usarla, en vez de dejarla prendida por las dudas.",
    ),
    "STACKY_LOG_FLUSH_INCREMENTAL_ENABLED": PlainHelp(
        what="Guarda el historial de lo que hizo el agente de a poco durante el trabajo, no solo al terminar.",
        on_effect="Si la activás: el historial se va guardando durante el trabajo, así no se pierde nada si algo se corta antes de tiempo.",
        off_effect="Si la apagás: el historial se guarda recién al cerrar el trabajo normalmente.",
        example="Como ir guardando un documento mientras lo escribís, en vez de guardarlo recién al cerrarlo.",
    ),
    "STACKY_ORPHAN_REAPER_ENABLED": PlainHelp(
        what="Limpieza automática de procesos que quedaron colgados sin que nadie los use.",
        on_effect="Si la activás: cada tanto se buscan y cierran procesos abandonados, liberando memoria de la máquina.",
        off_effect="Si la apagás: los procesos colgados quedan vivos hasta que alguien los cierre a mano.",
        example="Como apagar las luces de las oficinas vacías cada una hora.",
    ),
    "STACKY_ORPHAN_REAPER_INTERVAL_SEC": PlainHelp(
        what="Cada cuántos segundos se repite la limpieza automática de procesos abandonados, además de al arrancar el sistema.",
        on_effect="Si le ponés un número de segundos: la limpieza se repite periódicamente con esa frecuencia.",
        off_effect="Si lo dejás en cero: la limpieza solo se hace una vez al arrancar el sistema, no de forma periódica.",
        example="Como decidir si la limpieza de oficinas se hace solo a primera hora, o además cada tantas horas durante el día.",
    ),
    "STACKY_STALL_WATCHDOG_SECONDS": PlainHelp(
        what="Cuánto tiempo sin ninguna novedad de un trabajo se tolera antes de darlo por trabado y cerrarlo con error.",
        on_effect="Si le ponés un número de segundos: si el trabajo queda en silencio más de ese tiempo, se cierra automáticamente como trabado.",
        off_effect="Si lo dejás en cero: no se detecta ese silencio; un trabajo trabado puede quedar corriendo indefinidamente.",
        example="Como colgar el teléfono si la otra persona queda en silencio demasiado tiempo, en vez de esperar para siempre.",
    ),
    "STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED": PlainHelp(
        what="Revisa que los datos de una tarea pendiente estén completos y sean coherentes antes de crearla de verdad en el tablero.",
        on_effect="Si la activás: una tarea con datos incompletos o inconsistentes queda apartada para revisar, en vez de crearse mal.",
        off_effect="Si la apagás: la tarea se crea igual aunque tenga datos incompletos o inconsistentes.",
        example="Como que el cajero automático rechace un formulario mal completado, en vez de procesarlo como está.",
    ),
    "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED": PlainHelp(
        what="Evita que un mismo trabajo termine publicado dos veces en el tablero si hay un reintento por una falla momentánea.",
        on_effect="Si la activás: si el sistema reintenta publicar algo que ya se publicó, detecta la marca previa y no lo duplica.",
        off_effect="Si la apagás: un reintento podría terminar publicando el mismo contenido dos veces.",
        example="Como que el cajero automático no te cobre dos veces si apretaste 'confirmar' dos veces por las dudas.",
    ),
    "STACKY_RUNAWAY_MAX_TURNS": PlainHelp(
        what="Cuántas idas y vueltas como máximo puede tener un agente trabajando en un mismo pedido antes de cortarlo por las dudas.",
        on_effect="Si le ponés un número: si el agente se pasa de esa cantidad de idas y vueltas, el trabajo se corta y queda marcado para revisar.",
        off_effect="Si lo dejás en cero: no hay ese límite; el agente puede seguir indefinidamente.",
        example="Como poner un límite de vueltas a una negociación antes de decir 'esto lo tiene que mirar una persona'.",
    ),
    "STACKY_RUNAWAY_MAX_COST_USD": PlainHelp(
        what="Freno de emergencia por costo: cuánto puede gastar un trabajo antes de que se lo frene.",
        on_effect="Si le ponés un valor: un trabajo que se desboca y gasta de más se corta y queda marcado para que lo revises (hoy este freno solo funciona con el agente de Claude).",
        off_effect="Si lo dejás en cero: no hay tope, y un trabajo descontrolado puede gastar sin límite.",
        example="Como el límite de la tarjeta de crédito: si algo intenta gastar de más, la operación se bloquea.",
    ),
    "STACKY_RUN_REPAIR_ENABLED": PlainHelp(
        what="Si el trabajo termina sin resultado o con un archivo de datos roto, le da al agente una única oportunidad más de intentarlo bien.",
        on_effect="Si la activás: ante un resultado vacío o roto, se reintenta una vez más automáticamente.",
        off_effect="Si la apagás: un resultado vacío o roto queda así, sin reintento automático.",
        example="Como volver a apretar el botón una vez si la máquina expendedora no largó el producto, antes de llamar a un técnico.",
    ),
    "STACKY_TRANSIENT_RUN_RETRY_ENABLED": PlainHelp(
        what="Reintentaría automáticamente un trabajo que falló por un problema pasajero de conexión o sistema (función preparada, todavía sin activar).",
        on_effect="Si la activás: hoy no cambia el comportamiento; la detección confiable de errores pasajeros todavía no está lista.",
        off_effect="Si la apagás: no hay reintento automático por errores pasajeros (comportamiento actual).",
        example="Como un botón instalado en el tablero que todavía no está conectado a nada.",
    ),
    "STACKY_TRANSIENT_RUN_RETRY_MAX": PlainHelp(
        what="Cuántas veces se reintentaría un trabajo que falló por un problema pasajero (función todavía sin activar de verdad).",
        on_effect="Si subís el número: se permitirían más reintentos el día que esta función quede activa.",
        off_effect="Si lo bajás: se permitirían menos reintentos; hoy no tiene efecto porque la función no está activa.",
        example="Como fijar de antemano cuántos reintentos tendrá un mecanismo que todavía no está encendido.",
    ),
    "STACKY_ARTIFACT_INTAKE_ENABLED": PlainHelp(
        what="Revisa y corrige automáticamente los archivos que un agente entrega como resultado, antes de mandarlos al tablero.",
        on_effect="Si la activás: cada archivo entregado pasa por una revisión y corrección automática antes de subirse al tablero.",
        off_effect="Si la apagás: los archivos entregados se suben al tablero tal cual, sin esa revisión adicional.",
        example="Como un control de calidad antes de despachar un paquete, corrigiendo la etiqueta si viene mal.",
    ),
    "STACKY_ARTIFACT_RESCUE_ENABLED": PlainHelp(
        what="Si el agente termina contando lo que hizo en vez de entregar el resultado esperado, el sistema rescata el archivo que ya guardó y lo publica.",
        on_effect="Si la activás: se rescata y publica el archivo real que el agente ya había guardado, aunque no lo haya entregado como se esperaba.",
        off_effect="Si la apagás: si el agente no entrega el resultado como se esperaba, no se rescata nada automáticamente.",
        example="Como ir a buscar el trabajo que el empleado ya dejó impreso en la bandeja, aunque se haya olvidado de avisarte.",
    ),
    # ── observabilidad_notif ──────────────────────────────────────────────
    "STACKY_RELIABILITY_KPIS_ENABLED": PlainHelp(
        what="Muestra en el panel de salud indicadores sobre qué tan bien está funcionando el sistema en general.",
        on_effect="Si la activás: esos indicadores de fiabilidad (fallas, recuperaciones, tiempos) aparecen en el panel de salud.",
        off_effect="Si la apagás: esos indicadores no se muestran.",
        example="Como el tablero de indicadores de una fábrica que muestra fallas y tiempos de producción.",
    ),
    "STACKY_QUALITY_KPIS_ENABLED": PlainHelp(
        what="Muestra en el panel de salud qué porcentaje de trabajos salen bien a la primera, sin necesitar correcciones.",
        on_effect="Si la activás: ese indicador de calidad aparece en el panel de salud.",
        off_effect="Si la apagás: ese indicador no se muestra.",
        example="Como el indicador de 'productos sin devolución' de una fábrica.",
    ),
    "STACKY_INTEGRITY_KPIS_ENABLED": PlainHelp(
        what="Muestra en el panel de salud indicadores sobre cuántos problemas se evitaron a tiempo y cuántos éxitos falsos se detectaron.",
        on_effect="Si la activás: esos indicadores de integridad aparecen en el panel de salud.",
        off_effect="Si la apagás: esos indicadores no se muestran.",
        example="Como un indicador de cuántos productos con falla se frenaron antes de salir a la venta.",
    ),
    "STACKY_EXEC_VERIFICATION_KPIS_ENABLED": PlainHelp(
        what="Muestra en el panel de salud indicadores sobre los resultados de la prueba real del código: aprobados, recuperados, fallas detectadas.",
        on_effect="Si la activás: esos indicadores de la prueba real del código aparecen en el panel de salud.",
        off_effect="Si la apagás: esos indicadores no se muestran.",
        example="Como el indicador de cuántas piezas pasaron el control de calidad a la primera en una fábrica.",
    ),
    "STACKY_ACCEPTANCE_KPIS_ENABLED": PlainHelp(
        what="Muestra en el panel de salud indicadores sobre qué tan bien los trabajos cumplen el examen automático derivado de cada pedido.",
        on_effect="Si la activás: esos indicadores del examen automático aparecen en el panel de salud.",
        off_effect="Si la apagás: esos indicadores no se muestran.",
        example="Como un resumen de cuántos exámenes de calidad se aprobaron a la primera.",
    ),
    "STACKY_EXECUTION_HISTORY_ENABLED": PlainHelp(
        what="Muestra un historial completo de todos los trabajos hechos: cuánto tardaron, cuánto costaron, y qué produjeron.",
        on_effect="Si la activás: podés consultar ese historial completo con filtros por proyecto, agente, fecha y estado.",
        off_effect="Si la apagás: ese historial detallado no está disponible.",
        example="Como el resumen de movimientos de una cuenta bancaria, con filtros por fecha y tipo de gasto.",
    ),
    "STACKY_ADO_RUN_FOOTER_ENABLED": PlainHelp(
        what="Agrega una firma visible al final de los comentarios y tareas que dice qué agente y modelo hizo el trabajo.",
        on_effect="Si la activás: cada comentario o tarea publicada lleva esa firma con los datos del agente que la hizo.",
        off_effect="Si la apagás: los comentarios y tareas se publican sin esa firma.",
        example="Como el sello de 'hecho por' que deja un técnico en el informe de servicio.",
    ),
    "STACKY_WEBHOOKS_V2_ENABLED": PlainHelp(
        what="Envía avisos automáticos a sistemas externos cuando un trabajo termina, falla, o queda para revisar.",
        on_effect="Si la activás: esos avisos se envían automáticamente a los sistemas externos conectados.",
        off_effect="Si la apagás: esos avisos automáticos no se envían.",
        example="Como que un sistema le avise a otro 'ya terminé' automáticamente, en vez de que alguien avise a mano.",
    ),
    "STACKY_DESKTOP_NOTIFY_ENABLED": PlainHelp(
        what="Avisos emergentes en tu computadora cuando un agente termina o necesita tu atención.",
        on_effect="Si la activás: te salta una notificación en la pantalla al terminar un trabajo, sin tener que mirar la aplicación.",
        off_effect="Si la apagás: no hay avisos; te enterás solo cuando entrás a mirar la aplicación.",
        example="Como el timbre del microondas: podés irte a hacer otra cosa y te avisa cuando está listo.",
    ),
    "STACKY_LIVE_TELEMETRY_ENABLED": PlainHelp(
        what="Muestra en tiempo real cómo va progresando un trabajo mientras corre: idas y vueltas y cuánto va costando.",
        on_effect="Si la activás: podés ver ese progreso en vivo mientras el trabajo está corriendo.",
        off_effect="Si la apagás: no hay esa vista en vivo; solo ves el resultado al terminar.",
        example="Como ver el taxímetro correr durante el viaje, en vez de enterarte del total recién al bajarte.",
    ),
    "STACKY_OPERATIONAL_HEALTH_ENABLED": PlainHelp(
        what="Muestra un panel que agrupa los trabajos problemáticos (para revisar, fallidos, caros o colgados) para repasarlos fácil.",
        on_effect="Si la activás: ese panel de trabajos problemáticos está disponible.",
        off_effect="Si la apagás: ese panel no está disponible, aunque los trabajos problemáticos sigan existiendo sin agrupar.",
        example="Como una bandeja de 'para revisar' separada de la bandeja de entrada general, para no perderte lo urgente.",
    ),
    "STACKY_PIPELINES_ENABLED": PlainHelp(
        what="Permite encadenar varios trabajos en etapas sucesivas, pausando automáticamente si alguna etapa falla.",
        on_effect="Si la activás: podés armar y correr esas cadenas de trabajos por etapas.",
        off_effect="Si la apagás: esa función de cadenas de trabajo no está disponible; cada trabajo se lanza por separado.",
        example="Como una línea de montaje que se detiene sola si una estación tiene un problema, en vez de seguir a ciegas.",
    ),
    "STACKY_EXECUTION_TRACE_ENABLED": PlainHelp(
        what="Guarda datos de trazabilidad de cada trabajo: qué agente lo hizo, con qué pedido exacto, y qué archivos produjo.",
        on_effect="Si la activás: cada trabajo queda con esos datos de trazabilidad guardados.",
        off_effect="Si la apagás: esos datos de trazabilidad no se guardan.",
        example="Como el número de seguimiento de un envío, que te permite rastrear exactamente qué pasó con tu pedido.",
    ),
    "STACKY_TRACE_PROMPT_TEXT_ENABLED": PlainHelp(
        what="Guarda también el texto completo del pedido interno que recibió el agente, no solo los datos básicos de trazabilidad.",
        on_effect="Si la activás: se guarda el texto completo enviado al agente; usalo solo si ese contenido no es sensible.",
        off_effect="Si la apagás: no se guarda ese texto completo, solo los datos básicos de trazabilidad (recomendado por privacidad).",
        example="Como decidir si además del número de seguimiento de un envío, se guarda también una foto del contenido del paquete.",
    ),
    "STACKY_DIGEST_INTERVAL_HOURS": PlainHelp(
        what="Cada cuántas horas se genera un resumen periódico de la actividad del sistema.",
        on_effect="Si le ponés un número de horas: ese resumen se genera automáticamente cada tanto.",
        off_effect="Si lo dejás en cero: no se genera ese resumen periódico.",
        example="Como un boletín semanal automático con el resumen de lo que pasó, en vez de armarlo a mano.",
    ),
    "STACKY_ADO_FAILURE_COMMENT_ENABLED": PlainHelp(
        what="Publica automáticamente un comentario con el diagnóstico del problema cuando un trabajo falla o queda para revisar.",
        on_effect="Si la activás: ese comentario de diagnóstico se publica solo, en el mismo ítem del tablero.",
        off_effect="Si la apagás: no se publica ese comentario automático de diagnóstico.",
        example="Como que el técnico deje anotado en la orden de servicio qué fue lo que falló, para que quede a la vista.",
    ),
    "STACKY_UNBLOCKER_COMPLETED_CAP": PlainHelp(
        what="Cuántos tickets ya completados como máximo se muestran en el panel de tickets trabados, para no saturarlo de historial viejo.",
        on_effect="Si subís el número: se muestran más tickets completados en ese panel.",
        off_effect="Si lo bajás: se muestran menos tickets completados; si lo dejás en cero, se muestran todos sin límite.",
        example="Como mostrar solo los últimos 50 mensajes leídos de una bandeja, en vez de toda la historia.",
    ),
    # ── aprendizaje ───────────────────────────────────────────────────────
    "STACKY_PUSH_REJECTIONS_ENABLED": PlainHelp(
        what="Hace que el sistema aprenda de los trabajos que rechazaste, para no repetir el mismo error.",
        on_effect="Si la activás: cada rechazo tuyo se convierte en una lección que los agentes reciben en los próximos trabajos.",
        off_effect="Si la apagás: los rechazos no dejan enseñanza; el mismo error puede repetirse.",
        example="Como un empleado que anota 'al jefe no le gusta X' después de cada devolución, y no tropieza dos veces.",
    ),
    "STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED": PlainHelp(
        what="Guarda la nota que vos escribís al revisar un trabajo, para que quede disponible como aprendizaje en futuros trabajos.",
        on_effect="Si la activás: tu nota de revisión queda guardada como un recuerdo reutilizable para el sistema.",
        off_effect="Si la apagás: tu nota de revisión no se guarda como recuerdo reutilizable.",
        example="Como que un supervisor anote sus observaciones en la ficha del empleado para consultarlas más adelante.",
    ),
    "STACKY_ADO_EDIT_LEARNING_ENABLED": PlainHelp(
        what="Detecta cuando corregís a mano algo que un agente publicó en el tablero, y guarda esa corrección como una lección.",
        on_effect="Si la activás: tus correcciones manuales al contenido publicado se convierten en lecciones guardadas automáticamente.",
        off_effect="Si la apagás: tus correcciones manuales no se convierten en lecciones; quedan solo como el cambio que hiciste.",
        example="Como que un aprendiz tome nota cada vez que el jefe le corrige un informe, para no repetir el mismo error.",
    ),
    "STACKY_ADO_EDIT_SWEEP_HOURS": PlainHelp(
        what="Cada cuántas horas el sistema revisa si hiciste correcciones manuales a lo que publicó un agente.",
        on_effect="Si subís el número: esa revisión de tus correcciones se hace con menos frecuencia.",
        off_effect="Si lo bajás: esa revisión se hace más seguido.",
        example="Como decidir cada cuántas horas alguien pasa a ver si corregiste algo en el pizarrón.",
    ),
    "STACKY_ADO_SERVICE_IDENTITY": PlainHelp(
        what="Los nombres de usuario con los que el propio sistema publica en el tablero, para no confundir sus cambios con los tuyos.",
        on_effect="Si escribís esos nombres separados por coma: los cambios hechos con esos usuarios no cuentan como corrección humana.",
        off_effect="Si lo dejás vacío: el sistema intenta adivinar solo cuáles cambios son del sistema y cuáles tuyos.",
        example="Como que la fotocopiadora no cuente sus propias marcas de agua como si fueran anotaciones tuyas.",
    ),
    "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED": PlainHelp(
        what="Guarda lo que vos borrás al corregir el contenido publicado, para que el sistema aprenda a no volver a proponer eso.",
        on_effect="Si la activás: lo que borraste queda guardado como un ejemplo de 'esto no va', y el control de calidad avisa si reaparece.",
        off_effect="Si la apagás: lo que borrás no queda guardado como ejemplo negativo para el futuro.",
        example="Como que un editor anote 'esta frase no la quiero ver más' y te avise si alguien la vuelve a escribir.",
    ),
    # ── preflight_intencion ───────────────────────────────────────────────
    "INTENT_PREFLIGHT_ENABLED": PlainHelp(
        what="Antes de lanzar un trabajo, genera un resumen de lo que va a hacer para que lo apruebes o corrijas primero.",
        on_effect="Si la activás: aparece ese resumen previo para tu aprobación antes de que el trabajo arranque de verdad.",
        off_effect="Si la apagás: el trabajo arranca directo, sin ese resumen previo para aprobar.",
        example="Como que te muestren el presupuesto antes de arrancar la obra, para que lo apruebes o lo corrijas.",
    ),
    "INTENT_PREFLIGHT_AUTO_APPROVE": PlainHelp(
        what="Si el resumen previo del trabajo está muy claro y sin dudas, lo aprueba solo sin pedirte que confirmes cada vez.",
        on_effect="Si la activás: cuando el resumen previo está claro, se aprueba solo, sin interrumpirte con una ventana de confirmación.",
        off_effect="Si la apagás: siempre se te pide confirmar el resumen previo, por más claro que esté.",
        example="Como que el asistente no te pregunte algo obvio, pero sí te pregunte en los casos dudosos.",
    ),
    "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF": PlainHelp(
        what="Qué tan seguro tiene que estar el sistema, en una escala de 0 a 1, para aprobar solo el resumen previo sin preguntarte.",
        on_effect="Si subís el número, más cerca de 1: hace falta más seguridad para aprobar solo, y te va a preguntar más seguido.",
        off_effect="Si lo bajás, más cerca de 0: aprueba solo con menos seguridad, preguntándote menos seguido.",
        example="Como bajar o subir la vara de 'esto está tan claro que no hace falta preguntar'.",
    ),
    # ── base_datos ────────────────────────────────────────────────────────
    "STACKY_DB_READONLY_DIRECTIVE_ENABLED": PlainHelp(
        what="Le indica al agente que use un usuario de la base de datos que solo puede leer, nunca modificar, al consultarla.",
        on_effect="Si la activás: el agente recibe la indicación de usar ese usuario de solo lectura al consultar la base de datos del cliente.",
        off_effect="Si la apagás: el agente no recibe esa indicación explícita sobre qué usuario usar.",
        example="Como darle a un auditor una llave que solo abre para mirar, nunca para modificar el archivo.",
    ),
    "STACKY_ADO_READ_CACHE_TTL_SEC": PlainHelp(
        what="Cuánto tiempo, en segundos, se guarda en memoria una consulta reciente al tablero, para no pedirla de nuevo enseguida.",
        on_effect="Si le ponés un número de segundos: las consultas recientes se reusan durante ese tiempo, ahorrando consultas repetidas.",
        off_effect="Si lo dejás en cero: cada consulta se pide de nuevo siempre, sin reusar nada guardado.",
        example="Como anotar en un papelito la respuesta de una pregunta reciente, para no tener que preguntar de nuevo enseguida.",
    ),
    "STACKY_ADO_PREWARM_ENABLED": PlainHelp(
        what="Adelanta en segundo plano las consultas más pesadas al tablero, para que el próximo trabajo las encuentre ya guardadas.",
        on_effect="Si la activás: esas consultas pesadas se adelantan en segundo plano antes de que se necesiten.",
        off_effect="Si la apagás: cada trabajo espera a hacer esas consultas pesadas recién cuando las necesita.",
        example="Como calentar el horno antes de que llegue la comida, para no hacer esperar cuando haga falta.",
    ),
    # ── avanzado ──────────────────────────────────────────────────────────
    "STACKY_CLI_EGRESS_ENABLED": PlainHelp(
        what="Revisa el contenido final que se le va a mandar al agente contra reglas de seguridad, antes de lanzar el trabajo.",
        on_effect="Si la activás: si el contenido final viola una regla de seguridad, el trabajo no se lanza y termina con error.",
        off_effect="Si la apagás: no se hace esa revisión de reglas antes de lanzar el trabajo.",
        example="Como el control de equipaje antes de embarcar: si algo no está permitido, no sube al avión.",
    ),
    "STACKY_SPECULATIVE_ENABLED": PlainHelp(
        what="Función experimental que adelanta en segundo plano parte del trabajo antes de que confirmes, para ganar tiempo.",
        on_effect="Si la activás: el sistema puede empezar a adelantar trabajo antes de tu confirmación final, por si acierta lo que ibas a pedir.",
        off_effect="Si la apagás: nada se adelanta; el trabajo arranca recién después de tu confirmación, como siempre.",
        example="Como un mozo que empieza a preparar el plato más pedido antes de que confirmes, por si es justo el que vas a elegir.",
    ),
    "STACKY_SPECULATIVE_MODE": PlainHelp(
        what="Cómo se comporta la función experimental de adelanto de trabajo: apenas puede, o de forma diferida.",
        on_effect="Si escribís un modo: elegís cuándo arranca el adelanto de trabajo (hoy ambos modos se comportan igual).",
        off_effect="Si lo dejás vacío, o la función principal está apagada: este valor no tiene ningún efecto.",
        example="Como elegir 'arrancar ya' o 'arrancar en un rato' para una tarea que hoy arranca igual en ambos casos.",
    ),
    "STACKY_CODEBASE_MEMORY_MCP_ENABLED": PlainHelp(
        what="Permite conectar un programa externo, instalado aparte, que indexa el código fuente del proyecto para que el agente lo consulte mejor.",
        on_effect="Si la activás: podés conectar ese programa externo, que tenés que instalar vos, para que el agente lo use.",
        off_effect="Si la apagás: esa integración no está disponible; nada cambia respecto de hoy.",
        example="Como habilitar el enchufe para un electrodoméstico que vos compraste aparte; sin el aparato, el enchufe no hace nada solo.",
    ),
    "STACKY_CODEBASE_MEMORY_MCP_PROJECTS": PlainHelp(
        what="En qué proyectos se usa el programa externo de indexado de código, cuando esa función está activada en general.",
        on_effect="Si escribís nombres de proyectos separados por coma: el programa externo se conecta solo en esos proyectos.",
        off_effect="Si lo dejás vacío: se conecta en todos los proyectos, si la función principal está activada y la ruta está seteada.",
        example="Como elegir en qué sucursales instalar un equipo nuevo, en vez de instalarlo en todas de una.",
    ),
    "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH": PlainHelp(
        what="La ubicación exacta en tu computadora donde está instalado el programa externo de indexado de código.",
        on_effect="Si escribís la ruta: el sistema sabe dónde encontrar ese programa externo para usarlo.",
        off_effect="Si lo dejás vacío: no se intenta usar ningún programa externo (opción más segura).",
        example="Como anotar en qué cajón guardaste la herramienta, para que alguien sepa dónde buscarla.",
    ),
}


def plain_help_for(key: str) -> dict | None:
    """Devuelve la ayuda llana serializable de una key, o None si no existe."""
    entry = PLAIN_HELP.get(key)
    if entry is None:
        return None
    return {
        "what": entry.what,
        "on_effect": entry.on_effect,
        "off_effect": entry.off_effect,
        "example": entry.example,
    }
