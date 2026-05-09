/* QA_UAT_SEED_PROPOSAL — Ticket: 70, Scenario: P05 */
/* Generated: 2026-05-09T19:11:05.266398Z */
/* IMPORTANT: Review and verify ALL statements before un-commenting COMMIT. */
/* Default mode: ROLLBACK — no data will be persisted until COMMIT is un-commented. */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = 'seed-70-34004FE0F5B6';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

-- ── Anti-PROD guard ────────────────────────────────────────────────────────
IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'
BEGIN
    RAISERROR('QA_UAT_SEED_BLOCKED: This script must NOT run on production. DB=%s', 20, 1, DB_NAME()) WITH LOG;
    ROLLBACK TRANSACTION;
    RETURN;
END;

-- ── Seed: Lote (alias: lote_asignado) ─────────────────────────────────
-- Schema source: contract
-- TODO: verify table name and column names against actual schema
-- Constraint: lote existe en RAGEN
-- Constraint: lote tiene perfil asignado

-- Idempotent INSERT: skips if record already exists with @SeedRunId marker
IF NOT EXISTS (
    SELECT 1 FROM RAGEN
    WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy
)
BEGIN
    INSERT INTO RAGEN (
        AGLOTE, CreatedBy, SeedRunId, CreatedAt
    ) VALUES (
        <TODO: AGLOTE_value>, @CreatedBy, @SeedRunId, GETUTCDATE()
    );
END;

-- ── Seed: GestionAgenda (alias: gestion_en_agenda) ─────────────────────────────────
-- Schema source: contract
-- TODO: verify table name and column names against actual schema
-- Constraint: existe al menos una gestion asignada al agente QA

-- Idempotent INSERT: skips if record already exists with @SeedRunId marker
IF NOT EXISTS (
    SELECT 1 FROM RAGEN
    WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy
)
BEGIN
    INSERT INTO RAGEN (
        AGPERFIL, AGLOTE, CreatedBy, SeedRunId, CreatedAt
    ) VALUES (
        <TODO: AGPERFIL_value>, <TODO: AGLOTE_value>, @CreatedBy, @SeedRunId, GETUTCDATE()
    );
END;

-- ── Verification SELECT ────────────────────────────────────────────────────
-- Verify the seed data was inserted correctly before committing.
SELECT * FROM RAGEN
WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;

SELECT * FROM RAGEN
WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;

-- ── Transaction control ────────────────────────────────────────────────────
-- DEFAULT: ROLLBACK — no data will be persisted.
-- To apply the seed: review all statements above, then:
--   1. Change ROLLBACK to COMMIT below.
--   2. Obtain human operator approval.
--   3. Execute in a QA/DEV environment only.
ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment ONLY after human review and approval
