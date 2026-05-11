/* QA_UAT_CLEANUP_PROPOSAL — Ticket: 120, Scenario: P08 */
/* Seed run: seed-120-1810F1048169 */
/* Generated: 2026-05-10T01:48:33.624986Z */
/* IMPORTANT: This script ONLY deletes rows tagged with SeedRunId='seed-120-1810F1048169'. */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = 'seed-120-1810F1048169';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

-- ── Anti-PROD guard ────────────────────────────────────────────────────────
IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'
BEGIN
    RAISERROR('QA_UAT_CLEANUP_BLOCKED: This script must NOT run on production.', 20, 1) WITH LOG;
    ROLLBACK TRANSACTION;
    RETURN;
END;

-- Cleanup: Cliente (alias: cliente_existente)
DELETE FROM RCLIE
WHERE CreatedBy = @CreatedBy AND SeedRunId = @SeedRunId;

-- ── Post-cleanup verification SELECT ───────────────────────────────────────
SELECT COUNT(*) AS RemainingRows FROM RCLIE
WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;
-- Expected result: 0 rows

ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment ONLY after human review and approval
