/* QA_UAT_CLEANUP_PROPOSAL — Ticket: 70, Scenario: P06 */
/* Seed run: seed-70-672A8DF0A1F3 */
/* Generated: 2026-05-09T19:47:04.232031Z */
/* IMPORTANT: This script ONLY deletes rows tagged with SeedRunId='seed-70-672A8DF0A1F3'. */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = 'seed-70-672A8DF0A1F3';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

-- ── Anti-PROD guard ────────────────────────────────────────────────────────
IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'
BEGIN
    RAISERROR('QA_UAT_CLEANUP_BLOCKED: This script must NOT run on production.', 20, 1) WITH LOG;
    ROLLBACK TRANSACTION;
    RETURN;
END;

-- Cleanup: Lote (alias: lote_asignado)
DELETE FROM RAGEN
WHERE CreatedBy = @CreatedBy AND SeedRunId = @SeedRunId;

-- Cleanup: GestionAgenda (alias: gestion_en_agenda)
DELETE FROM RAGEN
WHERE CreatedBy = @CreatedBy AND SeedRunId = @SeedRunId;

-- ── Post-cleanup verification SELECT ───────────────────────────────────────
SELECT COUNT(*) AS RemainingRows FROM RAGEN
WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;
-- Expected result: 0 rows

SELECT COUNT(*) AS RemainingRows FROM RAGEN
WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;
-- Expected result: 0 rows

ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment ONLY after human review and approval
