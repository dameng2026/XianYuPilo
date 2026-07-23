-- Migration 034: 闲鱼消息表
-- 补建 xianyu_message 表（模型已存在于 entities.py，但之前缺少建表迁移）。
-- 该表用于存储 AI 自动回复消息记录，会话列表加载 AI 回复上下文时依赖此表。
-- 使用 CREATE TABLE IF NOT EXISTS，对已有数据库安全（幂等）。

CREATE TABLE IF NOT EXISTS `xianyu_message` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `conversation_id` BIGINT NULL COMMENT '关联xianyu_conversation.id',
  `session_id` VARCHAR(200) NULL COMMENT '会话session ID，用于关联xianyu_chat_message.s_id',
  `from_user_id` VARCHAR(200) NULL,
  `to_user_id` VARCHAR(200) NULL,
  `content` TEXT NULL,
  `message_type` VARCHAR(50) NULL DEFAULT 'text' COMMENT 'text/image/card',
  `direction` VARCHAR(20) NULL DEFAULT 'received' COMMENT 'sent/received',
  `is_auto_reply` SMALLINT NULL DEFAULT 0 COMMENT '0否 1是',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_message_account` (`account_id`, `deleted`),
  INDEX `idx_message_conversation` (`conversation_id`),
  INDEX `idx_message_auto_reply` (`account_id`, `is_auto_reply`, `deleted`),
  INDEX `idx_message_to_user` (`to_user_id`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼消息表（AI自动回复记录）';
