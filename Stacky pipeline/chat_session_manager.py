"""
chat_session_manager.py — Aislamiento de chats para ejecución concurrente de tickets.

PROBLEMA QUE RESUELVE:
    Antes, todos los tickets compartían UN solo VS Code + UN solo chat de Copilot.
    Si ticket A estaba en QA y ticket B arrancaba PM, el prompt de QA se podía
    pegar en el chat equivocado.

SOLUCIÓN:
    Cada ticket activo se asigna a una "sesión" con su propio puerto bridge.
    Cada sesión es un VS Code abierto con la extensión bridge escuchando en un
    puerto distinto (5051, 5052, 5053...).

    - Un ticket mantiene su sesión durante todo su ciclo PM→DEV→QA.
    - El lock por sesión garantiza que EN ESA SESIÓN solo corre un prompt a la vez.
    - Si todas las sesiones están ocupadas, el ticket espera en cola.
    - Al completarse un ticket, la sesión se libera para otro.

USO:
    from chat_session_manager import get_session_manager

    mgr = get_session_manager(config)

    # Adquirir sesión para un ticket (bloquea hasta que haya una libre)
    session = mgr.acquire(ticket_id="12345")

    # Invocar el agente en la sesión aislada
    session.invoke(prompt, agent_name="DevStack1", ...)

    # Liberar cuando el pipeline del ticket termina
    mgr.release(ticket_id="12345")
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.chat_sessions")

STATE_FILE = Path(__file__).parent / "state" / "chat_sessions.json"
PROFILES_DIR = Path(__file__).parent / "state" / "vscode_profiles"
DEFAULT_BASE_PORT = 5051
DEFAULT_MAX_SESSIONS = 3


# ─────────────────────────────────────────────────────────────────────────────
# ChatSession — una instancia aislada de VS Code + bridge
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChatSession:
    """
    Representa una sesión aislada: un VS Code con bridge en un puerto específico.

    Atributos:
        session_id:  Identificador único (0, 1, 2, ...).
        port:        Puerto HTTP del bridge de esta instancia.
        ticket_id:   Ticket actualmente asignado (None = libre).
        lock:        Lock que serializa invocaciones dentro de esta sesión.
        last_used:   Timestamp del último uso.
        stage:       Etapa actual del ticket (pm, dev, tester).
    """
    session_id: int
    port: int
    ticket_id: Optional[str] = None
    stage: Optional[str] = None
    last_used: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def bridge_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def is_free(self) -> bool:
        return self.ticket_id is None

    @property
    def is_busy(self) -> bool:
        return self.ticket_id is not None

    def health_check(self) -> bool:
        """Verifica si el bridge de esta sesión está activo."""
        try:
            req = urllib.request.Request(f"{self.bridge_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return bool(body.get("ok"))
        except Exception:
            return False

    def invoke(self, prompt: str, agent_name: str = None,
               workspace_root: str = None,
               new_conversation: bool = False) -> bool:
        """
        Envía un prompt al bridge de ESTA sesión, con lock de exclusión mutua.
        Garantiza que dos prompts no se crucen en el mismo chat.
        """
        with self._lock:
            self.last_used = time.time()

            # Asegurar que VS Code tenga el workspace correcto
            if workspace_root:
                self._ensure_workspace(workspace_root)

            # Verificar health
            if not self.health_check():
                logger.warning("[Session %d] Bridge en :%d no responde — "
                               "esperando 5s y reintentando...",
                               self.session_id, self.port)
                time.sleep(5)
                if not self.health_check():
                    logger.error("[Session %d] Bridge :%d no disponible",
                                 self.session_id, self.port)
                    return False

            # Enviar prompt
            return self._send_to_bridge(prompt, agent_name, workspace_root,
                                        new_conversation)

    def _send_to_bridge(self, prompt: str, agent_name: str = None,
                        workspace_root: str = None,
                        new_conversation: bool = False) -> bool:
        """POST al bridge HTTP de esta sesión."""
        try:
            payload = json.dumps({
                "prompt": prompt,
                "agent": agent_name or "",
                "workspace_root": workspace_root or "",
                "new_conversation": bool(new_conversation),
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{self.bridge_url}/invoke",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("ok"):
                    logger.info(
                        "[Session %d|:%d] Prompt enviado — ticket=%s, agent=%s, "
                        "chars=%d",
                        self.session_id, self.port,
                        self.ticket_id, agent_name or "?",
                        body.get("chars", 0),
                    )
                    return True
                else:
                    logger.warning(
                        "[Session %d|:%d] Bridge respondió ok=False: %s",
                        self.session_id, self.port, body.get("error"),
                    )
                    return False
        except Exception as e:
            logger.error("[Session %d|:%d] Error enviando prompt: %s",
                         self.session_id, self.port, e)
            return False

    def _ensure_workspace(self, workspace_root: str) -> bool:
        """
        Abre una instancia AISLADA de VS Code para esta sesión.

        Garantías:
        1) Abre VS Code EN LA CARPETA DEL PROYECTO (workspace_root).
        2) La instancia es EXCLUSIVA de esta sesión — no reutiliza ventanas ajenas.
        3) La extensión bridge escucha en el PUERTO CORRECTO de esta sesión.
        4) El prompt se envía al bridge de ESTA instancia (puerto único).

        Mecanismo:
        - Cada sesión tiene su propio --user-data-dir (perfil aislado).
        - El settings.json del perfil configura el puerto del bridge.
        - --extensions-dir apunta a las extensiones compartidas del VS Code principal.
        - --new-window fuerza una ventana nueva.
        - El bridge health check confirma que está escuchando en el puerto correcto
          ANTES de retornar True.
        """
        # Si el bridge ya responde en este puerto, la instancia ya está corriendo
        if self.health_check():
            logger.debug("[Session %d] Bridge :%d ya activo — no se necesita abrir VS Code",
                         self.session_id, self.port)
            return True

        # ── 1. Preparar perfil aislado ────────────────────────────────────
        profile_dir = PROFILES_DIR / f"session_{self.session_id}"
        user_dir = profile_dir / "User"
        user_dir.mkdir(parents=True, exist_ok=True)

        # Escribir settings.json con el puerto del bridge
        settings_file = user_dir / "settings.json"
        settings = {}
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                settings = {}
        settings["ripley-bridge.port"] = self.port
        settings_file.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # ── 2. Resolver paths de VS Code ──────────────────────────────────
        code_cmd = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs", "Microsoft VS Code", "bin", "code.cmd",
        )
        if not os.path.exists(code_cmd):
            code_cmd = "code"

        # Extensiones del VS Code principal (compartidas por todas las sesiones)
        extensions_dir = Path(os.environ.get("USERPROFILE", "")) / ".vscode" / "extensions"
        if not extensions_dir.exists():
            # Fallback: buscar en LOCALAPPDATA
            alt = (Path(os.environ.get("LOCALAPPDATA", ""))
                   / "Programs" / "Microsoft VS Code" / "resources" / "app" / "extensions")
            if alt.exists():
                extensions_dir = alt

        # ── 3. Lanzar VS Code con aislamiento completo ───────────────────
        cmd_parts = [
            f'"{code_cmd}"',
            "--new-window",                              # NUNCA reusar ventana ajena
            f'--user-data-dir="{profile_dir}"',          # Perfil aislado por sesión
            f'--extensions-dir="{extensions_dir}"',      # Extensiones compartidas
            f'"{workspace_root}"',                       # CARPETA DEL PROYECTO
        ]
        full_cmd = " ".join(cmd_parts)

        try:
            env = os.environ.copy()
            env["RIPLEY_BRIDGE_PORT"] = str(self.port)  # Respaldo via env var

            logger.info(
                "[Session %d] Abriendo VS Code — workspace=%s, puerto=%d, "
                "profile=%s",
                self.session_id, workspace_root, self.port, profile_dir,
            )

            subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except Exception as e:
            logger.error("[Session %d] Error lanzando VS Code: %s",
                         self.session_id, e)
            return False

        # ── 4. Esperar a que el bridge responda en el puerto correcto ─────
        # Esto CONFIRMA que la instancia correcta arrancó y está lista.
        deadline = time.time() + 30  # 30s max — VS Code puede tardar en cargar
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            if self.health_check():
                logger.info(
                    "[Session %d] Bridge :%d activo (intento %d, %.1fs)",
                    self.session_id, self.port, attempt,
                    time.time() - (deadline - 30),
                )
                return True
            time.sleep(2)

        logger.error(
            "[Session %d] Bridge :%d no respondió en 30s — VS Code no arrancó "
            "correctamente o la extensión bridge no está instalada",
            self.session_id, self.port,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ChatSessionManager — pool de sesiones con asignación por ticket
# ─────────────────────────────────────────────────────────────────────────────

class ChatSessionManager:
    """
    Gestiona un pool de sesiones de chat aisladas.

    Cada sesión = un puerto bridge distinto = un VS Code distinto.
    Un ticket se asigna a una sesión y la mantiene hasta que se libera.

    Configuración en config.json:
        "concurrency": {
            "max_sessions": 3,
            "base_port": 5051,
            "session_timeout_minutes": 120
        }
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = (config or {}).get("concurrency", {})
        self._max_sessions = cfg.get("max_sessions", DEFAULT_MAX_SESSIONS)
        self._base_port = cfg.get("base_port", DEFAULT_BASE_PORT)
        self._timeout_min = cfg.get("session_timeout_minutes", 120)

        # Pool de sesiones
        self._sessions: list[ChatSession] = [
            ChatSession(session_id=i, port=self._base_port + i)
            for i in range(self._max_sessions)
        ]

        # Mapa ticket_id → session_id para lookup rápido
        self._ticket_map: dict[str, int] = {}

        # Condition para esperar sesiones libres
        self._condition = threading.Condition()

        # Cola de tickets esperando sesión (FIFO)
        self._wait_queue: list[str] = []

        # Cargar estado persistido
        self._load_state()

        logger.info(
            "[SessionMgr] Inicializado con %d sesiones (puertos %d-%d)",
            self._max_sessions, self._base_port,
            self._base_port + self._max_sessions - 1,
        )

    @property
    def sessions(self) -> list[ChatSession]:
        return list(self._sessions)

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._sessions if s.is_busy)

    @property
    def free_count(self) -> int:
        return sum(1 for s in self._sessions if s.is_free)

    def status(self) -> dict:
        """Estado actual del pool para dashboard/logging."""
        return {
            "max_sessions": self._max_sessions,
            "active": self.active_count,
            "free": self.free_count,
            "sessions": [
                {
                    "id": s.session_id,
                    "port": s.port,
                    "ticket": s.ticket_id,
                    "stage": s.stage,
                    "healthy": s.health_check(),
                    "last_used": s.last_used,
                }
                for s in self._sessions
            ],
            "waiting": list(self._wait_queue),
        }

    # ── Adquisición / Liberación ──────────────────────────────────────────

    def acquire(self, ticket_id: str, stage: str = "",
                timeout: float = 600) -> Optional[ChatSession]:
        """
        Adquiere una sesión para un ticket.

        - Si el ticket ya tiene sesión asignada, la retorna directamente.
        - Si hay sesiones libres, asigna una.
        - Si todas están ocupadas, espera hasta que se libere una (max timeout).

        Args:
            ticket_id: ID del ticket.
            stage:     Etapa actual (pm, dev, tester) — informativo.
            timeout:   Segundos máximos de espera. Default 10 min.

        Returns:
            ChatSession asignada, o None si timeout.
        """
        with self._condition:
            # 1. ¿El ticket ya tiene sesión?
            if ticket_id in self._ticket_map:
                session = self._sessions[self._ticket_map[ticket_id]]
                session.stage = stage
                session.last_used = time.time()
                logger.info(
                    "[SessionMgr] Ticket #%s reutiliza sesión %d (:%d) → %s",
                    ticket_id, session.session_id, session.port, stage,
                )
                return session

            # Limpiar sesiones expiradas antes de buscar libres
            self._cleanup_expired()

            # 2. ¿Hay sesión libre?
            session = self._assign_free_session(ticket_id, stage)
            if session:
                return session

            # 3. Todas ocupadas → encolar y esperar
            if ticket_id not in self._wait_queue:
                self._wait_queue.append(ticket_id)
            logger.info(
                "[SessionMgr] Ticket #%s en cola (posición %d de %d) "
                "— esperando sesión libre...",
                ticket_id,
                self._wait_queue.index(ticket_id) + 1,
                len(self._wait_queue),
            )

            deadline = time.time() + timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    # Timeout
                    if ticket_id in self._wait_queue:
                        self._wait_queue.remove(ticket_id)
                    logger.warning(
                        "[SessionMgr] Timeout esperando sesión para ticket #%s",
                        ticket_id,
                    )
                    return None

                self._condition.wait(timeout=min(remaining, 10))

                # ¿Se liberó una sesión?
                self._cleanup_expired()
                # Respetar el orden de la cola FIFO
                if (self._wait_queue and
                        self._wait_queue[0] == ticket_id):
                    session = self._assign_free_session(ticket_id, stage)
                    if session:
                        self._wait_queue.remove(ticket_id)
                        return session

    def release(self, ticket_id: str) -> bool:
        """
        Libera la sesión asignada a un ticket.

        Args:
            ticket_id: ID del ticket a liberar.

        Returns:
            True si se liberó, False si el ticket no tenía sesión.
        """
        with self._condition:
            if ticket_id not in self._ticket_map:
                return False

            session_id = self._ticket_map.pop(ticket_id)
            session = self._sessions[session_id]
            old_stage = session.stage

            session.ticket_id = None
            session.stage = None

            logger.info(
                "[SessionMgr] Sesión %d (:%d) liberada — ticket #%s "
                "terminó en stage=%s",
                session_id, session.port, ticket_id, old_stage,
            )

            self._save_state()

            # Notificar a threads en espera que hay una sesión libre
            self._condition.notify_all()
            return True

    def get_session(self, ticket_id: str) -> Optional[ChatSession]:
        """Obtiene la sesión de un ticket sin adquirirla."""
        with self._condition:
            if ticket_id in self._ticket_map:
                return self._sessions[self._ticket_map[ticket_id]]
            return None

    def get_queue_position(self, ticket_id: str) -> int:
        """Posición en cola de espera (1-based). 0 = no está en cola."""
        with self._condition:
            if ticket_id in self._wait_queue:
                return self._wait_queue.index(ticket_id) + 1
            return 0

    # ── Internos ──────────────────────────────────────────────────────────

    def _assign_free_session(self, ticket_id: str,
                             stage: str) -> Optional[ChatSession]:
        """Busca una sesión libre, la asigna al ticket y persiste."""
        for session in self._sessions:
            if session.is_free:
                session.ticket_id = ticket_id
                session.stage = stage
                session.last_used = time.time()
                self._ticket_map[ticket_id] = session.session_id

                self._save_state()

                logger.info(
                    "[SessionMgr] Ticket #%s → sesión %d (:%d) para %s",
                    ticket_id, session.session_id, session.port, stage,
                )
                return session
        return None

    def _cleanup_expired(self):
        """Libera sesiones que superaron el timeout (tickets olvidados)."""
        now = time.time()
        threshold = self._timeout_min * 60

        for session in self._sessions:
            if session.is_busy and session.last_used > 0:
                elapsed = now - session.last_used
                if elapsed > threshold:
                    old_ticket = session.ticket_id
                    logger.warning(
                        "[SessionMgr] Sesión %d expirada (ticket #%s, "
                        "%.0f min sin uso) — liberando",
                        session.session_id, old_ticket,
                        elapsed / 60,
                    )
                    if old_ticket and old_ticket in self._ticket_map:
                        del self._ticket_map[old_ticket]
                    session.ticket_id = None
                    session.stage = None

    def _save_state(self):
        """Persiste el estado del pool para recovery post-crash."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "ticket_map": dict(self._ticket_map),
                "sessions": [
                    {
                        "id": s.session_id,
                        "port": s.port,
                        "ticket_id": s.ticket_id,
                        "stage": s.stage,
                        "last_used": s.last_used,
                    }
                    for s in self._sessions
                ],
            }
            STATE_FILE.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[SessionMgr] Error guardando estado: %s", e)

    def _load_state(self):
        """Restaura estado del pool desde disco."""
        if not STATE_FILE.exists():
            return
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            ticket_map = state.get("ticket_map", {})
            sessions_data = state.get("sessions", [])

            for sd in sessions_data:
                sid = sd.get("id", -1)
                if 0 <= sid < len(self._sessions):
                    s = self._sessions[sid]
                    s.ticket_id = sd.get("ticket_id")
                    s.stage = sd.get("stage")
                    s.last_used = sd.get("last_used", 0.0)

            # Reconstruir ticket_map desde sesiones (más confiable)
            self._ticket_map = {}
            for s in self._sessions:
                if s.ticket_id:
                    self._ticket_map[s.ticket_id] = s.session_id

            restored = sum(1 for s in self._sessions if s.is_busy)
            if restored:
                logger.info(
                    "[SessionMgr] Estado restaurado: %d sesiones activas",
                    restored,
                )
        except Exception as e:
            logger.warning("[SessionMgr] Error cargando estado: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_instance: Optional[ChatSessionManager] = None
_instance_lock = threading.Lock()


def get_session_manager(config: Optional[dict] = None) -> ChatSessionManager:
    """
    Retorna el singleton del ChatSessionManager.

    En la primera llamada, se crea con la config provista.
    Las siguientes retornan la misma instancia.
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ChatSessionManager(config)
    return _instance
