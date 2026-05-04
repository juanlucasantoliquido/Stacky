# Stacky Agents — Instalador Portable

Guía para llevar Stacky Agents a cualquier máquina Windows desde cero.

---

## Requisitos del sistema

| Herramienta | Versión mínima | Obligatorio |
|-------------|---------------|-------------|
| Windows | 10 / 11 | Si |
| PowerShell | 5.1+ | Si (ya incluido en Windows) |
| winget | cualquiera | Si (para auto-instalar prereqs) |
| Python | 3.11+ | Si (el instalador lo descarga si falta) |
| Node.js | 18 LTS+ | Si (el instalador lo descarga si falta) |
| Git | cualquiera | Si (el instalador lo descarga si falta) |
| GitHub CLI (`gh`) | cualquiera | No (recomendado para PRs y auth) |
| VS Code | cualquiera | No (requerido solo para integración Copilot) |
| Ollama | cualquiera | No (solo para StackyBrain / LLM local) |

> winget viene preinstalado en Windows 10 1709+ y Windows 11. Si no está disponible, instala los prereqs manualmente antes de ejecutar el instalador.

---

## Instalación en máquina nueva

### Paso 1 — Copiar el proyecto

Copia la carpeta `Stacky/` al equipo destino en cualquier ruta. El instalador detecta su propia ubicación, no hay rutas hardcodeadas.

```
C:\MiCarpeta\Stacky\          <- puede estar en cualquier ruta
├── INSTALL.ps1
├── START.bat
├── Stacky Agents\
├── Stacky pipeline\
├── Stacky tools\
└── StackyBrain\
```

### Paso 2 — Ejecutar el instalador

Abre PowerShell en la carpeta raíz de `Stacky/` y ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

O si PowerShell ya permite scripts locales:

```powershell
.\INSTALL.ps1
```

El instalador realiza estos pasos en orden:

1. Detecta Python 3.11+ — lo instala via `winget` si falta
2. Detecta Node.js 18+ — lo instala via `winget` si falta
3. Detecta Git — lo instala via `winget` si falta
4. Detecta gh CLI — lo instala via `winget` si falta (no bloquea)
5. Detecta VS Code — informa si falta (no bloquea)
6. Crea el virtualenv Python en `Stacky Agents\backend\.venv\`
7. Instala dependencias Python del backend (`Flask`, `SQLAlchemy`, etc.)
8. Instala dependencias del pipeline (`Playwright`, `pytest`, etc.) + Chromium
9. Instala dependencias del QA UAT Agent
10. Instala dependencias npm del frontend (`React`, `Vite`, `TypeScript`)
11. Instala la extensión VS Code `.vsix` si VS Code está disponible
12. Crea `Stacky Agents\backend\.env` desde `.env.example` con setup interactivo para ADO
13. Crea el directorio `data/` si no existe
14. Valida que todo funciona correctamente

El instalador es **idempotente**: si ya está instalado, no sobreescribe nada. Se puede volver a ejecutar sin riesgo.

### Paso 3 — Configurar Azure DevOps

Durante la instalación el script pregunta si configurar ADO ahora. Si se omite, editar el archivo directamente:

```
Stacky Agents\backend\.env
```

```env
ADO_ORG=MiOrganizacion
ADO_PROJECT=MiProyecto
ADO_PAT=elTokenPersonalDeAcceso
```

El PAT necesita permisos de lectura/escritura sobre Work Items y Code en el proyecto ADO.

### Paso 4 — Autenticar GitHub CLI (si se instaló)

```powershell
gh auth login
```

Seguir el wizard interactivo. Stacky usa gh para crear PRs y leer tokens de Copilot.

---

## Uso diario

Una vez instalado, para usar Stacky basta con:

```
START.bat
```

Esto arranca el backend Flask (puerto 5050) y el frontend React (puerto 5173) en ventanas separadas y abre el navegador automáticamente en `http://localhost:5173`.

Para detener: cerrar las ventanas **Stacky Agents Backend** y **Stacky Agents Frontend**.

---

## Servicios y puertos

| Puerto | Servicio | URL |
|--------|----------|-----|
| 5050 | Backend Flask (API REST) | http://localhost:5050/api/health |
| 5173 | Frontend React (dashboard) | http://localhost:5173 |
| 5051 | Bridge VS Code / Copilot | http://localhost:5051 (interno) |
| 8888 | StackyBrain (chat Ollama) | http://localhost:8888/chat.html |

---

## Módulos opcionales

### StackyBrain (chat con LLM local)

Requiere [Ollama](https://ollama.com) instalado. Lanzar con:

```
StackyBrain\iniciar_chat.bat
```

El bat detecta Ollama en `%LOCALAPPDATA%\Programs\Ollama\` o en el PATH si se instaló diferente.

### Integración VS Code / Copilot

Requiere VS Code con la extensión Stacky Agents instalada (`.vsix` en `Stacky Agents\vscode_extension\`). El instalador la instala automáticamente si VS Code está disponible.

Para instalar la extensión manualmente:

```powershell
code --install-extension "Stacky Agents\vscode_extension\stacky-agents-X.X.X.vsix" --force
```

---

## Solución de problemas

### winget no está disponible

Instalar las herramientas manualmente antes de correr `INSTALL.ps1`:

- Python 3.11+: https://www.python.org/downloads/ (marcar "Add to PATH")
- Node.js 18 LTS: https://nodejs.org/
- Git: https://git-scm.com/
- gh CLI: https://cli.github.com/

### Python instalado pero no reconocido después del winget

Cerrar y reabrir PowerShell para refrescar el PATH, luego volver a ejecutar `INSTALL.ps1`.

### Error al crear virtualenv

Verificar que el Python en PATH sea 3.11+:

```powershell
python --version
```

Si hay múltiples versiones, usar el launcher de Python:

```powershell
py -3.11 -m venv "Stacky Agents\backend\.venv"
```

### `npm install` falla en el frontend

Ejecutar manualmente desde la carpeta del frontend:

```powershell
cd "Stacky Agents\frontend"
npm install
```

### El backend no arranca (puerto 5050 ocupado)

Ver qué proceso ocupa el puerto:

```powershell
netstat -ano | findstr ":5050"
```

Cambiar el puerto en `.env`:

```env
PORT=5055
ALLOWED_ORIGINS=http://localhost:5173
```

Y actualizar `Stacky Agents\frontend\.env` (o `vite.config.ts`) con el nuevo puerto del backend.

### `.env` con credenciales incorrectas

Editar directamente `Stacky Agents\backend\.env`. El archivo no se sobreescribe al volver a ejecutar `INSTALL.ps1`.

---

## Estructura del directorio tras la instalación

```
Stacky/
├── INSTALL.ps1                          <- instalador
├── INSTALLER.md                         <- este archivo
├── START.bat                            <- lanzador diario
│
├── Stacky Agents/
│   ├── backend/
│   │   ├── .venv/                       <- virtualenv Python (creado por el instalador)
│   │   ├── data/
│   │   │   └── stacky_agents.db         <- base de datos SQLite (creada en primer arranque)
│   │   ├── .env                         <- credenciales (creado por el instalador, no en git)
│   │   ├── .env.example                 <- template de configuración
│   │   ├── requirements.txt
│   │   └── app.py
│   ├── frontend/
│   │   ├── node_modules/                <- deps npm (creado por el instalador)
│   │   ├── src/
│   │   └── package.json
│   ├── vscode_extension/
│   │   └── stacky-agents-X.X.X.vsix
│   └── start_dashboard.bat
│
├── Stacky pipeline/
│   └── requirements.txt
│
├── Stacky tools/
│   └── QA UAT Agent/
│       └── requirements.txt
│
└── StackyBrain/
    └── iniciar_chat.bat
```
