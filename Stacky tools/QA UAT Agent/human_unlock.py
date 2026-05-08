"""
human_unlock.py — Capa de desbloqueo humano para QA UAT Agent.

RESPONSABILIDADES:
  1. Registrar blockers cuando el pipeline no puede avanzar.
  2. Presentar preguntas estructuradas al operador (stdout + blockers.json).
  3. Emitir eventos forenses de lifecycle del blocker.
  4. Proveer API para que el operador responda y desbloquee.

FLUJO:
  pipeline detecta condición de bloqueo
    → human_unlock.register_blocker(stage, reason, question)
    → devuelve blocker_id
    → pipeline retorna {"ok": false, "verdict": "BLOCKED", "blocker_id": ...}
  operador lee blockers.json o la UI de Stacky
    → llama human_unlock.resolve_blocker(blocker_id, answer)
    → pipeline puede continuar (--resume)

DISEÑO: sin estado global — cada instancia es para un run específico.
Backward-compatible: funciona sin ForensicEventLogger.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from blocker_registry import BlockerRegistry


class HumanUnlock:
    """
    Gestor de desbloqueos humanos para un run de QA UAT.

    Uso:
        hu = HumanUnlock(run_id="uat-70-...", run_dir=run_dir, forensic_log=log)

        # Registrar blocker
        bid = hu.block(
            stage="runner",
            reason="session_expired",
            question="La sesión de AgendaWeb expiró. ¿Desea re-autenticar?",
            options=["sí", "no"],
        )

        # Resolver blocker (llamado por operador o CLI)
        hu.resolve(bid, answer="sí")

        # Verificar
        if hu.all_resolved():
            # continuar pipeline
    """

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        forensic_log: Optional[Any] = None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.forensic_log = forensic_log
        self._registry = BlockerRegistry(run_id, run_dir)

    # ── API principal ──────────────────────────────────────────────────────────

    def block(
        self,
        stage: str,
        reason: str,
        question: str,
        *,
        options: Optional[list[str]] = None,
        source_event_id: Optional[str] = None,
        extra: Optional[dict] = None,
        emit_event: bool = True,
    ) -> str:
        """
        Registrar un blocker y emitir evento forense.

        Devuelve blocker_id.
        """
        bid = self._registry.register(
            stage=stage,
            reason=reason,
            question=question,
            options=options,
            source_event_id=source_event_id,
            extra=extra,
        )

        if emit_event and self.forensic_log is not None:
            try:
                self.forensic_log.emit(
                    source="pipeline",
                    event_type="human_unlock.blocker_registered",
                    category="blocker",
                    stage=stage,
                    action="register_blocker",
                    status="blocked",
                    level="warning",
                    message=f"Blocker registrado: {reason}",
                    payload={
                        "blocker_id": bid,
                        "reason": reason,
                        "question": question,
                        "options": options or [],
                        "source_event_id": source_event_id,
                    },
                )
            except Exception:
                pass

        return bid

    def resolve(
        self,
        blocker_id: str,
        answer: str,
        *,
        answered_by: str = "operator",
        emit_event: bool = True,
    ) -> bool:
        """
        Resolver un blocker con la respuesta del operador.

        Devuelve True si se encontró y resolvió.
        """
        ok = self._registry.resolve(blocker_id, answer, answered_by=answered_by)
        if not ok:
            return False

        blocker = self._registry.get(blocker_id)

        if emit_event and self.forensic_log is not None:
            try:
                self.forensic_log.emit(
                    source="pipeline",
                    event_type="human_unlock.blocker_resolved",
                    category="blocker",
                    stage=blocker.get("stage", "unknown") if blocker else "unknown",
                    action="resolve_blocker",
                    status="completed",
                    level="info",
                    message=f"Blocker resuelto por {answered_by}",
                    payload={
                        "blocker_id": blocker_id,
                        "answer": answer,
                        "answered_by": answered_by,
                        "reason": blocker.get("reason") if blocker else None,
                    },
                )
            except Exception:
                pass

        return True

    def skip(
        self,
        blocker_id: str,
        *,
        skipped_by: str = "operator",
        emit_event: bool = True,
    ) -> bool:
        """Marcar un blocker como skipped."""
        ok = self._registry.skip(blocker_id, skipped_by=skipped_by)
        if not ok:
            return False

        if emit_event and self.forensic_log is not None:
            try:
                self.forensic_log.emit(
                    source="pipeline",
                    event_type="human_unlock.blocker_skipped",
                    category="blocker",
                    stage="unknown",
                    action="skip_blocker",
                    status="completed",
                    level="warning",
                    message=f"Blocker skipped por {skipped_by}",
                    payload={"blocker_id": blocker_id, "skipped_by": skipped_by},
                )
            except Exception:
                pass

        return True

    # ── Consultas ──────────────────────────────────────────────────────────────

    def get_pending(self) -> list[dict]:
        return self._registry.get_pending()

    def all_resolved(self) -> bool:
        return self._registry.all_resolved()

    def summary(self) -> dict:
        return self._registry.summary()

    def get(self, blocker_id: str) -> Optional[dict]:
        return self._registry.get(blocker_id)

    # ── CLI helper: print pending blockers en formato legible ─────────────────

    def print_pending(self) -> None:
        """Imprime blockers pendientes en stdout (para uso CLI/operator)."""
        pending = self.get_pending()
        if not pending:
            print("[HumanUnlock] Sin blockers pendientes.")
            return
        print(f"\n[HumanUnlock] {len(pending)} blocker(s) pendiente(s) en run {self.run_id}:\n")
        for i, b in enumerate(pending, 1):
            print(f"  [{i}] {b['blocker_id']}")
            print(f"      Stage   : {b['stage']}")
            print(f"      Reason  : {b['reason']}")
            print(f"      Question: {b['question']}")
            if b["options"]:
                print(f"      Options : {', '.join(b['options'])}")
            print()

    # ── CLI API: resolver desde línea de comandos ─────────────────────────────

    @classmethod
    def resolve_from_cli(
        cls,
        run_dir: Path,
        run_id: str,
        blocker_id: str,
        answer: str,
        *,
        answered_by: str = "operator_cli",
    ) -> dict:
        """
        Resolver un blocker desde CLI sin ForensicEventLogger.

        Uso:
          python -c "
          from human_unlock import HumanUnlock; from pathlib import Path
          r = HumanUnlock.resolve_from_cli(Path('evidence/70/uat-70-...'), 'uat-70-...', 'blk-abc', 'sí')
          print(r)
          "
        """
        hu = cls(run_id=run_id, run_dir=run_dir)
        ok = hu.resolve(blocker_id, answer, answered_by=answered_by, emit_event=False)
        return {
            "ok": ok,
            "blocker_id": blocker_id,
            "answer": answer,
            "answered_by": answered_by,
            "remaining_pending": len(hu.get_pending()),
        }

    @classmethod
    def list_blockers(cls, run_dir: Path, run_id: str) -> list[dict]:
        """Listar todos los blockers de un run desde CLI."""
        hu = cls(run_id=run_id, run_dir=run_dir)
        return hu._registry.get_all()


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser(
        description="Gestión de blockers para QA UAT runs",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--run-dir", required=True, help="Directorio del run (evidence/<ticket>/<run_id>/)")
    p.add_argument("--run-id", required=True, help="Run ID (uat-70-...)")
    sub = p.add_subparsers(dest="cmd")

    # list
    sub.add_parser("list", help="Listar todos los blockers del run")

    # resolve
    res_p = sub.add_parser("resolve", help="Resolver un blocker con una respuesta")
    res_p.add_argument("--blocker-id", required=True)
    res_p.add_argument("--answer", required=True)
    res_p.add_argument("--by", default="operator_cli")

    args = p.parse_args()
    run_dir = Path(args.run_dir)

    if args.cmd == "list":
        blockers = HumanUnlock.list_blockers(run_dir, args.run_id)
        print(json.dumps(blockers, ensure_ascii=False, indent=2))

    elif args.cmd == "resolve":
        result = HumanUnlock.resolve_from_cli(
            run_dir, args.run_id, args.blocker_id, args.answer, answered_by=args.by
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["ok"] else 1)

    else:
        p.print_help()
        sys.exit(1)
