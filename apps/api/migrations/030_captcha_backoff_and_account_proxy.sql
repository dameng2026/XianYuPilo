-- 全自动滑块：失败指数退避状态表
-- 对标商业版 V1.10 的 xianyu_captcha_backoff 部分（单租户版，不含账号代理列）
-- 代理用于按账号固定出口，属商业版多租户能力，开源版不引入
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `xianyu_captcha_backoff` (
  `account_id` BIGINT NOT NULL COMMENT '账号ID',
  `fail_count` INT NOT NULL DEFAULT 0 COMMENT '连续失败次数',
  `next_allowed_at` DATETIME NULL COMMENT '下次允许自动求解时间',
  `last_fail_at` DATETIME NULL COMMENT '最近失败时间',
  `last_success_at` DATETIME NULL COMMENT '最近成功时间',
  `last_error` VARCHAR(512) DEFAULT '' COMMENT '最近失败摘要',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`),
  INDEX `idx_cb_next_allowed` (`next_allowed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='滑块自动求解指数退避';
