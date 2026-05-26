# Stacky Agents - Deployment

Esta carpeta contiene el generador de release distribuible de Stacky Agents.

## Generar una entrega nueva

```powershell
powershell -ExecutionPolicy Bypass -File ".\Stacky Agents\deployment\build_release.ps1"
```

El script:

- compila `frontend/dist`
- congela el backend con PyInstaller en `backend/stacky-backend.exe`
- sirve el frontend desde Flask en el mismo puerto
- incluye el ultimo `.vsix` disponible
- crea una carpeta en `deployment/out/`
- genera tambien un `.zip` listo para enviar
- si Inno Setup esta instalado, genera un `StackyAgents-<version>-Setup.exe`

## Salida esperada

Se crea algo como:

```text
Stacky Agents/deployment/out/stacky-agents-<version>-YYYYMMDD-HHMMSS/
Stacky Agents/deployment/out/stacky-agents-<version>-YYYYMMDD-HHMMSS.zip
Stacky Agents/deployment/out/StackyAgents-<version>-Setup.exe
```

## Entrega al otro desarrollador

1. Enviar el `.exe` del instalador o el `.zip` generado.
2. Si se usa `.zip`, ejecutar `INSTALL.ps1` una vez.
3. Ejecutar `START.bat`.

## Flujo recomendado local

Desde `Stacky Agents\`:

```bat
Instalador Dependencias.bat
PrepararPublicacion.bat
```

`PrepararPublicacion.bat` genera `DeployStackyAgents\`, respalda el deploy
anterior en `DeployStackyAgents\backups\`, incrementa version desde `1.0.0`
y crea `DeployStackyAgents-<version>.zip`.
