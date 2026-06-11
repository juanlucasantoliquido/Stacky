"""CLI del eval harness (F3.1 + H6.1).

    python -m evals run <agent_type>
    python -m evals run all
    python -m evals list
    python -m evals harvest <execution_id> [--name <caso>]

Exit code 0 si todo ok; 1 si algún caso falló (para usarlo como gate opcional).
"""
from __future__ import annotations

import sys

from . import list_agents, run_agent, run_all


def _print_results(agent: str, results: list) -> bool:
    if not results:
        print(f"  {agent}: (sin golden set)")
        return True
    all_ok = True
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        if not r.ok:
            all_ok = False
        detail = f" — {'; '.join(r.reasons)}" if r.reasons else ""
        print(f"  [{mark}] {agent}/{r.case.name} score={r.score} passed={r.passed_contract}{detail}")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2

    cmd = argv[0]

    if cmd == "list":
        agents = list_agents()
        if not agents:
            print("(no hay golden sets en evals/agents/)")
        for a in agents:
            print(a)
        return 0

    if cmd == "run":
        target = argv[1] if len(argv) > 1 else "all"
        all_ok = True
        if target == "all":
            grouped = run_all()
            if not grouped:
                print("(no hay golden sets en evals/agents/)")
            for agent, results in grouped.items():
                if not _print_results(agent, results):
                    all_ok = False
        else:
            results = run_agent(target)
            if not results:
                print(f"agent '{target}' no tiene golden set (revisá evals/agents/)")
                return 2
            all_ok = _print_results(target, results)
        return 0 if all_ok else 1

    if cmd == "harvest":
        if len(argv) < 2:
            print("uso: python -m evals harvest <execution_id> [--name <caso>]")
            return 2
        try:
            execution_id = int(argv[1])
        except ValueError:
            print(f"execution_id debe ser entero, recibí: '{argv[1]}'")
            return 2
        # parsear --name <valor>
        name: str | None = None
        rest = argv[2:]
        for i, arg in enumerate(rest):
            if arg == "--name" and i + 1 < len(rest):
                name = rest[i + 1]
                break
        from .harvest import harvest as _harvest, HarvestError
        try:
            out_path = _harvest(execution_id=execution_id, name=name)
            print(f"Golden escrito: {out_path}")
            return 0
        except HarvestError as exc:
            print(f"Error: {exc}")
            return 1

    print(f"comando desconocido: {cmd}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
