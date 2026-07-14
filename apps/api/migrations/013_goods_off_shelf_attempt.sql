-- Migration 013: durable, idempotent platform off-shelf attempts.
-- This migration records workflow state only; it never calls the platform and
-- does not alter the current state of any existing goods row.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `goods_off_shelf_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `goods_id` BIGINT NOT NULL COMMENT '本地 xianyu_goods.id',
  `account_id` BIGINT NOT NULL COMMENT '本地闲鱼账号 ID',
  `external_goods_id` VARCHAR(200) NOT NULL COMMENT '平台商品 ID，仅用于恢复执行，不进入日志或浏览器响应',
  `idempotency_key` VARCHAR(128) NOT NULL COMMENT '单次下架意图的幂等键',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/remote_confirmed/confirmed/failed/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1 COMMENT '仅平台明确未执行时为 1',
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `remote_started_at` DATETIME NULL,
  `remote_confirmed_at` DATETIME NULL,
  `local_confirmed_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '脱敏、限长的可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_goods_off_shelf_attempt_key` (`idempotency_key`),
  KEY `idx_goods_off_shelf_goods_created` (`goods_id`, `created_time`),
  KEY `idx_goods_off_shelf_state_lease` (`state`, `lease_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商品下架的持久化幂等与恢复状态';
