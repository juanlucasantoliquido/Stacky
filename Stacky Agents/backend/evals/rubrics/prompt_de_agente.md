RUBRICA: prompt_de_agente v1
Evaluás el PROMPT DE SISTEMA de un agente de Stacky. Buscá defectos concretos, no elogios.
Criterios (cada uno pesa igual):
1. Rol y objetivo: el prompt define QUIÉN es el agente y QUÉ debe lograr, sin ambigüedad.
2. Contrato de salida: formato de salida esperado explícito (secciones, JSON, artefactos) y verificable.
3. Límites y rieles: dice qué NO debe hacer (no inventar datos, no salirse del alcance, human-in-the-loop).
4. Accionabilidad: instrucciones ejecutables por un modelo menor sin inferir contexto no dado.
5. Consistencia interna: sin instrucciones contradictorias ni redundancia que diluya las reglas.
Devolvé score entre 0 y 1 (promedio de criterios) y una crítica que liste los defectos más graves con la frase exacta del prompt que los causa.
