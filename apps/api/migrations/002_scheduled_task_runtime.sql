-- Migration 002: reliable scheduled-task execution state and finite leases.
-- MySQL 8.0. This script is idempotent so an operator can safely verify/re-run
-- it while recovering an installation whose migration history is uncertain.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `schema_migration` (
  `version` VARCHAR(64) NOT NULL,
  `description` VARCHAR(255) NOT NULL,
  `checksum` CHAR(64) NULL,
  `applied_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='已应用数据库迁移';

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task' AND column_name = 'last_status'
  ),
  'SELECT 1',
  'ALTER TABLE `scheduled_task` ADD COLUMN `last_status` VARCHAR(32) NULL COMMENT ''最近执行状态'' AFTER `next_run_time`'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task' AND column_name = 'last_result'
  ),
  'SELECT 1',
  'ALTER TABLE `scheduled_task` ADD COLUMN `last_result` JSON NULL COMMENT ''最近执行结果（已脱敏）'' AFTER `last_status`'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task' AND column_name = 'lease_token'
  ),
  'SELECT 1',
  'ALTER TABLE `scheduled_task` ADD COLUMN `lease_token` VARCHAR(64) NULL COMMENT ''执行租约令牌'' AFTER `last_result`'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task' AND column_name = 'lease_until'
  ),
  'SELECT 1',
  'ALTER TABLE `scheduled_task` ADD COLUMN `lease_until` DATETIME NULL COMMENT ''租约到期时间'' AFTER `lease_token`'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task' AND column_name = 'lease_owner'
  ),
  'SELECT 1',
  'ALTER TABLE `scheduled_task` ADD COLUMN `lease_owner` VARCHAR(128) NULL COMMENT ''持有租约的 worker'' AFTER `lease_until`'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'scheduled_task'
      AND index_name = 'idx_scheduled_task_due_lease'
  ),
  'SELECT 1',
  'CREATE INDEX `idx_scheduled_task_due_lease` ON `scheduled_task` (`status`, `deleted`, `next_run_time`, `lease_until`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- Version history is written by ``python -m app.migrations upgrade`` only
-- after every statement above succeeds.
