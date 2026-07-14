-- Migration 014: index targeted external operations for business-intent locking.
-- Runtime code locks xianyu_goods first, then reads the latest attempt for the
-- same operation type and local target.  This prevents a different browser
-- idempotency key from bypassing an active or ambiguous publish intent.

SET NAMES utf8mb4;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'external_operation_attempt'
      AND index_name = 'idx_external_operation_target_created'
  ),
  'SELECT 1',
  'ALTER TABLE `external_operation_attempt` ADD INDEX `idx_external_operation_target_created` (`operation_type`, `target_local_id`, `created_time`, `id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
