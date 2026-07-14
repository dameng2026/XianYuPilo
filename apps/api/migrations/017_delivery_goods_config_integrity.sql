-- Migration 017: enforce the delivery configuration -> goods relationship.
--
-- This migration deliberately performs no orphan cleanup. If legacy rows refer
-- to missing goods, ADD CONSTRAINT fails and the deployment remains stopped at
-- the migration gate. Reconcile those rows from a verified backup/change plan,
-- then rerun the migration. Silently deleting business configuration is unsafe.

SET NAMES utf8mb4;

SET @ddl = IF(
  EXISTS(
    SELECT 1
    FROM information_schema.referential_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'delivery_goods_config'
      AND constraint_name = 'fk_delivery_goods_config_goods'
  ),
  'SELECT 1',
  'ALTER TABLE `delivery_goods_config` ADD CONSTRAINT `fk_delivery_goods_config_goods` FOREIGN KEY (`goods_id`) REFERENCES `xianyu_goods` (`id`) ON UPDATE RESTRICT ON DELETE RESTRICT'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
