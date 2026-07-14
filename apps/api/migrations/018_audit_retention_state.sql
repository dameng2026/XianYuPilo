-- Migration 018: durable coordination for bounded audit-log retention.

SET NAMES utf8mb4;

-- Bounded deletion must not degrade into a full operation_log scan as the
-- audit trail grows. MySQL 8.0 has no portable CREATE INDEX IF NOT EXISTS, so
-- guard the forward-only DDL through information_schema.
SET @ddl = IF(
  EXISTS(
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'operation_log'
      AND index_name = 'idx_operation_log_created_time'
  ),
  'SELECT 1',
  'ALTER TABLE `operation_log` ADD INDEX `idx_operation_log_created_time` (`created_time`, `id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

CREATE TABLE IF NOT EXISTS `audit_retention_state` (
  `id` SMALLINT NOT NULL,
  `last_run_at` DATETIME NULL,
  `next_run_at` DATETIME NULL,
  `last_deleted_count` INT NOT NULL DEFAULT 0,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Singleton coordination state for bounded operation-log retention';

INSERT IGNORE INTO `audit_retention_state`(
  `id`, `last_run_at`, `next_run_at`, `last_deleted_count`, `updated_time`
) VALUES(1, NULL, NULL, 0, NOW());
