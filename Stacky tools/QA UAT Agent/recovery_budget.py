"""recovery_budget.py — Plan 262 F5. Presupuesto anti-bucle: techo, nunca piso.

El operador pidio explicitamente "evitar ciclos infinitos de recuperacion". Sin
esto, SERVICE_DOWN -> arrancar -> probar -> SERVICE_DOWN -> arrancar... consume la
ventana entera de la corrida.

INV-7: el presupuesto NO PUEDE AUTORIZAR mas intentos que las cotas ya existentes
(_MAX_REAUTH_PER_STEP=1, MAX_REPLAN_ROUNDS=3, QA_UAT_MAX_BROWSER_LAUNCHES). Ante
conflicto gana EL MINIMO.

EL PRESUPUESTO NO SE REINICIA NUNCA dentro de la corrida: ni por caso nuevo, ni por
replan, ni por reinicio del navegador. Un contador que se resetea no es un
presupuesto: es un bucle con pasos extra.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

_CASE_POR_DEFECTO = "<run>"


def _norm_case(case_id) -> str:
    """case_id vacio o None -> '<run>'. Nunca se crea una clave None en el dict."""
    if case_id is None:
        return _CASE_POR_DEFECTO
    texto = str(case_id).strip()
    return texto or _CASE_POR_DEFECTO


@dataclass
class RecoveryBudget:
    max_per_run: int
    max_per_case: int
    max_service_starts: int          # derivado; ver build_budget
    _used_run: int = 0
    _used_by_case: dict = field(default_factory=dict)
    _service_starts: int = 0
    _ledger: list = field(default_factory=list)   # historial completo, para el reporte

    def attempts_for(self, case_id) -> int:
        return int(self._used_by_case.get(_norm_case(case_id), 0))

    def can_recover(self, case_id: str, recovery_class: str) -> tuple[bool, str]:
        """(autorizado, motivo). El motivo viaja al reporte cuando es False."""
        try:
            from recovery_config import hot_recovery_enabled
            if not hot_recovery_enabled():
                return False, "hot_recovery_off"
        except Exception:                          # noqa: BLE001
            return False, "hot_recovery_off"

        # v2/C14 — API PUBLICA de F3. Indexar _CLASS_TO_TAXONOMY directamente daria
        # KeyError ante una clase desconocida, y un KeyError aca termina rotulado
        # PIPELINE_CRASH: el bug que este plan cierra, reintroducido por la capa
        # que lo cierra.
        try:
            from recovery_classifier import is_recoverable
            if not is_recoverable(recovery_class):
                return False, "clase_no_recuperable"
        except Exception:                          # noqa: BLE001
            return False, "clase_no_recuperable"

        if self._used_run >= self.max_per_run:
            return False, "presupuesto_de_run_agotado"
        if self.attempts_for(case_id) >= self.max_per_case:
            return False, "presupuesto_del_caso_agotado"
        if recovery_class == "SERVICE_DOWN" and self._service_starts >= self.max_service_starts:
            return False, "arranques_de_servicio_agotados"
        return True, ""

    def consume(self, case_id: str, recovery_class: str, detail: str = "") -> None:
        """Gasta un intento. Una clase NO recuperable no incrementa nada pero SI
        se registra: el reporte necesita saber que paso."""
        caso = _norm_case(case_id)
        recuperable = False
        try:
            from recovery_classifier import is_recoverable
            recuperable = is_recoverable(recovery_class)
        except Exception:                          # noqa: BLE001
            recuperable = False

        if recuperable:
            self._used_run += 1
            self._used_by_case[caso] = self.attempts_for(caso) + 1
            if recovery_class == "SERVICE_DOWN":
                self._service_starts += 1

        self._ledger.append({
            "ts": round(time.time(), 3),
            "case_id": caso,
            "recovery_class": recovery_class,
            "consumed": bool(recuperable),
            "detail": detail,
            "used_run": self._used_run,
            "used_case": self.attempts_for(caso),
        })

    def exhausted_reason(self, case_id: str) -> str:
        """'' si no esta agotado."""
        if self._used_run >= self.max_per_run:
            return "presupuesto_de_run_agotado"
        if self.attempts_for(case_id) >= self.max_per_case:
            return "presupuesto_del_caso_agotado"
        return ""

    def as_dict(self) -> dict:
        return {
            "max_per_run": self.max_per_run,
            "max_per_case": self.max_per_case,
            "max_service_starts": self.max_service_starts,
            "used_run": self._used_run,
            "used_by_case": dict(self._used_by_case),
            "service_starts": self._service_starts,
            "ledger": list(self._ledger),
        }


def build_budget() -> RecoveryBudget:
    """Lee recovery_config y aplica INV-7 (el minimo gana)."""
    try:
        import recovery_config as rc
        per_run = rc.recovery_max_per_run()
        per_case = rc.recovery_max_per_case()
        # INV-7: arrancar el servicio abre un proceso en la maquina del operador.
        # El techo NO puede exceder lo que el 240 ya autoriza: UN intento por run.
        # agenda_web_launcher.ensure_agenda_web documenta "UN intento" (:144) y hace
        # UN solo subprocess.Popen (:148). Se respeta.
        service_starts = 1 if rc.hot_recovery_enabled() else 0
        # Y el per_case nunca puede exceder el per_run.
        per_case = min(per_case, per_run)
        return RecoveryBudget(per_run, per_case, service_starts)
    except Exception:                              # noqa: BLE001
        # Fallback: modo observacion, cero riesgo.
        return RecoveryBudget(0, 0, 0)
