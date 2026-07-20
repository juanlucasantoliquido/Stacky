#!/usr/bin/env bash
# Plan 197 v2 - gates compuestos de la serie UX 164-194. Correr con Git Bash desde la RAIZ del repo.
# Exit 0 = todo limpio. Cada chequeo es tolerante a "todavia no existe" (pre-modulo comun).
# PRERREQUISITO: Gate 0.7 ejecutado una unica vez (dedup preexistente de los runners, C3).
set -u
fail=0
FE="Stacky Agents/frontend"
BE="Stacky Agents/backend"
# G1 compileall backend con el INTERPRETE CANONICO (.venv py3.13.5, seccion 4.1) y excluyendo
# AMBOS venvs (C4: "python" del PATH es hoy 3.11.9 = justo la version prohibida por 4.1, y
# compilar site-packages ajenos es lento y fragil)
"$BE/.venv/Scripts/python.exe" -m compileall "$BE" -q -x "(\.venv|venv)" || { echo "G1 compileall FALLO"; fail=1; }
# G4a flags backend duplicadas - SOLO definiciones FlagSpec (key="...").
# C1: el patron v1 (toda mencion STACKY_*_ENABLED) daba DECENAS de falsos duplicados con el
# arbol limpio (una flag aparece legitimamente en key=, categorias, requires= y comentarios).
# Verificado 2026-07-18: 217 definiciones key=", 0 duplicadas.
dups_flags=$(grep -o 'key="STACKY_[A-Z_0-9]*"' "$BE/services/harness_flags.py" | sort | uniq -d)
[ -n "$dups_flags" ] && { echo "G4a FlagSpec duplicada: $dups_flags"; fail=1; }
# G4b registros de tests duplicados (sh y ps1; patron test_ generico, leccion 195 C2).
# Baseline limpio SOLO tras el Gate 0.7 (hoy tests/test_harness_flags.py esta 2x en ambos, C3).
dups_sh=$(sort "$BE/scripts/run_harness_tests.sh" | uniq -d | grep "test_")
[ -n "$dups_sh" ] && { echo "G4b duplicados en run_harness_tests.sh: $dups_sh"; fail=1; }
dups_ps=$(sort "$BE/scripts/run_harness_tests.ps1" | uniq -d | grep "test_")
[ -n "$dups_ps" ] && { echo "G4b duplicados en run_harness_tests.ps1: $dups_ps"; fail=1; }
# G5 keydown: App.tsx en 0 tras el plan 172; techo global 8 (lista nominal 197 seccion 6.4)
kd_app=$(grep -c 'addEventListener("keydown"' "$FE/src/App.tsx")
if [ -f "$FE/src/services/shortcuts.ts" ] && [ "$kd_app" -ne 0 ]; then
  echo "G5 App.tsx tiene keydown directo ($kd_app) con el registry 172 ya presente"; fail=1
fi
kd_total=$(grep -rn 'addEventListener("keydown"' "$FE/src" | wc -l)
[ "$kd_total" -gt 8 ] && { echo "G5 conteo keydown $kd_total > techo 8"; fail=1; }
# G6 clipboard fuera del canonico (solo aplica cuando copyService existe, plan 194)
if [ -f "$FE/src/services/copyService.ts" ]; then
  cb=$(grep -rn "navigator.clipboard" "$FE/src" --include=*.ts --include=*.tsx | grep -v "copyService" | grep -v ".test." | wc -l)
  [ "$cb" -ne 0 ] && { echo "G6 navigator.clipboard fuera de copyService: $cb"; fail=1; }
fi
# G7 flagGate unico lector de FEATURE (solo aplica cuando flagGate existe).
# C5: barre TODO src/ (useUiPerfFlags del 174 vive en hooks/, no en services/), con allowlist
# de ADMINISTRACION (HarnessFlagsPanel y MemoryConfigPanel hacen list+update del panel).
if [ -f "$FE/src/services/flagGate.ts" ]; then
  readers=$(grep -rln "HarnessFlags.list" "$FE/src" --include=*.ts --include=*.tsx | grep -v "flagGate" | grep -v "HarnessFlagsPanel" | grep -v "MemoryConfigPanel" | grep -v ".test.")
  [ -n "$readers" ] && { echo "G7 lectores de flag fuera de flagGate: $readers"; fail=1; }
fi
[ $fail -eq 0 ] && echo "GATES SERIE UX OK"
exit $fail
