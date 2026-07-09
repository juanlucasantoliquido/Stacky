"""services/remote_exec.py — Plan 105. ÚNICO módulo que ejecuta comandos remotos.

Riel §3.1: la credencial viaja SOLO por env del proceso hijo powershell.exe.
Riel §3.3: run_remote SIEMPRE audita (éxito o error) antes de devolver.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_AUDIT_LOCK = threading.Lock()
_TIMEOUT_S_DEFAULT = 120
_TIMEOUT_S_MAX = 600
_OUTPUT_CAP = 200_000  # chars; truncar stdout/stderr más allá (marca "...[truncated]")

# §3.4 — validador conservador. Allowlist de PRIMER token (verbo/alias de lectura):
_READ_VERBS = re.compile(
    r"^\s*(Get-|Test-|Select-|Measure-|Resolve-|Compare-|Find-|Show-|Trace-)[A-Za-z]+"
    r"|^\s*(dir|ls|type|cat|gci|gc|echo|hostname|whoami|tasklist)\b",
    re.IGNORECASE,
)
# Blocklist de tokens mutantes/peligrosos en CUALQUIER parte del comando.
# C3 (v2): sumados vectores de EJECUCIÓN ARBITRARIA y descarga/exfil que un agente
# podría intentar creyéndolos "de lectura" (el riesgo real es el AGENTE, no un humano
# adversario — mono-operador). El operador de veras destructivo usa el modo escritura.
_MUTANT_TOKENS = re.compile(
    r"(Remove-|Set-|New-|Stop-|Start-|Restart-|Clear-|Move-|Rename-|Copy-|Add-|Install-|"
    r"Uninstall-|Disable-|Enable-|Invoke-Expression|iex\b|Invoke-Command|Invoke-WebRequest|"
    r"Invoke-RestMethod|\biwr\b|\birm\b|\bcurl\b|\bwget\b|Start-Process|Add-Type|"
    r"\.Invoke\b|\[scriptblock\]|Out-File|Set-Content|"
    r"Add-Content|Format-Volume|Stop-Computer|Restart-Computer|del\b|rd\b|rmdir\b|"
    r"erase\b|mklink\b|reg\s+(add|delete)|schtasks|sc\s+(config|delete|stop|start)|"
    r"&|\$\(|`|>>|(?<![0-9a-zA-Z])>(?![0-9a-zA-Z=]))",
    re.IGNORECASE,
)


def is_read_only_command(command: str) -> bool:
    """True solo si el comando ARRANCA con verbo de lectura y NO contiene tokens
    mutantes. Cada segmento de pipeline (split por '|') y cada statement (split por
    ';') debe cumplir la allowlist o ser un cmdlet de formato/filtro inocuo."""
    if not command or not command.strip():
        return False
    # C3 (v2): en read_only NUNCA se permiten bloques de script { ... }: son el vector
    # clásico de ejecución arbitraria dentro de un pipeline "de lectura"
    # (p.ej. `Get-Content x | %{ & $_ }`). Ante llaves → RECHAZA.
    if "{" in command or "}" in command:
        return False
    if _MUTANT_TOKENS.search(command):
        return False
    _INNOCUOUS = re.compile(
        r"^\s*(Where-Object|ForEach-Object|Sort-Object|Select-Object|Select-String|"
        r"Format-Table|Format-List|Out-String|ConvertTo-Json|Group-Object|"
        r"Measure-Object|\?|%|ft|fl|sort|select)\b",
        re.IGNORECASE,
    )
    for stmt in command.split(";"):
        if not stmt.strip():
            continue
        segments = stmt.split("|")
        if not _READ_VERBS.search(segments[0]):
            return False
        for seg in segments[1:]:
            if not (_READ_VERBS.search(seg) or _INNOCUOUS.search(seg)):
                return False
    return True


def _audit_dir() -> Path:
    from runtime_paths import data_dir
    p = Path(data_dir()) / "devops_remote_audit"
    p.mkdir(parents=True, exist_ok=True)
    return p


def append_audit(alias: str, entry: dict) -> None:
    """Append-only JSONL por alias. entry NO debe contener secretos (el caller
    garantiza; este módulo además hace un assert defensivo)."""
    from services.server_registry import validate_alias
    if not validate_alias(alias):
        raise ValueError(f"alias inválido: {alias!r}")
    # Assert defensivo: sin secretos
    assert "password" not in str(entry).lower()
    assert "SR_PASS" not in str(entry)

    entry = dict(entry)
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(entry, ensure_ascii=False)
    with _AUDIT_LOCK:
        with open(_audit_dir() / f"{alias}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def read_audit(alias: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Lee el JSONL del alias, MÁS RECIENTES PRIMERO. Tolerante a líneas corruptas
    (las salta). Devuelve [] si el archivo no existe."""
    from services.server_registry import validate_alias
    if not validate_alias(alias):
        raise ValueError(f"alias inválido: {alias!r}")
    path = _audit_dir() / f"{alias}.jsonl"
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    rows.reverse()
    return rows[offset : offset + limit]


_WINRM_PASSTHROUGH_KINDS = frozenset(
    {"windows_only", "keyring_unavailable", "server_not_found", "server_missing_host", "test_failed"}
)


def classify_winrm_failure(detail: str) -> str:
    """Plan 108 F1b (C9 v2) — PURA. Clasifica el `detail` crudo de check_winrm en
    un tipo accionable. Passthrough exacto para los detail ya tipificados por
    check_winrm; matching case-insensitive por substring para el resto (stderr
    crudo de Windows, incluye variantes en inglés y español)."""
    if detail in _WINRM_PASSTHROUGH_KINDS:
        return detail
    d = (detail or "").lower()
    if any(tok in d for tok in (
        "trustedhosts", "negotiate", "kerberos", "authentication mechanism",
        "mecanismo de autenticación",
    )):
        return "trust_config"
    if any(tok in d for tok in (
        "access is denied", "acceso denegado", "unauthorized", "no autorizado",
    )):
        return "auth_denied"
    if any(tok in d for tok in (
        "timed out", "timeout", "tiempo de espera", "refused", "rechazó",
        "cannot connect", "no puede conectar", "unreachable",
    )):
        return "unreachable_or_disabled"
    return "winrm_error"


def build_winrm_remediation(host: str, kind: str) -> list[dict]:
    """Plan 108 F1b (C9 v2) — PURA. Pasos copy-paste para que el OPERADOR
    remedie WinRM. Stacky NUNCA ejecuta estos comandos (HITL innegociable).
    PROHIBIDO interpolar credenciales o el alias del keyring: solo `host`."""
    if kind in ("windows_only", "keyring_unavailable", "server_not_found", "server_missing_host"):
        return []
    steps: list[dict] = [{
        "where": "servidor",
        "label": (
            "Habilitar WinRM (correr en PowerShell como admin EN el servidor; si la red "
            "es de perfil Público usar la variante -SkipNetworkProfileCheck)"
        ),
        "command": "Enable-PSRemoting -Force",
    }]
    if kind == "unreachable_or_disabled":
        steps.append({
            "where": "cliente",
            "label": "Verificar que el puerto 5985 del servidor sea alcanzable desde esta máquina",
            "command": f"Test-NetConnection {host} -Port 5985",
        })
    elif kind == "trust_config":
        steps.append({
            "where": "cliente",
            "label": (
                "Sin dominio compartido (workgroup): agregar el host a TrustedHosts de "
                "ESTA máquina (o configurar listener HTTPS 5986)"
            ),
            "command": (
                f"Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '{host}' "
                "-Concatenate -Force"
            ),
        })
    elif kind == "auth_denied":
        steps.append({
            "where": "servidor",
            "label": (
                "La credencial del alias debe ser Administrador del servidor o miembro "
                "del grupo local 'Remote Management Users'"
            ),
            "command": None,
        })
    elif kind == "winrm_error":
        steps.append({
            "where": "cliente",
            "label": "Detalle crudo del error abajo; probar Test-WSMan a mano",
            "command": f"Test-WSMan -ComputerName {host}",
        })
    return steps


def check_winrm(alias: str) -> dict:
    """Test-WSMan contra el host del alias. Devuelve {"ok": bool, "detail": str}.
    NO usa credencial (Test-WSMan sin -Credential valida el listener).

    Plan 108 F1b (C9 v2): cuando ok=False agrega "kind" (clasificación
    tipificada, classify_winrm_failure) y "remediation" (pasos copy-paste,
    build_winrm_remediation; [] si no aplica). Backward-compatible: "ok" y
    "detail" NUNCA cambian; con ok=True no se agregan keys nuevas."""
    # win32-only; en otros SO {"ok": False, "detail": "windows_only"}
    if sys.platform != "win32":
        return {"ok": False, "detail": "windows_only", "kind": "windows_only", "remediation": []}

    from services.server_registry import get_server, keyring_available
    if not keyring_available():
        return {"ok": False, "detail": "keyring_unavailable", "kind": "keyring_unavailable", "remediation": []}

    try:
        server = get_server(alias)
    except Exception:
        return {"ok": False, "detail": "server_not_found", "kind": "server_not_found", "remediation": []}

    host = server.get("host")
    if not host:
        return {"ok": False, "detail": "server_missing_host", "kind": "server_missing_host", "remediation": []}

    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-Command", f"Test-WSMan -ComputerName {host}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return {"ok": True, "detail": "ok"}
        else:
            detail = result.stderr or "winrm_error"
            kind = classify_winrm_failure(detail)
            return {"ok": False, "detail": detail, "kind": kind,
                    "remediation": build_winrm_remediation(host, kind)}
    except subprocess.TimeoutExpired:
        kind = classify_winrm_failure("timeout")
        return {"ok": False, "detail": "timeout", "kind": kind,
                "remediation": build_winrm_remediation(host, kind)}
    except Exception:
        kind = classify_winrm_failure("test_failed")
        return {"ok": False, "detail": "test_failed", "kind": kind,
                "remediation": build_winrm_remediation(host, kind)}


def run_remote(
    alias: str,
    command: str,
    *,
    mode: str,                 # "read_only" | "write"
    conversation_id: int | None = None,
    user: str = "",
    timeout_s: int = _TIMEOUT_S_DEFAULT,
) -> dict:
    """Ejecuta `command` en el servidor `alias` vía Invoke-Command (WinRM).

    Retorna SIEMPRE un dict: {"ok": bool, "error": str|None, "stdout": str,
    "stderr": str, "exit_code": int|None, "duration_ms": int}.
    Errores tipificados en "error": remote_exec_disabled | server_not_found |
    keyring_unavailable | no_password | command_not_read_only |
    remote_exec_windows_only | winrm_error | timeout.
    SIEMPRE llama a append_audit() antes de retornar (riel §3.3), con:
      {kind:"exec", command, mode, ok, error, exit_code, duration_ms,
       stdout_sha256, stdout_bytes, conversation_id, user}
    — NUNCA el stdout completo ni la credencial en la auditoría.
    """
    import config as _config
    from services.server_registry import get_server, get_credential, keyring_available

    start = time.time()
    error_key = None
    exit_code = None
    stdout_val = ""
    stderr_val = ""

    # 1) guards: flag ON, sys.platform == "win32", mode válido, timeout_s clamp
    if not getattr(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
        error_key = "remote_exec_disabled"
    elif sys.platform != "win32":
        error_key = "remote_exec_windows_only"
    elif mode not in ("read_only", "write"):
        error_key = "invalid_mode"
    else:
        timeout_s = min(max(timeout_s, 1), _TIMEOUT_S_MAX)

    # 2) validación read_only
    if error_key is None and mode == "read_only" and not is_read_only_command(command):
        error_key = "command_not_read_only"

    # 3) resolver server y credencial
    if error_key is None:
        if not keyring_available():
            error_key = "keyring_unavailable"
        else:
            try:
                server = get_server(alias)
            except Exception:
                error_key = "server_not_found"
            else:
                try:
                    username, password, host = get_credential(alias)
                    if not password:
                        error_key = "no_password"
                except Exception:
                    error_key = "server_not_found"

    # 4) ejecución remota (sino hay error)
    if error_key is None:
        ps1 = Path(__file__).parent / "remote_exec_invoke.ps1"
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                env={**_config.os.environ,
                     "SR_HOST": host,
                     "SR_USER": username,
                     "SR_PASS": password,
                     "SR_CMD": command,
                     "SR_TIMEOUT": str(timeout_s)},
                capture_output=True,
                text=True,
                timeout=timeout_s + 15,
            )
            stdout_val = result.stdout or ""
            stderr_val = result.stderr or ""
            exit_code = result.returncode
            if exit_code != 0:
                error_key = "winrm_error"
        except subprocess.TimeoutExpired:
            error_key = "timeout"
        except Exception:
            error_key = "winrm_error"

    # 5) truncar output
    if len(stdout_val) > _OUTPUT_CAP:
        stdout_val = stdout_val[:_OUTPUT_CAP] + "...[truncated]"
    if len(stderr_val) > _OUTPUT_CAP:
        stderr_val = stderr_val[:_OUTPUT_CAP] + "...[truncated]"

    duration_ms = int((time.time() - start) * 1000)

    # 6) auditoría SIEMPRE
    append_audit(alias, {
        "kind": "exec",
        "command": command,
        "mode": mode,
        "ok": error_key is None,
        "error": error_key,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_sha256": hashlib.sha256(stdout_val.encode()).hexdigest() if stdout_val else "",
        "stdout_bytes": len(stdout_val),
        "conversation_id": conversation_id,
        "user": user,
    })

    return {
        "ok": error_key is None,
        "error": error_key,
        "stdout": stdout_val,
        "stderr": stderr_val,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }
