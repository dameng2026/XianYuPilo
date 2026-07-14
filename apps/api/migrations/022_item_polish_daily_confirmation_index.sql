-- Migration 022: cover same-day confirmed item-polish target lookups.
-- Runtime filters by account, external platform item, terminal status, and
-- confirmation time. Guard the forward-only index build for safe reruns after
-- a partially completed MySQL DDL operation.

SET NAMES utf8mb4;

SET @ddl = IF(
  EXISTS(
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'item_polish_task_item'
      AND index_name = 'idx_item_polish_item_daily_confirmation'
  ),
  'SELECT 1',
  'ALTER TABLE `item_polish_task_item` ADD INDEX `idx_item_polish_item_daily_confirmation` (`account_id`, `external_goods_id`, `status`, `remote_confirmed_at`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
