-- Migration 031: 会话级自动回复状态机
-- 同步商业版功能：人工干预自动暂停/手动关闭/自动恢复
--
-- 业务规则：
--   1. 人工发送消息后，会话级 auto_reply_paused=1（人工干预暂停）
--   2. 买家发送"开启自动回复"指令 → 自动恢复（仅当未被用户手动关闭）
--   3. 距上次人工回复 > 1 分钟，买家发新消息时自动恢复
--   4. 用户在网站手动点击按钮关闭时，auto_reply_manual_disabled=1，
--      禁止自动恢复，仅允许用户手动开启
--
-- 新增字段：
--   auto_reply_paused: 会话级是否暂停（0否 1是）
--   auto_reply_manual_disabled: 是否被用户手动关闭（0否 1是，禁止自动恢复）
--   last_manual_reply_at: 最后人工回复时间戳（毫秒，BIGINT）
--   last_auto_reply_at: 最后 AI 自动回复时间戳（毫秒，BIGINT）

SET NAMES utf8mb4;

-- auto_reply_paused 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 'auto_reply_paused'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `auto_reply_paused` SMALLINT NOT NULL DEFAULT 0 COMMENT ''会话级自动回复是否暂停 0否 1是（人工干预或手动关闭触发）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- auto_reply_manual_disabled 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 'auto_reply_manual_disabled'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `auto_reply_manual_disabled` SMALLINT NOT NULL DEFAULT 0 COMMENT ''是否被用户手动关闭 0否 1是（1时不允许自动恢复，仅手动开启）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- last_manual_reply_at 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 'last_manual_reply_at'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `last_manual_reply_at` BIGINT NULL COMMENT ''最后一次人工回复时间戳（毫秒，用于1分钟自动恢复判断）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- last_auto_reply_at 列
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 'last_auto_reply_at'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `last_auto_reply_at` BIGINT NULL COMMENT ''最后一次 AI 自动回复时间戳（毫秒）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
