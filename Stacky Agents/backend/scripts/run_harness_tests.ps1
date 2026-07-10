# V1.4a — Runner curado del arnes (plan 22), version PowerShell para dev local.
# Equivalente a run_harness_tests.sh: corre cada archivo del arnes UNO POR UNO
# (esquiva la polucion de la suite completa). Exit 1 si alguno falla o falta.
#
# Uso:  pwsh scripts/run_harness_tests.ps1   (o powershell)
# La lista es un RATCHET: solo crece. Mantener en sync con run_harness_tests.sh.

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$HarnessTestFiles = @(
  # Nucleo del arnes
  "tests/test_harness_flags.py",
  "tests/test_harness_health.py",
  "tests/test_harness_h8_kpis.py",
  "tests/test_model_policy.py",
  "tests/test_run_contract.py",
  "tests/test_runaway_guard.py",
  "tests/test_codex_telemetry.py",
  "tests/test_codex_post_run.py",
  "tests/test_claude_code_cli_phase1.py",
  # Plan 22 V0
  "tests/test_harness_profiles.py",
  "tests/test_harness_failure.py",
  "tests/test_harness_pricing.py",
  "tests/test_harness_health_v0.py",
  "tests/test_run_guard.py",
  "tests/test_run_slots.py",
  "tests/test_run_launch_guards.py",
  "tests/test_mark_terminal_failure_kind.py",
  "tests/test_telemetry_cost_estimation.py",
  # Plan 22 V1
  "tests/test_u1_executions_filters.py",
  "tests/test_u1_local_diag_cli_runtimes.py",
  "tests/test_u1_self_review.py",
  "tests/test_agent_prompt_registry.py",
  "tests/test_run_advisor.py",
  "tests/test_artifact_intake.py",
  "tests/test_v15_memory_channel.py",
  # Plan 22 V2
  "tests/test_u2_cost_metrics.py",
  "tests/test_u2_pipeline_orchestrator.py",
  "tests/test_u2_publish_review_mode.py",
  "tests/test_run_fingerprint.py",
  "tests/test_evals_promote.py",
  "tests/test_eval_gate_modes.py",
  "tests/conformance/test_runtime_conformance.py",
  # Plan 49 - Blindaje de calidad determinista
  "tests/test_golden_extraction.py",
  "tests/test_extraction_detects_pathologies.py",
  "tests/test_harness_ratchet_meta.py",
  "tests/test_no_determinism_sentinel.py",
  # Plan 50 - Saneamiento determinista de la epica + warnings
  "tests/test_epic_sanitize.py",
  "tests/test_epic_structure_warnings.py",
  "tests/test_catalog_grounding_warnings.py",
  # Plan 51 - Gates correctivos deterministas de epica
  "tests/test_epic_gate.py",
  "tests/test_golden_catalog_diff.py",
  # Plan 52 - Paridad runtimes autopublish + idempotencia comentarios
  "tests/test_run_brief_autopublish_parity.py",
  "tests/test_ado_comment_idempotency.py",
  "tests/test_issue_observability.py",
  "tests/test_persist_issue_ticket.py",
  # Plan 53 - Selector adaptativo de modelo/effort por confidence
  "tests/test_adaptive_selector.py",
  "tests/test_adaptive_selector_wiring.py",
  # Plan 54 - Memoria que empuja: paridad rejection_lessons 3 runtimes
  "tests/test_memory_prefix.py",
  "tests/test_base_prompt_parity.py",
  "tests/test_cli_memory_parity.py",
  "tests/test_rejection_sink.py",
  "tests/test_rejection_lessons_trim.py",
  # Plan 55 - Preview ejecutable portafolio epicas
  "tests/test_epic_payload_preview.py",
  "tests/test_epic_preview_endpoint.py",
  "tests/test_epic_portfolio_preview.py",
  # Plan 56 - Gate de regresion golden
  "tests/test_regression_capture.py",
  "tests/test_regression_goldens.py",
  "tests/test_regression_goldens_store.py",
  "tests/test_epic_gate_regression.py",
  # Plan 57 - FA-36 Especulacion anticipatoria
  "tests/test_speculative_hash.py",
  "tests/test_speculative_parity.py",
  "tests/test_speculative_flag.py",
  "tests/test_speculative_claim_flow.py",
  # Plan 58 - Bucle de convergencia de calidad determinista
  "tests/test_convergence_loop.py",
  "tests/test_convergence_wiring.py",
  # Plan 59 - Descomposicion vertical epica->hijos
  "tests/test_epic_decomposition.py",
  # Plan 60 - Aprendizaje bidireccional ediciones ADO
  "tests/test_ado_edit_diff.py",
  "tests/test_ado_edit_detect.py",
  "tests/test_ado_edit_ledger.py",
  "tests/test_ado_edit_learning.py",
  "tests/test_ado_edit_sweep.py",
  "tests/test_plan81_negative_golden_from_edits.py",
  # Plan 87 - Panel DevOps: creador gráfico de pipelines
  "tests/test_plan87_devops_flag.py",
  "tests/test_plan87_devops_endpoints.py",
  "tests/test_plan87_drafts_validation.py",
  # Plan 88 - Publicaciones parametrizables de procesos DevOps
  "tests/test_plan88_publications_flag.py",
  "tests/test_plan88_publication_spec.py",
  "tests/test_plan88_presets_validation.py",
  "tests/test_plan88_materialize_endpoint.py",
  # Plan 89 - Inicializacion de ambientes DevOps
  "tests/test_plan89_environments_flag.py",
  "tests/test_plan89_environment_layout.py",
  "tests/test_plan89_environment_plan_apply.py",
  "tests/test_plan89_env_settings_validation.py",
  "tests/test_plan89_environments_endpoints.py",
  # Plan 90 - Agente DevOps interactivo multi-turno
  "tests/test_plan90_devops_agent_flag.py",
  "tests/test_plan90_devops_agent_registry.py",
  "tests/test_plan90_devops_agent_endpoints.py",
  # Plan 91 - Registro de servidores DevOps
  "tests/test_plan91_servers_flag.py",
  "tests/test_plan91_server_registry.py",
  "tests/test_plan91_servers_endpoints.py",
  "tests/test_plan91_rdp_endpoint.py",
  # Plan 93 - Preflight "va a funcionar": semaforo de pipelines (ADO + GitLab)
  "tests/test_plan93_preflight_flag.py",
  "tests/test_plan93_preflight_pure.py",
  "tests/test_plan93_preflight_providers.py",
  "tests/test_plan93_preflight_endpoint.py",
  # Plan 94 - Caja fuerte de variables: secretos del pipeline fuera del YAML (ADO + GitLab)
  "tests/test_plan94_variables_flag.py",
  "tests/test_plan94_variables_pure.py",
  "tests/test_plan94_variables_providers.py",
  "tests/test_plan94_variables_endpoints.py",
  # Plan 95 - Llevar a producción: MR/PR + merge HITL + paridad ADO commit/trigger/monitor
  "tests/test_plan95_production_flag.py",
  "tests/test_plan95_ado_parity.py",
  "tests/test_plan95_mr_providers.py",
  "tests/test_plan95_production_endpoints.py",
  # Plan 97 - Presets de pasos de pipeline por stack + deteccion opcional
  "tests/test_plan97_stack_detect_flag.py",
  "tests/test_plan97_stack_detector.py",
  "tests/test_plan97_stack_detect_endpoint.py",
  # Plan 96 - Doctor de pipelines: el fallo explicado en llano (ADO + GitLab)
  "tests/test_plan96_doctor_flag.py",
  "tests/test_plan96_failure_doctor.py",
  "tests/test_plan96_logs_providers.py",
  "tests/test_plan96_doctor_endpoint.py",
  # Plan 104 - Filtro de presets por stack + doctores IA por seccion DevOps
  "tests/test_plan104_section_doctor.py",
  # Plan 105 - Consola remota prompts por servidor
  "tests/test_plan105_remote_exec_service.py",
  "tests/test_plan105_console_prompt.py",
  "tests/test_plan105_remote_console_flag.py",
  "tests/test_plan105_remote_console_api.py",
  # Plan 107 - Preview arbol directorios + sandbox raiz DevOps
  "tests/test_plan107_flags.py",
  "tests/test_plan107_sandbox_guard.py",
  "tests/test_plan107_sandbox_endpoints.py",
  # Plan 108 - Agente DevOps opera EN el servidor seleccionado (anclaje remoto)
  "tests/test_plan108_console_repair.py",
  "tests/test_plan108_flags.py",
  "tests/test_plan108_winrm_diagnosis.py",
  "tests/test_plan108_prompt_hardening.py",
  "tests/test_plan108_agent_server_binding.py",
  "tests/test_plan108_environment_remote.py",
  # Plan 106 - Modelo local Qwen 3 para analisis de codigo y pipelines
  "tests/test_plan106_local_llm_config.py",
  "tests/test_plan106_local_llm_bridge.py",
  "tests/test_plan106_analyze_code_api.py",
  "tests/test_plan106_suggest_pipeline_api.py",
  "tests/test_plan106_playground_api.py",
  # Plan 109 - Grafo documental READ-ONLY + salud documental
  "tests/test_plan109_flag.py",
  "tests/test_plan109_parsers.py",
  "tests/test_plan109_build_graph.py",
  "tests/test_plan109_doc_health.py",
  "tests/test_plan109_graph_endpoint.py",
  # Plan 110 - Revisor de PRs (Haiku solo-lectura + modelo local)
  "tests/test_plan110_list_merge_requests.py",
  "tests/test_plan110_pr_review_detail_diff.py",
  "tests/test_plan110_pr_review_execute.py",
  "tests/test_plan110_pr_review_flags.py",
  "tests/test_plan110_pr_review_haiku.py",
  "tests/test_plan110_pr_review_list_endpoint.py",
  "tests/test_plan110_pr_review_local.py",
  "tests/test_plan110_pr_review_models.py",
  # Plan 112 - Retrieval hibrido docs-rag (lexico + 1-hop + prior backlinks)
  "tests/test_plan112_flags.py",
  "tests/test_plan112_backlink_index.py",
  "tests/test_plan112_search_hybrid.py",
  "tests/test_plan112_search_route.py",
  "tests/test_plan112_telemetry.py",
  "tests/test_plan112_doc_consultor_fallback.py",
  # Plan 113 - Documentador 1-click polifuncional
  "tests/test_plan113_flags_and_agent.py",
  "tests/test_plan113_plan_selector.py",
  "tests/test_plan113_invoke_and_parse.py",
  "tests/test_plan113_git_gate.py",
  "tests/test_plan113_apply.py",
  "tests/test_plan113_endpoints.py",
  # Plan 61 - Gate determinista del flujo funcional (Task)
  "tests/test_task_gate_flags.py",
  "tests/test_task_gate.py",
  "tests/test_create_child_task_gate.py",
  # Plan 68 - Paridad de visibilidad de streams Codex vs Claude (AD-1 stderr tail)
  "tests/test_cli_visibility_parity.py",
  # Clasificacion colateral (Plan 68): 2 tests preexistentes sin clasificar
  "tests/test_codex_prompt_dedup.py",
  "tests/test_prompt_dedup_guard.py",
  # Plan 67 - Disciplina de procesos: reusar por default
  "tests/test_process_discipline.py",
  # Plan 66 - Desatascador visibilidad total + subida forzada
  "tests/test_unblocker_board.py",
  # Plan 73 - Generador declarativo PipelineSpec->ADO/GitLab
  "tests/test_plan73_pipeline_spec.py",
  "tests/test_plan73_validate.py",
  "tests/test_plan73_render_ado.py",
  "tests/test_plan73_render_gitlab.py",
  "tests/test_plan73_repo_writer.py",
  "tests/test_plan73_generator_endpoint.py",
  "tests/test_plan73_routes_registered.py",
  "tests/test_plan73_round_trip.py",
  # Plan 74 — Migrador ADO→GitLab
  "tests/test_plan74_migrator_map.py",
  "tests/test_plan74_migrator_core.py",
  "tests/test_plan74_migrator_epics.py",
  "tests/test_plan74_migrator_attachments.py",
  "tests/test_plan74_migrator_executor.py",
  "tests/test_plan74_migrator_verify.py",
  "tests/test_plan74_migrator_api.py",
  "tests/test_plan74_migrator_wiring.py",
  "tests/test_plan74_migrator_idempotency.py",
  "tests/test_plan74_migrator_readonly_origin.py",
  "tests/test_plan74_routes_registered.py",
  # Plan 75 — Deep links bidireccionales GitLab
  "tests/test_plan75_deep_links_compose.py",
  "tests/test_plan75_gitlab_provider_urls.py",
  "tests/test_plan75_deep_links_epic_fallback.py",
  "tests/test_plan75_deep_links_bidirectional.py",
  "tests/test_plan75_deep_links_wiring.py",
  "tests/test_plan75_deep_links_no_double_encode.py",
  # Plan 76 — Eval codebase-memory-mcp
  "tests/test_plan76_codebase_memory_mcp.py",
  "tests/test_plan76_routes_registered.py",
  "tests/test_plan76_ratchet_byteidentical.py",
  # Plan 77 — Issue pipeline fases comentarios + color
  "tests/test_issue_phase_mapper.py",
  "tests/test_issue_phase_publisher.py",
  "tests/test_issue_no_children_guard.py",
  "tests/test_issue_phase_runtime_parity.py",
  "tests/test_harness_flags.py",
  # Plan 79 — Estados de tarea deterministas y configurables
  "tests/test_plan79_flag.py",
  "tests/test_plan79_resolver.py",
  "tests/test_plan79_safe_transition.py",
  "tests/test_plan79_apply_start.py",
  "tests/test_plan79_apply_final.py",
  "tests/test_plan79_centinela_estados.py",
  "tests/test_plan79_validate_states.py",
  "tests/test_plan79_agent_md_note.py",
  "tests/test_plan79_ratchet.py",
  # Plan 80 — Wiring real codebase-memory-mcp
  "tests/test_plan80_flags.py",
  "tests/test_plan80_wiring_pure.py",
  "tests/test_plan80_writer.py",
  "tests/test_plan80_codex.py",
  "tests/test_plan80_copilot.py",
  "tests/test_plan80_savings.py",
  "tests/test_plan80_status_shape.py",
  "tests/test_plan80_ratchet_byteidentical.py",
  "tests/test_plan80_routes_registered.py",
  # Plan 82 - Claridad de configuracion del arnes (requires + profile_deltas)
  "tests/test_harness_flags_requires.py",
  "tests/test_harness_profile_deltas.py",
  # Plan 83 - Bounds declarativos para flags numericas
  "tests/test_harness_flags_bounds.py"
  # Plan 84 - Hot-apply honesto: flags de startup (restart_required)
  "tests/test_harness_flags_restart_required.py"
  "tests/test_harness_flags_endpoint_restart.py"
  # Plan 85 - Cableado honesto: flags reservadas sin consumidor
  "tests/test_flag_wiring.py"
  # Plan 86 - Flags para mortales: ayuda en lenguaje llano
  "tests/test_harness_flags_help.py"
)

$pass = 0; $fail = 0; $missing = 0
$failed = @()

foreach ($f in $HarnessTestFiles) {
  if (-not (Test-Path $f)) {
    Write-Host "MISSING  $f"
    $missing++; $failed += "$f (missing)"; continue
  }
  & $python -m pytest $f -q | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "PASS     $f"; $pass++
  } else {
    Write-Host "FAIL     $f"; $fail++; $failed += $f
  }
}

Write-Host ""
Write-Host "===================== RESUMEN ARNES ====================="
Write-Host "PASS=$pass  FAIL=$fail  MISSING=$missing  TOTAL=$($HarnessTestFiles.Count)"
if ($fail -gt 0 -or $missing -gt 0) {
  Write-Host "Archivos con problema:"
  foreach ($ff in $failed) { Write-Host "  - $ff" }
  exit 1
}
Write-Host "Todos los archivos del arnes pasan aislados."
exit 0
