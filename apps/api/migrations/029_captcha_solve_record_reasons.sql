-- 滑块求解记录表
-- 记录每次滑块自动求解的触发场景、处理结果和验证状态
-- 对标商业版 V1.8（基表）+ V1.9（open_reason / solve_reason），合并为单租户版本
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `xianyu_captcha_solve_record` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `account_id` BIGINT NOT NULL COMMENT '账号ID',
  `account_name` VARCHAR(128) DEFAULT '' COMMENT '账号名称',
  `event_desc` VARCHAR(255) NOT NULL COMMENT '事件描述',
  `open_reason` VARCHAR(255) DEFAULT '' COMMENT '开启原因：为什么打开滑块求解流程（手动/自动 等）',
  `solve_reason` VARCHAR(255) DEFAULT '' COMMENT '求解原因：为什么进行滑块求解（具体业务原因，如 WS Token 失败/Cookie 保活触发滑块 等）',
  `trigger_scene` VARCHAR(64) DEFAULT '' COMMENT '触发场景: ws_connect/cookie_keepalive/token_refresh/manual',
  `result` VARCHAR(32) DEFAULT '' COMMENT '处理结果: slider_success/slider_fail',
  `status` VARCHAR(32) NOT NULL DEFAULT 'retrying' COMMENT '处理状态: retrying/success/fail',
  `engine` VARCHAR(64) DEFAULT 'Playwright' COMMENT '验证引擎',
  `retry_count` INT DEFAULT 0 COMMENT '重试次数',
  `error_message` TEXT COMMENT '错误详情',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` TINYINT DEFAULT 0 COMMENT '0未删除 1已删除',
  PRIMARY KEY (`id`),
  INDEX `idx_csr_account_id` (`account_id`),
  INDEX `idx_csr_created_at` (`created_at`),
  INDEX `idx_csr_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='滑块求解记录表';
