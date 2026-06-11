---
name: plan-de-pruebas-general
description: Cómo estructurar un plan de pruebas genérico para cualquier feature
agents: []
projects: []
keywords: [plan de pruebas, casos de prueba, testing, regresión, test plan]
---

## Plan de pruebas — estructura general

Cuando el agente deba producir un plan de pruebas, seguir este esquema:

### 1. Identificación
- Nombre del feature / ticket ADO
- Versión del sistema bajo prueba
- Responsable QA

### 2. Alcance
- Funcionalidades incluidas (positivas y negativas)
- Funcionalidades excluidas con justificación

### 3. Casos de prueba
Para cada caso registrar:
- ID único (TC-NNN)
- Precondición
- Pasos de ejecución
- Resultado esperado
- Severidad: crítica / alta / media / baja

### 4. Casos de regresión mínimos
- Flujo principal (happy path)
- Caso de error más común
- Integración con el módulo upstream más relevante

### 5. Criterios de aceptación
- 100 % de casos críticos/altos en PASS
- Sin bloqueantes abiertos al momento del sign-off

### 6. Registro de ejecución
Tabla: ID | Entorno | Fecha | Ejecutor | Resultado | Notas
