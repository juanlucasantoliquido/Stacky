#!/usr/bin/env bash
# V1.4a — Runner curado del arnés (plan 22).
#
# Ejecuta los archivos de test del arnés UNO POR UNO con `pytest <archivo> -q`.
# Correr por archivo esquiva la polución conocida de la suite completa
# (engine sqlite in-memory compartido + singletons de app, ver D7 del plan 22).
#
# La lista HARNESS_TEST_FILES es un RATCHET: solo crece. Un archivo entra acá
# cuando pasa aislado; CI impide que la cobertura se encoja silenciosamente.
#
# Uso:  bash scripts/run_harness_tests.sh
# Exit: 0 si todos verdes; 1 si alguno falla (o no existe).
set -u

cd "$(dirname "$0")/.." || exit 2

PYTHON="${PYTHON:-python}"

# Lista curada (archivos que pasan en aislamiento). Mantener ordenada por área.
HARNESS_TEST_FILES=(
  # — Núcleo del arnés (F1-F3, H0-H8) —
  tests/test_harness_flags.py
  tests/test_harness_health.py
  tests/test_harness_h8_kpis.py
  tests/test_model_policy.py
  tests/test_run_contract.py
  tests/test_runaway_guard.py
  tests/test_codex_telemetry.py
  tests/test_codex_post_run.py
  tests/test_claude_code_cli_phase1.py
  # — Plan 22 · V0 —
  tests/test_harness_profiles.py
  tests/test_harness_failure.py
  tests/test_harness_pricing.py
  tests/test_harness_health_v0.py
  tests/test_run_guard.py
  tests/test_run_slots.py
  tests/test_run_launch_guards.py
  tests/test_mark_terminal_failure_kind.py
  tests/test_telemetry_cost_estimation.py
  # — Plan 22 · V1 —
  tests/test_u1_executions_filters.py
  tests/test_u1_local_diag_cli_runtimes.py
  tests/test_u1_self_review.py
  tests/test_agent_prompt_registry.py
  tests/test_run_advisor.py
  tests/test_artifact_intake.py
  tests/test_v15_memory_channel.py
  # — Plan 22 · V2 —
  tests/test_u2_cost_metrics.py
  tests/test_u2_pipeline_orchestrator.py
  tests/test_u2_publish_review_mode.py
  tests/test_run_fingerprint.py
  tests/test_evals_promote.py
  tests/test_eval_gate_modes.py
  tests/conformance/test_runtime_conformance.py
  # — Plan 49 · Blindaje de calidad determinista —
  tests/test_golden_extraction.py
  tests/test_extraction_detects_pathologies.py
  tests/test_harness_ratchet_meta.py
  tests/test_no_determinism_sentinel.py
  # — Plan 50 · Saneamiento determinista de la épica + warnings —
  tests/test_epic_sanitize.py
  tests/test_epic_structure_warnings.py
  tests/test_catalog_grounding_warnings.py
  # — Plan 51 · Gates correctivos deterministas de épica —
  tests/test_epic_gate.py
  tests/test_golden_catalog_diff.py
  # — Plan 52 · Paridad runtimes autopublish + idempotencia comentarios —
  tests/test_run_brief_autopublish_parity.py
  tests/test_ado_comment_idempotency.py
  tests/test_issue_observability.py
  tests/test_persist_issue_ticket.py
  # — Plan 53 · Selector adaptativo de modelo/effort por confidence —
  tests/test_adaptive_selector.py
  tests/test_adaptive_selector_wiring.py
  # — Plan 54 · Memoria que empuja: paridad rejection_lessons 3 runtimes —
  tests/test_memory_prefix.py
  tests/test_base_prompt_parity.py
  tests/test_cli_memory_parity.py
  tests/test_rejection_sink.py
  tests/test_rejection_lessons_trim.py
  # — Plan 55 · Preview ejecutable portafolio épicas —
  tests/test_epic_payload_preview.py
  tests/test_epic_preview_endpoint.py
  tests/test_epic_portfolio_preview.py
  # — Plan 56 · Gate de regresión golden —
  tests/test_regression_capture.py
  tests/test_regression_goldens.py
  tests/test_regression_goldens_store.py
  tests/test_epic_gate_regression.py
  # — Plan 57 · FA-36 Especulación anticipatoria —
  tests/test_speculative_hash.py
  tests/test_speculative_parity.py
  tests/test_speculative_flag.py
  tests/test_speculative_claim_flow.py
  # — Plan 58 · Bucle de convergencia de calidad determinista —
  tests/test_convergence_loop.py
  tests/test_convergence_wiring.py
  # — Plan 59 · Descomposición vertical épica→hijos —
  tests/test_epic_decomposition.py
  # — Plan 60 · Aprendizaje bidireccional ediciones ADO —
  tests/test_ado_edit_diff.py
  tests/test_ado_edit_detect.py
  tests/test_ado_edit_ledger.py
  tests/test_ado_edit_learning.py
  tests/test_ado_edit_sweep.py
  tests/test_plan146_verified_fixes.py
  tests/test_plan81_negative_golden_from_edits.py
  # — Plan 87 · Panel DevOps: creador gráfico de pipelines —
  tests/test_plan87_devops_flag.py
  tests/test_plan87_devops_endpoints.py
  tests/test_plan87_drafts_validation.py
  # — Plan 88 · Publicaciones parametrizables de procesos DevOps —
  tests/test_plan88_publications_flag.py
  tests/test_plan88_publication_spec.py
  tests/test_plan88_presets_validation.py
  tests/test_plan88_materialize_endpoint.py
  # — Plan 89 · Inicialización de ambientes DevOps —
  tests/test_plan89_environments_flag.py
  tests/test_plan89_environment_layout.py
  tests/test_plan89_environment_plan_apply.py
  tests/test_plan89_env_settings_validation.py
  tests/test_plan89_environments_endpoints.py
  # — Plan 90 · Agente DevOps interactivo multi-turno —
  tests/test_plan90_devops_agent_flag.py
  tests/test_plan90_devops_agent_registry.py
  tests/test_plan90_devops_agent_endpoints.py
  # — Plan 91 · Registro de servidores DevOps —
  tests/test_plan91_servers_flag.py
  tests/test_plan91_server_registry.py
  tests/test_plan91_servers_endpoints.py
  tests/test_plan91_rdp_endpoint.py
  # — Plan 93 · Preflight "¿Va a funcionar?": semáforo de pipelines (ADO + GitLab) —
  tests/test_plan93_preflight_flag.py
  tests/test_plan93_preflight_pure.py
  tests/test_plan93_preflight_providers.py
  tests/test_plan93_preflight_endpoint.py
  # — Plan 94 · Caja fuerte de variables: secretos del pipeline fuera del YAML (ADO + GitLab) —
  tests/test_plan94_variables_flag.py
  tests/test_plan94_variables_pure.py
  tests/test_plan94_variables_providers.py
  tests/test_plan94_variables_endpoints.py
  # — Plan 95 · Llevar a producción: MR/PR + merge HITL + paridad ADO commit/trigger/monitor —
  tests/test_plan95_production_flag.py
  tests/test_plan95_ado_parity.py
  tests/test_plan95_mr_providers.py
  tests/test_plan95_production_endpoints.py
  # — Plan 97 · Presets de pasos de pipeline por stack + deteccion opcional —
  tests/test_plan97_stack_detect_flag.py
  tests/test_plan97_stack_detector.py
  tests/test_plan97_stack_detect_endpoint.py
  # — Plan 96 · Doctor de pipelines: el fallo explicado en llano (ADO + GitLab) —
  tests/test_plan96_doctor_flag.py
  tests/test_plan96_failure_doctor.py
  tests/test_plan96_logs_providers.py
  tests/test_plan96_doctor_endpoint.py
  # — Plan 104 · Filtro de presets por stack + doctores IA por seccion DevOps —
  tests/test_plan104_section_doctor.py
  # — Plan 105 · Consola remota prompts por servidor —
  tests/test_plan105_remote_exec_service.py
  tests/test_plan105_console_prompt.py
  tests/test_plan105_remote_console_flag.py
  tests/test_plan105_remote_console_api.py
  # — Plan 107 · Preview arbol directorios + sandbox raiz DevOps —
  tests/test_plan107_flags.py
  tests/test_plan107_sandbox_guard.py
  tests/test_plan107_sandbox_endpoints.py
  # — Plan 108 · Agente DevOps opera EN el servidor seleccionado (anclaje remoto) —
  tests/test_plan108_console_repair.py
  tests/test_plan108_flags.py
  tests/test_plan108_winrm_diagnosis.py
  tests/test_plan108_prompt_hardening.py
  tests/test_plan108_agent_server_binding.py
  tests/test_plan108_environment_remote.py
  # — Plan 106 · Modelo local Qwen 3 para análisis de código y pipelines —
  tests/test_plan106_local_llm_config.py
  tests/test_plan106_local_llm_bridge.py
  tests/test_plan106_analyze_code_api.py
  tests/test_plan106_suggest_pipeline_api.py
  tests/test_plan106_playground_api.py
  # — Plan 109 · Grafo documental READ-ONLY + salud documental —
  tests/test_plan109_flag.py
  tests/test_plan109_parsers.py
  tests/test_plan109_build_graph.py
  tests/test_plan109_doc_health.py
  tests/test_plan109_graph_endpoint.py
  # — Plan 110 · Revisor de PRs (Haiku solo-lectura + modelo local) —
  tests/test_plan110_list_merge_requests.py
  tests/test_plan110_pr_review_detail_diff.py
  tests/test_plan110_pr_review_execute.py
  tests/test_plan110_pr_review_flags.py
  tests/test_plan110_pr_review_haiku.py
  tests/test_plan110_pr_review_list_endpoint.py
  tests/test_plan110_pr_review_local.py
  tests/test_plan110_pr_review_models.py
  # — Plan 112 · Retrieval híbrido docs-rag (léxico + 1-hop + prior backlinks) —
  tests/test_plan112_flags.py
  tests/test_plan112_backlink_index.py
  tests/test_plan112_search_hybrid.py
  tests/test_plan112_search_route.py
  tests/test_plan112_telemetry.py
  tests/test_plan112_doc_consultor_fallback.py
  # — Plan 113 · Documentador 1-click polifuncional —
  tests/test_plan113_flags_and_agent.py
  tests/test_plan113_plan_selector.py
  tests/test_plan113_invoke_and_parse.py
  tests/test_plan113_git_gate.py
  tests/test_plan113_apply.py
  tests/test_plan113_endpoints.py
  tests/test_documenter_autonomy.py
  # — Plan 114 · Doctor de staleness doc↔código —
  tests/test_plan114_flag.py
  tests/test_plan114_staleness.py
  tests/test_plan114_graph_payload.py
  tests/test_plan114_fix_endpoint.py
  # — Plan 115 · Consolidación motor TF-IDF (lexical_core) —
  tests/test_plan115_lexical_core.py
  tests/test_plan115_golden_rag_retriever.py
  tests/test_plan115_golden_docs_rag.py
  tests/test_plan115_golden_memory_store.py
  tests/test_plan115_no_duplicate_math.py
  # — Plan 116 · Doctor de conexiones con remediación guiada —
  tests/test_plan116_connection_doctor_core.py
  tests/test_plan116_connection_probes.py
  tests/test_plan116_connections_endpoints.py
  tests/test_plan116_connection_doctor_flag.py
  # — Plan 117 · Insights locales de ejecuciones (IA local) —
  tests/test_plan117_insights_flags.py
  tests/test_plan117_insights_core.py
  tests/test_plan117_insights_sweep.py
  tests/test_plan117_insights_api.py
  tests/test_plan117_digest_narrative.py
  # — Plan 119 · Rediseño minimalista del shell DevOps —
  tests/test_plan119_devops_ui_v2_flag.py
  # — Plan 120 · Centro de Despliegues (deploy multi-destino, rollback 1-click) —
  tests/test_plan120_flags.py
  tests/test_plan120_planner.py
  tests/test_plan120_remote_exec_deploy.py
  tests/test_plan120_store.py
  tests/test_plan120_executor.py
  tests/test_plan120_api.py
  tests/test_plan120_ai_diagnosis.py
  # — Plan 128 · Tablero de evolución de planes (solo lectura) —
  tests/test_plan128_plans_board_flag.py
  tests/test_plan128_plans_board_parser.py
  tests/test_plan128_plans_board_git.py
  tests/test_plan128_plans_board_endpoints.py
  # — Plan 129 · Paleta global: búsqueda profunda multi-fuente —
  tests/test_plan129_flag.py
  tests/test_plan129_global_search_service.py
  tests/test_plan129_global_search_api.py
  # — Plan 61 · Gate determinista del flujo funcional (Task) —
  tests/test_task_gate_flags.py
  tests/test_task_gate.py
  tests/test_create_child_task_gate.py
  # — Plan 64 · RAG TF-IDF grounding catalog —
  tests/test_rag_context_enrichment.py
  tests/test_rag_perf.py
  tests/test_rag_retriever.py
  # — Plan 65 · GitLab TrackerProvider puerto + adapters ADO/GitLab —
  tests/test_tracker_provider_conformance.py
  tests/test_ado_provider.py
  tests/test_gitlab_client.py
  tests/test_gitlab_provider.py
  tests/test_tracker_factory.py
  tests/test_no_adoclient_outside_ado_provider.py
  tests/test_global_config_gitlab.py
  # — Plan 68 · Paridad de visibilidad de streams Codex vs Claude (AD-1 stderr tail) —
  tests/test_cli_visibility_parity.py
  # — Clasificación colateral (Plan 68): 2 tests preexistentes sin clasificar que rompían el meta-test —
  tests/test_codex_prompt_dedup.py
  tests/test_prompt_dedup_guard.py
  # — Plan 67 · Disciplina de procesos: reusar por default —
  tests/test_process_discipline.py
  # — Plan 66 · Desatascador visibilidad total + subida forzada —
  tests/test_unblocker_board.py
  # — Plan 70 · Desacople consumidores TrackerProvider —
  tests/test_plan70_provider_for_ticket.py
  tests/test_plan70_tracker_item_adapter.py
  tests/test_plan70_gitlab_provider_complete.py
  tests/test_plan70_group_comments.py
  tests/test_plan70_group_state.py
  tests/test_plan70_group_url.py
  tests/test_plan70_group_assignee_auth.py
  tests/test_plan70_group_attachments.py
  tests/test_plan70_group_create.py
  tests/test_plan70_group_helpers.py
  tests/test_plan70_group_sync.py
  tests/test_plan70_publisher_sync.py
  tests/test_plan70_no_typed_adoclient_in_api.py
  tests/test_plan70_smoke_gitlab.py
  # — Plan 71 — CIProvider sub-puerto —
  tests/test_plan71_ci_provider_protocol.py
  tests/test_plan71_ado_ci_provider.py
  tests/test_plan71_gitlab_ci_provider.py
  # — Plan 72 — Trigger y monitoreo CI (HITL) —
  tests/test_plan72_trigger_rules.py
  tests/test_plan72_ci_provider_trigger_port.py
  tests/test_plan72_routes_registered.py
  tests/test_plan72_trigger_endpoint.py
  tests/test_plan72_ado_trigger_not_implemented.py
  tests/test_plan72_preview_endpoint.py
  tests/test_plan72_monitor_endpoint.py
  # Plan 73 - Generador declarativo PipelineSpec->ADO/GitLab
  tests/test_plan73_pipeline_spec.py
  tests/test_plan73_validate.py
  tests/test_plan73_render_ado.py
  tests/test_plan73_render_gitlab.py
  tests/test_plan73_repo_writer.py
  tests/test_plan73_generator_endpoint.py
  tests/test_plan73_routes_registered.py
  tests/test_plan73_round_trip.py
  # Plan 74 - Migrador ADO->GitLab seguro e idempotente
  tests/test_plan74_migrator_map.py
  tests/test_plan74_migrator_core.py
  tests/test_plan74_migrator_epics.py
  tests/test_plan74_migrator_attachments.py
  tests/test_plan74_migrator_executor.py
  tests/test_plan74_migrator_verify.py
  tests/test_plan74_migrator_api.py
  tests/test_plan74_migrator_wiring.py
  tests/test_plan74_migrator_idempotency.py
  tests/test_plan74_migrator_readonly_origin.py
  tests/test_plan74_routes_registered.py
  tests/test_plan75_deep_links_compose.py
  tests/test_plan75_gitlab_provider_urls.py
  tests/test_plan75_deep_links_epic_fallback.py
  tests/test_plan75_deep_links_bidirectional.py
  tests/test_plan75_deep_links_wiring.py
  tests/test_plan75_deep_links_no_double_encode.py
  tests/test_plan76_codebase_memory_mcp.py
  tests/test_plan76_routes_registered.py
  tests/test_plan76_ratchet_byteidentical.py
  # — Plan 77 — Issue pipeline fases comentarios + color —
  tests/test_issue_phase_mapper.py
  tests/test_issue_phase_publisher.py
  tests/test_issue_no_children_guard.py
  tests/test_issue_phase_runtime_parity.py
  tests/test_harness_flags.py
  # — Plan 79 — Estados de tarea deterministas y configurables —
  tests/test_plan79_flag.py
  tests/test_plan79_resolver.py
  tests/test_plan79_safe_transition.py
  tests/test_plan79_apply_start.py
  tests/test_plan79_apply_final.py
  tests/test_plan79_centinela_estados.py
  tests/test_plan79_validate_states.py
  tests/test_plan79_agent_md_note.py
  tests/test_plan79_ratchet.py
  # — Plan 80 — Wiring real codebase-memory-mcp —
  tests/test_plan80_flags.py
  tests/test_plan80_wiring_pure.py
  tests/test_plan80_writer.py
  tests/test_plan80_codex.py
  tests/test_plan80_copilot.py
  tests/test_plan80_savings.py
  tests/test_plan80_status_shape.py
  tests/test_plan80_ratchet_byteidentical.py
  tests/test_plan80_routes_registered.py
  # — Plan 82 — Claridad de configuración del arnés (requires + profile_deltas) —
  tests/test_harness_flags_requires.py
  tests/test_harness_profile_deltas.py
  # — Plan 83 — Bounds declarativos para flags numéricas —
  tests/test_harness_flags_bounds.py
  # — Plan 84 — Hot-apply honesto: flags de startup (restart_required) —
  tests/test_harness_flags_restart_required.py
  tests/test_harness_flags_endpoint_restart.py
  # — Plan 85 — Cableado honesto: flags reservadas sin consumidor —
  tests/test_flag_wiring.py
  # — Plan 86 — Flags para mortales: ayuda en lenguaje llano —
  tests/test_harness_flags_help.py
  # — Plan 134 — Awareness total de runs: project/ticket_title en ejecuciones —
  tests/test_executions_ticket_context.py
  # — Plan 137 F0 — Documentador v2: flags + esqueleto de evidencia —
  tests/test_doc_evidence.py
  # — Plan 137 F3 — Documentador v2: pipeline short-circuit + persistencia —
  tests/test_documenter_v2_pipeline.py
  # — Plan 137 F4 — Documentador v2: endpoint historial de corridas —
  tests/test_plan137_endpoints.py
  # — Plan 142 — Centro de Costos + Codeburn: KPIs de tokens y USD —
  tests/test_cost_analytics_extract.py
  tests/test_cost_analytics_aggregate.py
  tests/test_cost_center_api.py
  tests/test_cost_reconciliation_audit.py
  tests/test_cost_codeburn_import.py
  # — Plan 158 — Centro de Costos: telemetria real claude_code_cli —
  tests/test_plan158_claude_cli_cost_parity.py
  # — Plan 144 — Ejecucion confiable Claude CLI: trust, stalls, estados —
  tests/test_status_vocabulary_contract.py
  tests/test_ticket_status_robust_transition.py
  tests/test_claude_workspace_trust.py
  tests/test_claude_trust_preflight.py
  tests/test_claude_stall_signal.py
  tests/test_execution_metadata_serialization.py
  tests/test_plan144_parity.py
  # — Plan 145 — Higiene y observabilidad de logs: 404, ANSI, dedup, pytest —
  tests/test_plan145_log_throttle.py
  tests/test_plan145_ansi_strip.py
  tests/test_plan145_pytest_log_isolation.py
  tests/test_plan145_pipeline_status_shim.py
  tests/test_plan145_agents_dir_dedup.py
  # — Plan 147 — Resolución robusta de rutas de proyecto + estado UI de watchers —
  tests/test_completion_preflight.py
  tests/test_watchers_health_check.py
  tests/test_diag_health_watchers.py
  # — Plan 148 — Degradación explícita de integraciones no configuradas (ADO/Jira/LLM) —
  tests/test_ado_connection_data_api_version.py
  tests/test_integration_breaker.py
  tests/test_plan148_integration_degradation.py
  tests/test_plan148_ado_sync_breaker.py
  tests/test_plan148_jira_sync_breaker.py
  tests/test_plan148_graceful_degradation.py
  tests/test_plan148_integrations_api.py

  # — Plan 149 — Robustez de intake de artefactos + excepciones tipadas en endpoints —
  tests/test_plan149_flags.py
  tests/test_plan149_typed_errors.py
  tests/test_plan149_intake_reason_codes.py
  tests/test_plan149_intake_quarantine_surface.py
  tests/test_plan149_prewrite_hook_message.py
  # — Plan 121 · Centinela local de egreso (secretos/PII semántico) —
  tests/test_plan121_egress_sentinel_flags.py
  tests/test_plan121_secret_patterns.py
  tests/test_plan121_sentinel_core.py
  tests/test_plan121_sentinel_sweep.py
  tests/test_plan121_sentinel_api.py
  # — Plan 127 · Reuso IA local: análisis de errores + doctor local DevOps —
  tests/test_plan127_flags.py
  tests/test_plan127_diag_snapshot.py
  tests/test_plan127_error_analysis_core.py
  tests/test_plan127_error_analysis_api.py
  tests/test_plan127_doctor_context.py
  tests/test_plan127_devops_doctor_local.py
  tests/test_plan127_ci_explain_local.py
  # — Plan 130 — Gate determinista de integridad de código pre-publicación —
  tests/test_plan130_code_integrity_flag.py
  tests/test_plan130_code_integrity_service.py
  tests/test_plan130_code_integrity_endpoint_cli.py
  # — Plan 131 — Resolutor de incidencias multimodal —
  tests/test_plan131_incident_flag.py
  tests/test_plan131_incident_store.py
  tests/test_plan131_incident_agent.py
  tests/test_plan131_incident_context.py
  tests/test_plan131_run_incident.py
  tests/test_plan131_incident_preview_publish.py
  tests/test_plan131_incident_docs.py
  tests/test_plan131_incident_api.py
  tests/test_incident_repair_guard.py
  # — Plan 133 — Contrato de inyección de contexto por agente —
  tests/test_context_contract_flags.py
  tests/test_run_ticket_refresh.py
  tests/test_business_preflight.py
  tests/test_ado_blocker_block.py
  tests/test_run_directive_block.py
  tests/test_agent_contract.py
  tests/test_block_priorities_contract.py
  # — Plan 166 — Ciclo completo de incidencias —
  tests/test_persist_incident_ticket.py
  tests/test_incident_vision.py
  tests/test_incident_autopublish.py
  tests/test_incident_dev_agent.py
  # — Plan 177 — Auto-PR del Dev Resolutor de incidencias —
  tests/test_plan177_ado_commit_web_url.py
  tests/test_incident_dev_diff.py
  tests/test_incident_dev_autocommit.py
  # — Fix deploy: index.html sin cache-control servia UI vieja tras rebuild —
  tests/test_spa_index_no_cache.py
  # ===== Plan 154 F1 · reclasificacion de tests sin gatear (verdes aislados) =====
  # — Plan 98 · Bootstrap DevOps + profile keys —
  tests/test_plan98_bootstrap_endpoint.py
  tests/test_plan98_bootstrap_flag.py
  tests/test_plan98_profile_key_patch.py
  tests/test_plan98_profile_key_validators.py
  # — Plan 122 · Comparador BD nucleo —
  tests/test_plan122_dbcompare_api.py
  tests/test_plan122_dbcompare_engine.py
  tests/test_plan122_dbcompare_flags.py
  tests/test_plan122_dbcompare_registry.py
  tests/test_plan122_dbcompare_snapshot.py
  # — Plan 123 · Comparador BD diff/runs —
  tests/test_plan123_dbcompare_api.py
  tests/test_plan123_dbcompare_diff.py
  tests/test_plan123_dbcompare_export.py
  tests/test_plan123_dbcompare_runs.py
  # — Plan 125 · Comparador BD scripts/emitters —
  tests/test_plan125_dbcompare_bundle.py
  tests/test_plan125_dbcompare_emitters_oracle.py
  tests/test_plan125_dbcompare_emitters_sqlserver.py
  tests/test_plan125_dbcompare_flatten.py
  tests/test_plan125_dbcompare_preflight.py
  tests/test_plan125_dbcompare_scripts_api.py
  tests/test_plan125_dbcompare_sqlnames.py
  tests/test_plan125_dbcompare_toposort.py
  # — Plan 126 · Comparador BD data diff —
  tests/test_plan126_dbcompare_data_api.py
  tests/test_plan126_dbcompare_data_diff.py
  tests/test_plan126_dbcompare_data_flags.py
  tests/test_plan126_dbcompare_data_scripts.py
  tests/test_plan126_dbcompare_sqlvalues.py
  # — Plan 157 · DB Compare UX (config in-place + import web.config + panel migracion) —
  tests/test_plan157_dbcompare_ux_flags.py
  tests/test_plan157_dbcompare_webconfig_parse.py
  tests/test_plan157_dbcompare_import_api.py
  tests/test_plan157_dbcompare_secret_guardrails.py
  # — Plan 139 · Shell v2 flag —
  tests/test_plan139_shell_flag.py
  # — Sueltos verdes aislados (reclasificados por Plan 154 F1) —
  tests/test_ado_client_stacky_name_resolution.py
  tests/test_local_llm_model_fallback_and_ticket_insight.py
  # — Plan 154 · Arnés veraz —
  tests/test_flags_env_read_meta.py
  tests/test_plan154_network_guard.py
  tests/test_output_watcher.py
  # — Plan 153 · Ledger publicacion —
  tests/test_publish_ledger.py
  tests/test_publish_idempotent_guard.py
  tests/test_epic_children_type_mapping.py
  tests/test_autopublish_rev_from_response.py
  # — Plan 156 · Latido unico —
  tests/test_executions_summary.py
  tests/test_access_log_suppress_pollers.py
  # — Plan 163 · Identidad de build y huellas —
  tests/test_app_version_build_identity.py
  tests/test_lifecycle_shutdown_log.py
  tests/test_error_fingerprints_catalog.py
  tests/test_error_fingerprints_scan.py
  # — Plan 167 · Centro de Evolucion —
  tests/test_evolution_flags.py
  tests/test_evolution_store.py
  tests/test_evolution_apply.py
  tests/test_evolution_cycle.py
  tests/test_evolution_endpoints.py
  # — Plan 168 · Arnes de fitness —
  tests/test_fitness_flags.py
  tests/test_fitness_case_store.py
  tests/test_fitness_runner.py
  tests/test_fitness_judge.py
  tests/test_fitness_service.py
  tests/test_fitness_endpoints.py
  # — Plan 169 · Optimizador evolutivo —
  tests/test_optimizer_flags.py
  tests/test_optimizer_store.py
  tests/test_optimizer_generator.py
  tests/test_optimizer_engine.py
  tests/test_optimizer_endpoints.py
  # — Plan 170 · Flywheel de conocimiento —
  tests/test_knowledge_flags.py
  tests/test_knowledge_store.py
  tests/test_knowledge_harvest.py
  tests/test_knowledge_injection.py
  tests/test_knowledge_eval_link.py
  tests/test_knowledge_endpoints.py
)

pass=0
fail=0
missing=0
declare -a failed_files=()

# Plan 130 [ADICION ARQUITECTO] — chequeo informativo de integridad de código.
# NO cambia pass/fail/exit: si un SyntaxError en un módulo compartido rompe la
# COLECCIÓN de pytest en decenas de archivos del arnés a la vez, esto señala la
# causa raíz real (file:line) en segundos, antes del loop principal.
echo "== Plan 130: integridad de codigo (informativo) =="
"$PYTHON" scripts/check_code_integrity.py || true
echo ""

for f in "${HARNESS_TEST_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "MISSING  $f"
    missing=$((missing + 1))
    failed_files+=("$f (missing)")
    continue
  fi
  if "$PYTHON" -m pytest "$f" -q >/tmp/harness_test_out 2>&1; then
    echo "PASS     $f"
    pass=$((pass + 1))
  else
    echo "FAIL     $f"
    tail -n 20 /tmp/harness_test_out
    fail=$((fail + 1))
    failed_files+=("$f")
  fi
done

echo ""
echo "===================== RESUMEN ARNÉS ====================="
echo "PASS=$pass  FAIL=$fail  MISSING=$missing  TOTAL=${#HARNESS_TEST_FILES[@]}"
if (( fail > 0 || missing > 0 )); then
  echo "Archivos con problema:"
  for ff in "${failed_files[@]}"; do echo "  - $ff"; done
  exit 1
fi
echo "Todos los archivos del arnés pasan aislados."
exit 0
