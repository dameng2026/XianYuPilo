-- Migration 032: 为 delivery_text_source 增加卡密发货模式支持
-- 同步商业版功能：货源库支持文本/卡密两种发货模式
--
-- 业务规则：
--   1. delivery_mode='text'：文本发货，content 字段为实际发货文本
--   2. delivery_mode='card'：卡密发货，content 字段需包含 {卡密占位}，
--      发货时从 card_group_id 指定的卡密分组中认领一张卡密替换占位符
--
-- 新增字段：
--   source_type: 货源类型（保留字段，默认 'text'，与商业版对齐）
--   delivery_mode: 发货模式（'text' 文本 / 'card' 卡密，默认 'text'）
--   card_group_id: 卡密分组 ID（delivery_mode='card' 时关联 card_group.id）

SET NAMES utf8mb4;

-- source_type 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'delivery_text_source'
      AND column_name = 'source_type'),
  'SELECT 1',
  'ALTER TABLE `delivery_text_source` ADD COLUMN `source_type` VARCHAR(50) NOT NULL DEFAULT ''text'' COMMENT ''货源类型（保留字段，默认 text）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- delivery_mode 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'delivery_text_source'
      AND column_name = 'delivery_mode'),
  'SELECT 1',
  'ALTER TABLE `delivery_text_source` ADD COLUMN `delivery_mode` VARCHAR(20) NOT NULL DEFAULT ''text'' COMMENT ''发货模式 text 文本 / card 卡密'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- card_group_id 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'delivery_text_source'
      AND column_name = 'card_group_id'),
  'SELECT 1',
  'ALTER TABLE `delivery_text_source` ADD COLUMN `card_group_id` BIGINT NULL COMMENT ''卡密分组 ID（delivery_mode=card 时关联 card_group.id）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 索引：按 delivery_mode 过滤
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'delivery_text_source'
      AND index_name = 'idx_delivery_text_source_mode'),
  'SELECT 1',
  'CREATE INDEX `idx_delivery_text_source_mode` ON `delivery_text_source` (`delivery_mode`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
