# Repo map: Stacky Agents
> **Mapa estructural auto-generado por repo_map.py, para CUALQUIER agente de codigo (Codex, GitHub Copilot, Claude, Cursor, Gemini, Aider...). No requiere prompt especial: leelo y ubicate.** Como usarlo: `Lenguajes` + `Carpetas` = la forma del proyecto; `Archivos clave` = que abrir primero. El mapa apunta al archivo; confirma con lectura/grep antes de afirmar y cita `archivo:linea`. Regenerar: `python repo_map.py "<repo>" --write`.
`N:\GIT\RS\STACKY\Stacky\Stacky Agents` | git=si | 1914 archivos | 661 de codigo | ~326,433 LOC

## Lenguajes
| Lenguaje | Archivos | ~LOC |
|---|---:|---:|
| (otros) | 1044 |  |
| TypeScript | 328 | 173,515 |
| Python | 310 | 96,208 |
| CSS | 85 |  |
| Markdown | 67 |  |
| JSON | 55 |  |
| PowerShell | 12 | 2,504 |
| JavaScript | 11 | 54,206 |
| YAML | 1 |  |
| HTML | 1 |  |

## Carpetas con mas codigo
- `vscode_extension/node_modules/typescript/lib` -- 111 archivos de codigo
- `backend/tests` -- 109 archivos de codigo
- `backend/services` -- 107 archivos de codigo
- `frontend/src/components` -- 75 archivos de codigo
- `vscode_extension/node_modules/@types/node` -- 47 archivos de codigo
- `backend/api` -- 38 archivos de codigo
- `vscode_extension/node_modules/undici-types` -- 38 archivos de codigo
- `backend` -- 13 archivos de codigo
- `backend/services/pm` -- 12 archivos de codigo
- `frontend/src/pages` -- 12 archivos de codigo
- `backend/agents` -- 10 archivos de codigo
- `backend/harness` -- 8 archivos de codigo
- `frontend/src/hooks` -- 8 archivos de codigo
- `deployment` -- 6 archivos de codigo
- `backend/evals` -- 5 archivos de codigo

## Archivos clave (top 40, rankeados por simbolos/entrypoint)

### `backend/app.py`  |  Python | 10 simbolos | 512 LOC
- fn `_startup_sync`  (L55)
- fn `_log_completion_preflight`  (L142)
- fn `create_app`  (L182)
- fn `_digest_loop`  (L369)
- fn `_memory_review_sweep_loop`  (L389)
- fn `_before_request`  (L411)
- fn `_after_request`  (L416)
- fn `_handle_unhandled_error`  (L448)
- fn `_serve_spa_index`  (L487)
- fn `_serve_spa_asset`  (L491)

### `backend/evals/__main__.py`  |  Python | 2 simbolos | 96 LOC
- fn `_print_results`  (L17)
- fn `main`  (L31)

### `backend/copilot_bridge.py`  |  Python | 12 simbolos | 723 LOC
- fn `_models_endpoint`  (L25)
- fn `_editor_headers`  (L30)
- fn `_get_copilot_token`  (L38)
- fn `_is_reasoning_model`  (L55)
- fn `list_copilot_models`  (L60)
- fn `BridgeResponse`  (L111)
- fn `cancel`  (L123)
- fn `_is_cancelled`  (L127)
- fn `invoke`  (L131)
- fn `_fallback_bridge_url`  (L167)
- fn `_bridge_target`  (L174)
- fn `_vscode_bridge_health`  (L226)

### `backend/log_streamer.py`  |  Python | 12 simbolos | 262 LOC
- fn `LogEvent`  (L22)
- fn `to_dict`  (L31)
- fn `_Buffer`  (L47)
- fn `open`  (L61)
- fn `push`  (L66)
- fn `logger_for`  (L96)
- fn `log`  (L97)
- fn `close`  (L109)
- fn `snapshot`  (L123)
- fn `stream`  (L134)
- fn `_get`  (L172)
- fn `flush`  (L177)

### `backend/models.py`  |  Python | 12 simbolos | 525 LOC
- fn `_json_dumps`  (L21)
- fn `_json_loads`  (L27)
- fn `Ticket`  (L38)
- fn `to_dict`  (L80)
- fn `User`  (L101)
- fn `to_dict`  (L118)
- fn `TicketStateHistory`  (L132)
- fn `to_dict`  (L159)
- fn `PackRun`  (L172)
- fn `options`  (L186)
- fn `options`  (L190)
- fn `to_dict`  (L193)

### `backend/project_manager.py`  |  Python | 12 simbolos | 629 LOC
- fn `get_all_projects`  (L39)
- fn `get_project_config`  (L55)
- fn `get_active_project`  (L65)
- fn `set_active_project`  (L85)
- fn `get_active_tracker_config`  (L90)
- fn `initialize_project`  (L105)
- fn `validate_workspace_root`  (L184)
- fn `validate_docs_paths`  (L203)
- fn `validate_agents_dir`  (L242)
- fn `initialize_ado_project`  (L270)
- fn `initialize_jira_project`  (L317)
- fn `get_project_pinned_agents`  (L371)

### `backend/runtime_paths.py`  |  Python | 12 simbolos | 222 LOC
- fn `is_frozen`  (L26)
- fn `backend_root`  (L30)
- fn `app_root`  (L36)
- fn `data_dir`  (L48)
- fn `projects_dir`  (L57)
- fn `_active_workspace_root`  (L66)
- fn `repo_root`  (L99)
- fn `frontend_dist_dir`  (L139)
- fn `stacky_home`  (L158)
- fn `stacky_agents_dir`  (L177)
- fn `ensure_stacky_home`  (L192)
- fn `ensure_stacky_agents_dir`  (L199)

### `deployment/Install-Dependencies.ps1`  |  PowerShell | 12 simbolos | 447 LOC
- fn `Write-Step`  (L42)
- fn `Write-OK`  (L48)
- fn `Write-Warn`  (L53)
- fn `Write-Fail`  (L58)
- fn `Update-ProcessPath`  (L63)
- fn `Invoke-CommandWithRetry`  (L79)
- fn `Install-WingetPackage`  (L117)
- fn `Get-PythonCandidate`  (L144)
- fn `Invoke-Python`  (L174)
- fn `Ensure-Python`  (L188)
- fn `Ensure-Node`  (L203)
- fn `Ensure-OptionalTools`  (L236)

### `deployment/Prepare-Publication.ps1`  |  PowerShell | 12 simbolos | 448 LOC
- fn `Write-Step`  (L40)
- fn `Write-OK`  (L46)
- fn `Write-Warn`  (L51)
- fn `Assert-ChildPath`  (L56)
- fn `Remove-SafeDirectory`  (L69)
- fn `Stop-DeployProcesses`  (L82)
- fn `Parse-Version`  (L103)
- fn `Compare-VersionObject`  (L116)
- fn `Get-CurrentDeployVersion`  (L123)
- fn `Get-DeployedPayloadVersion`  (L147)
- fn `Get-NextVersion`  (L177)
- fn `Test-CurrentDeployPayload`  (L199)

### `deployment/build_release.ps1`  |  PowerShell | 12 simbolos | 721 LOC
- fn `Write-Step`  (L33)
- fn `Write-OK`  (L34)
- fn `Write-Warn`  (L35)
- fn `Write-Utf8NoBom`  (L36)
- fn `Require-Command`  (L46)
- fn `Resolve-Python`  (L57)
- fn `Invoke-BuildPython`  (L83)
- fn `Resolve-SignTool`  (L90)
- fn `Invoke-AuthenticodeSignature`  (L120)
- fn `Assert-CleanReleasePayload`  (L167)
- fn `Resolve-StackyAgentsSource`  (L191)
- fn `Get-AgentName`  (L207)

### `backend/api/adoption.py`  |  Python | 12 simbolos | 817 LOC
- fn `_iso`  (L31)
- fn `_resolve_user`  (L35)
- fn `_user_matches`  (L40)
- fn `_serialize_ticket`  (L50)
- fn `session_resume`  (L79)
- fn `savings_weekly`  (L147)
- fn `_calibrate_baseline`  (L220)
- fn `standup_daily`  (L271)
- fn `fmt_ticket`  (L337)
- fn `_is_business_day`  (L390)
- fn `streak`  (L395)
- fn `_project_cap_path`  (L499)

### `backend/api/agents.py`  |  Python | 12 simbolos | 1042 LOC
- fn `list_agents_route`  (L29)
- fn `validate_artifact_route`  (L34)
- fn `list_vscode_agents`  (L58)
- fn `stacky_manifest`  (L65)
- fn `stacky_materialize`  (L97)
- fn `stacky_import_agent`  (L120)
- fn `vscode_agent_history`  (L227)
- fn `_validate_agent_filename`  (L283)
- fn `agent_prompt_versions`  (L291)
- fn `agent_prompt_version_diff`  (L302)
- fn `advise_runtime`  (L319)
- fn `run`  (L340)

### `backend/api/diag.py`  |  Python | 12 simbolos | 549 LOC
- fn `diagnose_execution`  (L39)
- fn `output_watcher_scan_now`  (L126)
- fn `output_watcher_stats`  (L155)
- fn `metrics`  (L180)
- fn `health`  (L281)
- fn `local_diagnostics`  (L364)
- fn `git_pull_check`  (L372)
- fn `run_db_backup`  (L404)
- fn `export_local_logs`  (L412)
- fn `_percentiles`  (L428)
- fn `at`  (L434)
- fn `_classify_recovery_reason`  (L447)

### `backend/api/executions.py`  |  Python | 12 simbolos | 487 LOC
- fn `list_executions`  (L27)
- fn `get_execution`  (L78)
- fn `get_logs`  (L87)
- fn `send_execution_input`  (L92)
- fn `stream_logs`  (L121)
- fn `generator`  (L122)
- fn `approve`  (L140)
- fn `discard`  (L145)
- fn `_set_verdict`  (L149)
- fn `publish_to_ado`  (L172)
- fn `diff`  (L193)
- fn `cancel_execution`  (L208)

### `backend/api/global_config.py`  |  Python | 12 simbolos | 878 LOC
- fn `_read_env`  (L90)
- fn `_write_env`  (L105)
- fn `get_global_config`  (L141)
- fn `put_global_config`  (L160)
- fn `test_global_tracker_connection`  (L184)
- fn `_merge`  (L196)
- fn `test_codex_connection`  (L293)
- fn `_dlog`  (L306)
- fn `codex_oauth_login`  (L389)
- fn `get_codex_session_status`  (L460)
- fn `delete_codex_session`  (L572)
- fn `_resolve_claude_bin`  (L645)

### `backend/api/memory.py`  |  Python | 12 simbolos | 463 LOC
- fn `_validate_applies_to`  (L19)
- fn `_is_nonempty_targeting`  (L42)
- fn `list_route`  (L47)
- fn `create_route`  (L61)
- fn `search_route`  (L126)
- fn `context_preview_route`  (L142)
- fn `status_route`  (L157)
- fn `start_validation_run_route`  (L170)
- fn `list_validation_runs_route`  (L184)
- fn `get_validation_run_route`  (L194)
- fn `list_validation_findings_route`  (L202)
- fn `get_validation_finding_route`  (L217)

### `backend/api/phase5.py`  |  Python | 12 simbolos | 251 LOC
- fn `speculate`  (L23)
- fn `get_spec`  (L40)
- fn `cancel_spec`  (L48)
- fn `claim_spec`  (L54)
- fn `critique`  (L68)
- fn `noop`  (L86)
- fn `verify_audit_chain`  (L99)
- fn `seal_audit`  (L105)
- fn `erase_pii`  (L115)
- fn `list_constraints`  (L153)
- fn `create_constraint`  (L159)
- fn `deactivate_constraint`  (L177)

### `backend/api/phase6.py`  |  Python | 12 simbolos | 330 LOC
- fn `list_egress`  (L30)
- fn `create_egress`  (L36)
- fn `delete_egress`  (L51)
- fn `check_egress`  (L58)
- fn `refine_endpoint`  (L71)
- fn `explore_endpoint`  (L91)
- fn `list_macros_route`  (L106)
- fn `create_macro_route`  (L112)
- fn `delete_macro_route`  (L129)
- fn `run_macro_route`  (L136)
- fn `ci_webhook`  (L153)
- fn `pr_review_webhook`  (L204)

### `backend/api/pm.py`  |  Python | 12 simbolos | 1301 LOC
- fn `_resolve_project`  (L57)
- fn `_ado_only_error`  (L67)
- fn `_new_client`  (L76)
- fn `sync_ado`  (L86)
- fn `sprint_current`  (L280)
- fn `sprint_history`  (L324)
- fn `list_risks`  (L365)
- fn `acknowledge_risk`  (L411)
- fn `list_comments`  (L464)
- fn `index_comments`  (L508)
- fn `_is_premium_hint`  (L611)
- fn `list_ai_models`  (L617)

### `backend/api/projects.py`  |  Python | 12 simbolos | 947 LOC
- fn `_has_credentials`  (L69)
- fn `_project_to_dict`  (L80)
- fn `_resolve_workspace_root`  (L112)
- fn `_resolve_text_field`  (L120)
- fn `_resolve_docs_paths`  (L127)
- fn `_resolve_agents_dir`  (L160)
- fn `_count_docs_files`  (L168)
- fn `list_projects`  (L199)
- fn `get_active`  (L211)
- fn `set_active`  (L224)
- fn `init_project`  (L243)
- fn `get_project`  (L374)

### `backend/api/qa_browser.py`  |  Python | 12 simbolos | 710 LOC
- fn `create_run`  (L40)
- fn `get_run_spec`  (L201)
- fn `push_event`  (L211)
- fn `add_evidence`  (L258)
- fn `complete_run`  (L285)
- fn `_qa_browser_evidence_dir`  (L414)
- fn `_write_stacky_comment_artifacts`  (L418)
- fn `_prepare_result_evidence_for_stacky`  (L474)
- fn `_evidence_local_image_path`  (L527)
- fn `_evidence_label`  (L565)
- fn `_safe_file_part`  (L571)
- fn `_resolve_ticket`  (L576)

### `backend/api/qa_uat.py`  |  Python | 12 simbolos | 1874 LOC
- fn `_utcnow_iso`  (L53)
- fn `_ensure_pipeline_on_path`  (L66)
- fn `run_pipeline`  (L76)
- fn `get_run_result`  (L177)
- fn `_run_pipeline_in_background`  (L203)
- fn `get_lanes`  (L338)
- fn `get_portfolio`  (L387)
- fn `get_dashboard`  (L429)
- fn `check_run_publish_policy`  (L462)
- fn `budget_check`  (L508)
- fn `list_quarantine`  (L563)
- fn `add_quarantine`  (L599)

### `backend/api/tickets.py`  |  Python | 12 simbolos | 5372 LOC
- fn `_payload_logical_sha256`  (L70)
- fn `_repo_root`  (L87)
- fn `_resolve_repo_root`  (L100)
- fn `_body_json`  (L112)
- fn `_artifact_root_override_from_request`  (L117)
- fn `_resolve_artifact_repo_root`  (L137)
- fn `_artifact_scan_roots`  (L187)
- fn `_watcher_snapshot`  (L199)
- fn `_write_manual_finish_html`  (L217)
- fn `_pending_task_preflight_for_finish`  (L236)
- fn `_request_project_name`  (L273)
- fn `_ado_sync_error_response`  (L284)

### `backend/services/ado_client.py`  |  Python | 12 simbolos | 892 LOC
- fn `AdoConfigError`  (L53)
- fn `AdoApiError`  (L57)
- fn `__init__`  (L60)
- fn `_is_signin_html`  (L78)
- fn `_looks_preencoded`  (L88)
- fn `_read_pat_file`  (L92)
- fn `_resolve_active_project_defaults`  (L116)
- fn `_resolve_auth_header`  (L159)
- fn `ado_pat_present`  (L186)
- fn `AdoClient`  (L222)
- fn `__init__`  (L223)
- fn `_headers`  (L245)

### `backend/services/ado_context.py`  |  Python | 12 simbolos | 380 LOC
- fn `_env_csv`  (L101)
- fn `_env_int`  (L108)
- fn `is_enrichment_enabled`  (L119)
- fn `_html_to_text`  (L131)
- fn `_S`  (L138)
- fn `__init__`  (L139)
- fn `handle_data`  (L143)
- fn `handle_starttag`  (L147)
- fn `handle_endtag`  (L151)
- fn `_guess_mime`  (L163)
- fn `_format_size`  (L175)
- fn `build_ado_context_blocks`  (L185)

### `backend/services/ado_pipeline_inference.py`  |  Python | 12 simbolos | 434 LOC
- fn `PipelineInferenceCache`  (L69)
- fn `is_fresh`  (L80)
- fn `to_result`  (L84)
- fn `StageInference`  (L93)
- fn `__init__`  (L94)
- fn `to_dict`  (L100)
- fn `PipelineInferenceResult`  (L109)
- fn `__init__`  (L110)
- fn `to_dict`  (L130)
- fn `_HTMLStripper`  (L147)
- fn `__init__`  (L148)
- fn `handle_data`  (L152)

### `backend/services/ado_publisher.py`  |  Python | 12 simbolos | 910 LOC
- fn `_render_run_footer`  (L52)
- fn `_get_ado_publish_lock`  (L106)
- fn `AgentHtmlPublish`  (L119)
- fn `to_dict`  (L167)
- fn `PublishResult`  (L188)
- fn `AttachmentPublishError`  (L202)
- fn `publish_from_execution`  (L209)
- fn `ado_publish_post_hook`  (L511)
- fn `_increment_idempotent_replay_counter`  (L550)
- fn `_default_client`  (L573)
- fn `_client_for_ticket_project`  (L579)
- fn `_stacky_comment_marker`  (L615)

### `backend/services/ado_sync.py`  |  Python | 12 simbolos | 423 LOC
- fn `_HtmlStripper`  (L23)
- fn `__init__`  (L24)
- fn `handle_data`  (L28)
- fn `handle_starttag`  (L32)
- fn `handle_endtag`  (L36)
- fn `_html_to_text`  (L41)
- fn `_parse_iso`  (L53)
- fn `_extract_assignee`  (L62)
- fn `_legacy_ticket_match`  (L82)
- fn `_client_project_metadata`  (L93)
- fn `sync_tickets`  (L102)
- fn `upsert_single_work_item`  (L235)

### `backend/services/ado_write_outbox.py`  |  Python | 12 simbolos | 508 LOC
- fn `_now`  (L73)
- fn `_json_dumps`  (L77)
- fn `_json_loads`  (L83)
- fn `AdoWriteOperation`  (L95)
- fn `payload`  (L150)
- fn `payload`  (L154)
- fn `ado_request`  (L158)
- fn `ado_response`  (L162)
- fn `is_open`  (L165)
- fn `to_dict`  (L168)
- fn `compute_backoff_seconds`  (L199)
- fn `enqueue`  (L210)

### `backend/services/agent_completion.py`  |  Python | 12 simbolos | 1385 LOC
- fn `CompletionMetadata`  (L53)
- fn `from_dict`  (L59)
- fn `to_dict`  (L66)
- fn `CompletionPayload`  (L71)
- fn `from_dict`  (L83)
- fn `GatewayError`  (L107)
- fn `to_dict`  (L113)
- fn `ClosurePlanStep`  (L118)
- fn `to_dict`  (L124)
- fn `GatewayResult`  (L133)
- fn `to_dict`  (L150)
- fn `_compute_sha256`  (L171)

### `backend/services/agent_completion_internal.py`  |  Python | 12 simbolos | 674 LOC
- fn `_utc_now_iso`  (L36)
- fn `CloseResult`  (L41)
- fn `to_dict`  (L53)
- fn `close_execution_with_publish`  (L66)
- fn `_infer_agent_type_from_filename`  (L304)
- fn `_resolve_transition_state_from_config`  (L321)
- fn `_should_auto_publish`  (L389)
- fn `_resolve_publish_mode`  (L400)
- fn `_set_publish_hold`  (L419)
- fn `publish_execution_from_review`  (L434)
- fn `_attempt_state_change`  (L502)
- fn `_r13_check_publish_guard`  (L556)

### `backend/services/artifact_validator.py`  |  Python | 12 simbolos | 321 LOC
- fn `_required_fields`  (L44)
- fn `_allowed_statuses`  (L52)
- fn `_ticket_exists`  (L60)
- fn `ArtifactValidation`  (L80)
- fn `to_dict`  (L87)
- fn `ArtifactReport`  (L98)
- fn `checked`  (L104)
- fn `invalid`  (L108)
- fn `ok`  (L112)
- fn `to_dict`  (L115)
- fn `_epic_id_from_path`  (L127)
- fn `validate_pending_task_file`  (L136)

### `backend/services/claude_code_cli_runner.py`  |  Python | 12 simbolos | 2317 LOC
- fn `_notify_outcome`  (L77)
- fn `start_claude_code_cli_run`  (L100)
- fn `cancel`  (L184)
- fn `_grace_watch`  (L202)
- fn `_user_message_line`  (L221)
- fn `send_input`  (L237)
- fn `_send_system_message`  (L275)
- fn `_run_in_background`  (L307)
- fn `log`  (L317)
- fn `_heartbeat_loop`  (L706)
- fn `_on_stream_event`  (L760)
- fn `_claude_repair_send`  (L1079)

### `backend/services/client_profile.py`  |  Python | 12 simbolos | 467 LOC
- fn `ClientProfileError`  (L66)
- fn `ValidationResult`  (L71)
- fn `to_dict`  (L77)
- fn `_read_default_template`  (L88)
- fn `get_default_client_profile`  (L119)
- fn `_check_section_type`  (L135)
- fn `_check_tracker_state_machine`  (L144)
- fn `_contains_secret_keys`  (L167)
- fn `_walk`  (L171)
- fn `validate_client_profile`  (L185)
- fn `_read_project_config_raw`  (L247)
- fn `load_client_profile`  (L266)

### `backend/services/codex_cli_runner.py`  |  Python | 12 simbolos | 1891 LOC
- fn `_push`  (L48)
- fn `_notify_outcome`  (L67)
- fn `start_codex_cli_run`  (L86)
- fn `cancel`  (L166)
- fn `send_input`  (L181)
- fn `_run_in_background`  (L236)
- fn `log`  (L246)
- fn `_heartbeat_loop`  (L493)
- fn `_codex_on_runaway`  (L537)
- fn `_codex_on_runaway_with_stall`  (L582)
- fn `_do_resume`  (L756)
- fn `_codex_repair_send`  (L842)

### `backend/services/config_transfer.py`  |  Python | 12 simbolos | 907 LOC
- fn `_app_version`  (L96)
- fn `ConfigTransferError`  (L116)
- fn `_canonical_json`  (L122)
- fn `compute_checksum`  (L126)
- fn `_project_dir`  (L138)
- fn `_load_project_config`  (L142)
- fn `_load_project_config_optional`  (L151)
- fn `_strip_secrets`  (L157)
- fn `_detect_secret_keys`  (L170)
- fn `_walk`  (L174)
- fn `_scan_secrets_ref`  (L188)
- fn `_write_project_config`  (L212)

### `backend/services/context_enrichment.py`  |  Python | 12 simbolos | 1167 LOC
- fn `_noop_log`  (L30)
- fn `enrich_blocks`  (L34)
- fn `_run_sim`  (L91)
- fn `_run_ado`  (L96)
- fn `_normalize_line`  (L204)
- fn `_dedup_blocks`  (L209)
- fn `_block_priority`  (L338)
- fn `_block_token_estimate`  (L342)
- fn `_apply_context_budget`  (L353)
- fn `_sort_key`  (L418)
- fn `build_client_profile_block`  (L478)
- fn `_inject_client_profile_block`  (L575)

### `backend/services/doc_indexer.py`  |  Python | 12 simbolos | 657 LOC
- fn `_anchor`  (L67)
- fn `_extract_headings`  (L72)
- fn `_should_exclude`  (L89)
- fn `_is_relative_to`  (L99)
- fn `_normalize_relative_path`  (L108)
- fn `_cache_get`  (L121)
- fn `_cache_set`  (L133)
- fn `_make_node`  (L138)
- fn `_make_folder_node`  (L163)
- fn `_sort_tree`  (L178)
- fn `_insert_file_node`  (L185)
- fn `_index_markdown_tree`  (L218)

### `backend/services/docs_rag.py`  |  Python | 12 simbolos | 366 LOC
- fn `_tokenize`  (L44)
- fn `_compute_tf`  (L49)
- fn `DocChunk`  (L62)
- fn `_split_markdown_to_chunks`  (L86)
- fn `index_project`  (L138)
- fn `_IdfCache`  (L200)
- fn `_get_idf`  (L209)
- fn `_invalidate_idf`  (L233)
- fn `DocHit`  (L242)
- fn `to_dict`  (L248)
- fn `search`  (L257)
- fn `get_stats`  (L354)

### `backend/services/flow_config_store.py`  |  Python | 12 simbolos | 372 LOC
- fn `DuplicateStateError`  (L68)
- fn `__init__`  (L69)
- fn `RuleNotFoundError`  (L74)
- fn `__init__`  (L75)
- fn `ValidationError`  (L80)
- fn `_now_iso`  (L87)
- fn `_normalize_project_name`  (L91)
- fn `_config_file_for`  (L96)
- fn `_legacy_fallback_file_for`  (L111)
- fn `_empty_config`  (L120)
- fn `_read_json_file`  (L124)
- fn `_read_raw`  (L132)

> Generado por repo_map.py. El mapa apunta al archivo; confirma con lectura/grep antes de afirmar. Extraccion por regex (best-effort), no parser exacto.
