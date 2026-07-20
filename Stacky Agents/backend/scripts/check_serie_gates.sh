#!/usr/bin/env bash
# Plan 195 — gates §7.1/7.3/7.4 en un comando. Exit 0 = todo limpio.
set -u
fail=0
python -m compileall .. -q || { echo "GATE1 compileall FALLO"; fail=1; }
dups_flags=$(grep -o "STACKY_[A-Z_]*_ENABLED" ../services/harness_flags.py | sort | uniq -d)
[ -n "$dups_flags" ] && { echo "GATE3 flags duplicadas: $dups_flags"; fail=1; }
dups_tests=$(sort ./run_harness_tests.sh | uniq -d | grep "test_")
[ -n "$dups_tests" ] && { echo "GATE4 registros duplicados: $dups_tests"; fail=1; }
[ $fail -eq 0 ] && echo "GATES BACKEND OK"
exit $fail
