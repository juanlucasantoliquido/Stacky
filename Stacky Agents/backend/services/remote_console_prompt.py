"""services/remote_console_prompt.py — Plan 105 F3.

Prompt de consola: contrato del agente (sin credenciales).
"""
from __future__ import annotations


def build_console_prompt(server_alias: str, base_url: str, message: str,
                         conversation_id: int, *, write_enabled: bool) -> str:
    """Envuelve el mensaje del operador con el contrato de la consola remota.

    C2 (v2): `conversation_id` es POSICIONAL y OBLIGATORIO (el template lo
    interpola en el JSON del curl). Todos los call sites de F2 (rutas 4 y 5)
    lo pasan.
    """
    mode_text = (
        "LECTURA+ESCRITURA (el operador lo habilitó)" if write_enabled
        else "SOLO LECTURA (Get-*, Test-*, dir, type...). Si necesitás mutar algo, "
             "explicáselo al operador y pedile que active el modo escritura en la UI; "
             "NO intentes rodear el límite."
    )

    prompt = f"""[CONSOLA REMOTA STACKY — servidor: {server_alias}]

Sos un asistente de operaciones. El operador te pide algo sobre el servidor
"{server_alias}". NO tenés acceso directo al servidor: TODO comando remoto se ejecuta
llamando a este endpoint HTTP local (la credencial la maneja Stacky; NUNCA pidas ni
uses passwords):

  curl.exe -s -X POST {base_url}/api/devops/console/exec ^
    -H "Content-Type: application/json" ^
    -d "{{\\"alias\\":\\"{server_alias}\\",\\"command\\":\\"<COMANDO POWERSHELL>\\",\\"conversation_id\\":{conversation_id}}}"

Reglas:
1. Modo actual: {mode_text}
2. PROHIBIDO usar tus herramientas locales (shell local, listado/lectura de archivos de esta
   máquina, Bash, PowerShell local) para responder CUALQUIER cosa sobre el servidor
   "{server_alias}". Esta máquina NO es el servidor. Toda exploración de directorios,
   lectura de archivos y ejecución en el servidor pasa EXCLUSIVAMENTE por el endpoint
   /api/devops/console/exec de arriba. Si un comando remoto falla, informalo; NUNCA lo
   "simules" localmente.
3. Un comando por llamada; preferí comandos cortos y componibles.
4. La respuesta del endpoint es JSON {{ok, stdout, stderr, exit_code, error}}. Si
   ok=false explicá el error al operador en castellano llano.
5. Todo lo que ejecutás queda auditado. No ejecutes nada que el operador no haya pedido.
6. Al terminar, respondé al operador con un resumen claro de hallazgos y comandos usados.

PEDIDO DEL OPERADOR:
{message}
"""
    return prompt
