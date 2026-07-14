-- Migration 006: durable, idempotent state machine for irreversible remote
-- goods deletion. No platform calls and no existing goods are modified here.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `remote_goods_delete_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `goods_id` BIGINT NOT NULL COMMENT '本地 xianyu_goods.id',
  `account_id` BIGINT NOT NULL COMMENT '本地闲鱼账号 ID',
  `external_goods_id` VARCHAR(200) NOT NULL COMMENT '平台商品 ID，仅用于恢复执行，不进入日志或浏览器响应',
  `idempotency_key` VARCHAR(128) NOT NULL COMMENT '删除意图幂等键',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/remote_confirmed/confirmed/failed/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `remote_started_at` DATETIME NULL,
  `remote_confirmed_at` DATETIME NULL,
  `local_deleted_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '脱敏、限长的可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_remote_goods_delete_attempt_goods` (`goods_id`),
  UNIQUE KEY `uk_remote_goods_delete_attempt_key` (`idempotency_key`),
  KEY `idx_remote_goods_delete_attempt_state_lease` (`state`, `lease_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='远程删除商品的持久化幂等与恢复状态';

