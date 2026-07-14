-- ============================================================
-- 单租户精简版数据库初始化 Schema
-- 基于 xianyu-assistant-package-temp 源项目 entities.py 改造
-- 改造规则：
--   1. 移除所有表的 tenant_id、user_id 字段
--   2. operation_log 表使用 operator varchar(64) 替代 user_id
--   3. xianyu_chat_message 复合索引改为 (account_id, deleted, s_id, message_time)
--   4. 字符集统一 utf8mb4
--   5. 删除多租户/工作流/商机/计费/会员等相关表
-- 适用于 MySQL 8.0
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 一、闲鱼账号相关
-- ============================================================

-- 闲鱼账号
CREATE TABLE IF NOT EXISTS `xianyu_account` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(50) NULL DEFAULT 'xianyu' COMMENT '平台: xianyu',
  `external_uid` VARCHAR(200) NULL COMMENT '闲鱼external_uid',
  `nickname` VARCHAR(200) NULL,
  `avatar_url` TEXT NULL,
  `province` VARCHAR(100) NULL,
  `city` VARCHAR(100) NULL,
  `account_level` VARCHAR(50) NULL,
  `remark` TEXT NULL,
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1正常 0禁用',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_account_external_uid` (`external_uid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼账号';

-- 闲鱼账号认证信息
CREATE TABLE IF NOT EXISTS `xianyu_account_auth` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL,
  `encrypted_cookie` TEXT NULL COMMENT '加密Cookie',
  `encrypted_token` TEXT NULL COMMENT '加密Token',
  `login_username` VARCHAR(255) NULL,
  `encrypted_login_password` TEXT NULL,
  `show_browser` TINYINT(1) NULL DEFAULT 0,
  `cookie_status` SMALLINT NULL DEFAULT 0 COMMENT '1正常 0待校验/失效 2过期',
  `ws_token` TEXT NULL,
  `token_expire_time` DATETIME NULL,
  `last_login_status_code` VARCHAR(64) NULL,
  `last_login_status_message` VARCHAR(255) NULL,
  `last_login_check_time` DATETIME NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_account_auth_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼账号认证信息';

-- 闲鱼账号运行时状态
CREATE TABLE IF NOT EXISTS `xianyu_account_runtime` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL,
  `online_status` SMALLINT NULL DEFAULT 0 COMMENT '1在线 0离线',
  `ws_status` SMALLINT NULL DEFAULT 0 COMMENT '1在线 0离线',
  `ws_latency_ms` INT NULL DEFAULT 0,
  `cookie_status` SMALLINT NULL DEFAULT 0 COMMENT '1正常 0待校验/失效 2过期',
  `last_login_status_code` VARCHAR(64) NULL,
  `last_login_status_message` VARCHAR(255) NULL,
  `last_login_check_time` DATETIME NULL,
  `last_login_time` DATETIME NULL,
  `last_heartbeat_time` DATETIME NULL,
  `last_online_time` DATETIME NULL,
  `last_sync_time` DATETIME NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_account_runtime_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼账号运行时状态';

-- ============================================================
-- 二、商品
-- ============================================================

-- 闲鱼商品
CREATE TABLE IF NOT EXISTS `xianyu_goods` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `goods_id` VARCHAR(100) NULL COMMENT '兼容旧商品ID字段',
  `external_goods_id` VARCHAR(100) NULL COMMENT '闲鱼商品ID',
  `title` VARCHAR(500) NULL COMMENT '商品标题',
  `price` VARCHAR(50) NULL COMMENT '价格',
  `sold_price` VARCHAR(50) NULL COMMENT '售价',
  `cover_pic` TEXT NULL COMMENT '封面图URL',
  `image_url` TEXT NULL COMMENT '图片URL',
  `image_urls` JSON NULL COMMENT '图片URL列表',
  `stock` INT NULL DEFAULT 0 COMMENT '库存',
  `quantity` INT NULL DEFAULT 0 COMMENT '库存数量',
  `exposure_count` INT NULL DEFAULT 0 COMMENT '曝光次数',
  `view_count` INT NULL DEFAULT 0 COMMENT '浏览次数',
  `want_count` INT NULL DEFAULT 0 COMMENT '想要人数',
  `detail_url` TEXT NULL COMMENT '详情页URL',
  `detail_info` TEXT NULL COMMENT '详情描述文字',
  `description` TEXT NULL COMMENT '描述',
  `raw_payload` JSON NULL COMMENT '原始商品数据快照',
  `category` VARCHAR(100) NULL COMMENT '分类',
  `sort_order` INT NULL DEFAULT 0 COMMENT '排序序号',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1在售 0下架 2已售',
  `deleted` SMALLINT NULL DEFAULT 0,
  `auto_reply_enabled` SMALLINT NULL DEFAULT NULL COMMENT 'NULL继承账号全局 0强制关 1强制开',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_goods_account` (`account_id`),
  INDEX `idx_goods_external` (`external_goods_id`),
  INDEX `idx_goods_status` (`status`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼商品';

-- ============================================================
-- 三、订单
-- ============================================================

-- 闲鱼交易订单
CREATE TABLE IF NOT EXISTS `xianyu_trade_order` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `external_order_id` VARCHAR(200) NULL COMMENT '闲鱼订单ID',
  `order_status` SMALLINT NULL DEFAULT 0 COMMENT '0待付款 1已付款 2待发货 3已发货 4已完成 5已关闭',
  `total_amount` VARCHAR(50) NULL,
  `buyer_name` VARCHAR(200) NULL,
  `buyer_id` VARCHAR(200) NULL,
  `create_time` DATETIME NULL,
  `pay_time` DATETIME NULL,
  `ship_time` DATETIME NULL,
  `confirm_time` DATETIME NULL,
  `buyer_message` TEXT NULL,
  `item_id` VARCHAR(100) NULL COMMENT '商品ID',
  `is_bargain` SMALLINT NULL DEFAULT 0 COMMENT '是否小刀',
  `is_rated` SMALLINT NULL DEFAULT 0 COMMENT '是否已评价',
  `is_red_flower` SMALLINT NULL DEFAULT 0 COMMENT '是否已求小红花',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_order_account` (`account_id`),
  INDEX `idx_order_external` (`external_order_id`),
  INDEX `idx_order_status` (`order_status`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼交易订单';

-- 闲鱼交易订单明细
CREATE TABLE IF NOT EXISTS `xianyu_trade_order_item` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `order_id` BIGINT NOT NULL,
  `goods_id` BIGINT NULL,
  `goods_name` VARCHAR(300) NULL,
  `goods_title` VARCHAR(500) NULL,
  `goods_image` TEXT NULL,
  `goods_price` DECIMAL(12,2) NULL,
  `price_cent` BIGINT NULL DEFAULT 0,
  `goods_count` INT NULL DEFAULT 1,
  `quantity` INT NULL DEFAULT 1,
  `subtotal_cent` BIGINT NULL DEFAULT 0,
  `sku_id` VARCHAR(100) NULL,
  `sku_name` VARCHAR(200) NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_order_item_order` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼交易订单明细';

-- ============================================================
-- 四、会话与消息
-- ============================================================

-- 闲鱼会话
CREATE TABLE IF NOT EXISTS `xianyu_conversation` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `seller_external_uid` VARCHAR(64) NULL COMMENT '闲鱼卖家真实UID/unb',
  `external_buyer_id` VARCHAR(200) NULL,
  `peer_external_uid` VARCHAR(64) NULL COMMENT '买家UID（稳定）',
  `peer_key` VARCHAR(128) NULL COMMENT '对端唯一标识（用于去重合并会话）',
  `buyer_name` VARCHAR(200) NULL,
  `buyer_avatar` TEXT NULL,
  `goods_title` VARCHAR(500) NULL,
  `goods_id` VARCHAR(200) NULL,
  `status` SMALLINT NULL DEFAULT 0 COMMENT '0进行中 1已完成 2已关闭',
  `last_message_time` DATETIME NULL,
  `last_message_content` TEXT NULL,
  `unread_count` INT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_conversation_account` (`account_id`),
  INDEX `idx_conversation_peer` (`peer_external_uid`),
  INDEX `idx_conversation_peer_key` (`peer_key`),
  INDEX `idx_conversation_last_msg` (`account_id`, `last_message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼会话';

-- 闲鱼 WebSocket 实时聊天消息（去重存储，含完整原始消息体）
CREATE TABLE IF NOT EXISTS `xianyu_chat_message` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL COMMENT '闲鱼账号ID',
  `seller_external_uid` VARCHAR(64) NULL COMMENT '闲鱼卖家真实UID/unb',
  `pnm_id` VARCHAR(200) NULL COMMENT '消息唯一ID（去重）',
  `message_uid` VARCHAR(128) NULL COMMENT '稳定消息唯一ID（用于去重）',
  `s_id` VARCHAR(200) NULL COMMENT '会话ID',
  `content_type` INT NULL DEFAULT 1 COMMENT '消息类型:1文本 2图片 14砍价 25已拍下 26已付款 28已发货 32已读',
  `msg_content` TEXT NULL COMMENT '消息文本内容',
  `sender_user_id` VARCHAR(200) NULL COMMENT '发送者ID',
  `receiver_user_id` VARCHAR(64) NULL COMMENT '接收者用户ID',
  `sender_user_name` VARCHAR(200) NULL COMMENT '发送者昵称',
  `peer_external_uid` VARCHAR(64) NULL COMMENT '买家UID',
  `xy_goods_id` VARCHAR(200) NULL COMMENT '关联商品ID',
  `message_time` BIGINT NULL DEFAULT 0 COMMENT '消息时间戳(毫秒)',
  `direction` VARCHAR(20) NULL DEFAULT 'IN' COMMENT 'IN/OUT',
  `parse_status` VARCHAR(16) NULL DEFAULT 'ok' COMMENT '解析状态 ok/partial/failed',
  `reminder_content` TEXT NULL COMMENT '提醒内容',
  `reminder_url` VARCHAR(500) NULL COMMENT '提醒链接',
  `complete_msg` JSON NULL COMMENT '完整原始消息体',
  `raw_payload` JSON NULL COMMENT '原始消息payload（用于调试和重新解析）',
  `read_status` SMALLINT NULL DEFAULT 0 COMMENT '0未读 1已读',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_chat_msg_lookup` (`account_id`, `deleted`, `s_id`, `message_time`),
  INDEX `idx_chat_msg_pnm` (`pnm_id`),
  INDEX `idx_chat_msg_uid` (`message_uid`),
  INDEX `idx_chat_msg_conversation` (`s_id`, `message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼WebSocket实时聊天消息';

-- ============================================================
-- 五、发货规则与卡密
-- ============================================================

-- 发货规则
CREATE TABLE IF NOT EXISTS `delivery_rule` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `rule_name` VARCHAR(200) NULL,
  `goods_id` BIGINT NULL,
  `delivery_mode` VARCHAR(50) NULL DEFAULT 'kami',
  `card_group_id` BIGINT NULL,
  `delivery_content` TEXT NULL,
  `trigger_on_pay` SMALLINT NULL DEFAULT 1,
  `trigger_keyword` VARCHAR(200) NULL,
  `max_delivery_per_day` INT NULL DEFAULT 0,
  `status` SMALLINT NULL DEFAULT 1,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_delivery_rule_account` (`account_id`),
  INDEX `idx_delivery_rule_goods` (`goods_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='发货规则';

-- 卡密分组
CREATE TABLE IF NOT EXISTS `card_group` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `group_name` VARCHAR(200) NOT NULL,
  `group_type` VARCHAR(50) NULL DEFAULT 'kami',
  `total_count` INT NULL DEFAULT 0,
  `used_count` INT NULL DEFAULT 0,
  `available_count` INT NULL DEFAULT 0,
  `remark` TEXT NULL,
  `status` SMALLINT NULL DEFAULT 1,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='卡密分组';

-- 卡密条目
CREATE TABLE IF NOT EXISTS `card_item` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `group_id` BIGINT NOT NULL,
  `card_key` TEXT NOT NULL,
  `card_value` TEXT NULL,
  `extra_info` TEXT NULL,
  `is_used` SMALLINT NULL DEFAULT 0,
  `used_time` DATETIME NULL,
  `used_by_order_id` BIGINT NULL,
  `used_by_user` VARCHAR(200) NULL,
  `expire_time` DATETIME NULL,
  `remark` TEXT NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_card_item_group` (`group_id`),
  INDEX `idx_card_item_used_order` (`used_by_order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='卡密条目';

-- 发货记录
CREATE TABLE IF NOT EXISTS `delivery_record` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL COMMENT '关联xianyu_account.id',
  `order_id` BIGINT NULL COMMENT '关联xianyu_trade_order.id',
  `rule_id` BIGINT NULL COMMENT '关联delivery_rule.id',
  `delivery_type` VARCHAR(50) NULL,
  `content` TEXT NULL,
  `delivery_status` VARCHAR(50) NULL DEFAULT 'pending' COMMENT '发货状态 pending/success/failed',
  `error_message` TEXT NULL,
  `retry_count` INT NULL DEFAULT 0,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_delivery_record_order` (`order_id`),
  INDEX `idx_delivery_record_account` (`account_id`),
  INDEX `idx_delivery_record_status` (`delivery_status`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='发货记录';

-- ============================================================
-- 六、自动回复
-- ============================================================

-- 自动回复规则
CREATE TABLE IF NOT EXISTS `auto_reply_rule` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `rule_name` VARCHAR(200) NULL,
  `match_type` VARCHAR(50) NULL DEFAULT 'keyword' COMMENT 'keyword/ai/all',
  `match_keywords` TEXT NULL,
  `reply_content` TEXT NULL,
  `reply_mode` VARCHAR(50) NULL DEFAULT 'keyword' COMMENT 'keyword/ai',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `priority` INT NULL DEFAULT 0,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_auto_reply_rule_account` (`account_id`),
  INDEX `idx_auto_reply_rule_status` (`status`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动回复规则';

-- 自动回复日志
CREATE TABLE IF NOT EXISTS `auto_reply_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `conversation_id` BIGINT NULL,
  `rule_id` BIGINT NULL,
  `trigger_message` TEXT NULL,
  `reply_content` TEXT NULL,
  `hit_type` VARCHAR(60) NULL COMMENT '命中类型：keyword/ai',
  `status` TINYINT NULL DEFAULT 1 COMMENT '1成功 0失败',
  `fail_reason` VARCHAR(500) NULL,
  `action` VARCHAR(40) NULL COMMENT '处理动作：manual/suggest_only/auto_send_allowed',
  `safety_reasons` TEXT NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_auto_reply_log_account` (`account_id`, `created_time`),
  INDEX `idx_auto_reply_log_rule` (`rule_id`, `created_time`),
  INDEX `idx_auto_reply_log_created` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动回复日志';

-- 快捷回复模板
CREATE TABLE IF NOT EXISTS `quick_reply_template` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL COMMENT 'NULL 表示全局通用',
  `title` VARCHAR(200) NOT NULL COMMENT '模板标题',
  `content` TEXT NOT NULL COMMENT '模板内容',
  `sort_order` INT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_quick_reply_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='快捷回复模板';

-- ============================================================
-- 七、通知与操作日志
-- ============================================================

-- 系统通知
CREATE TABLE IF NOT EXISTS `notification` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `notification_type` VARCHAR(50) NULL COMMENT '通知类型',
  `title` VARCHAR(300) NULL,
  `content` TEXT NULL,
  `reference_type` VARCHAR(100) NULL,
  `reference_id` BIGINT NULL,
  `is_read` SMALLINT NULL DEFAULT 0 COMMENT '0未读 1已读',
  `read_time` DATETIME NULL,
  `priority` SMALLINT NULL DEFAULT 0 COMMENT '优先级',
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_notification_is_read` (`is_read`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统通知';

-- 操作日志（使用 operator 字段替代 user_id）
CREATE TABLE IF NOT EXISTS `operation_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `operator` VARCHAR(64) NULL COMMENT '操作者标识',
  `operation_type` VARCHAR(100) NULL,
  `operation_desc` TEXT NULL,
  `target_type` VARCHAR(100) NULL,
  `target_id` VARCHAR(100) NULL,
  `ip_address` VARCHAR(50) NULL,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_operation_log_operator` (`operator`, `created_time`),
  INDEX `idx_operation_log_type` (`operation_type`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作日志';

-- ============================================================
-- 八、系统配置与 AI Provider
-- ============================================================

-- 系统动态配置
CREATE TABLE IF NOT EXISTS `xianyu_sys_setting` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `setting_key` VARCHAR(100) NULL,
  `setting_value` TEXT NULL,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uk_sys_setting_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统动态配置';

-- AI 服务商配置
-- 用户通知配置
CREATE TABLE IF NOT EXISTS `user_notification_setting` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL,
  `config_json` JSON NOT NULL,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` TINYINT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uk_uns_user` (`user_id`),
  INDEX `idx_uns_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户通知配置';

-- 通知投递日志
CREATE TABLE IF NOT EXISTS `notification_delivery_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NULL,
  `channel_key` VARCHAR(80) NULL,
  `channel_name` VARCHAR(120) NULL,
  `event_type` VARCHAR(80) NULL,
  `success` TINYINT NULL DEFAULT 0,
  `status_code` INT NULL DEFAULT 0,
  `cost_ms` BIGINT NULL DEFAULT 0,
  `message` VARCHAR(500) NULL,
  `request_body` TEXT NULL,
  `response_body` TEXT NULL,
  `retry_count` INT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_ndl_user_time` (`user_id`, `created_time`),
  INDEX `idx_ndl_success` (`success`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知投递日志';

CREATE TABLE IF NOT EXISTS `xianyu_ai_provider` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `provider_name` VARCHAR(100) NULL,
  `api_key` TEXT NULL,
  `base_url` VARCHAR(500) NULL,
  `model_name` VARCHAR(200) NULL,
  `status` INT NULL DEFAULT 1,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI服务商配置';

-- ============================================================
-- 九、模型配置（新增）
-- ============================================================

-- 模型配置（按场景）
CREATE TABLE IF NOT EXISTS `model_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `scene` VARCHAR(50) NULL COMMENT '使用场景',
  `provider_name` VARCHAR(100) NULL COMMENT '服务商名称',
  `model_name` VARCHAR(200) NULL COMMENT '模型名称',
  `base_url` VARCHAR(500) NULL COMMENT 'API base URL',
  `api_key` TEXT NULL COMMENT 'API Key',
  `max_tokens` INT NULL DEFAULT 0 COMMENT '最大token数',
  `temperature` DECIMAL(3,2) NULL DEFAULT 0.70 COMMENT '温度参数',
  `image_size` VARCHAR(50) NULL COMMENT '图片尺寸',
  `quality` VARCHAR(50) NULL COMMENT '图片质量',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_model_config_scene` (`scene`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型配置';

-- 模型图像生成提示词模板
CREATE TABLE IF NOT EXISTS `model_config_image_prompt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(200) NULL COMMENT '模板名称',
  `category_key` VARCHAR(100) NULL COMMENT '分类key',
  `match_keywords` TEXT NULL COMMENT '匹配关键词（多个用逗号分隔）',
  `prompt_template` TEXT NULL COMMENT '提示词模板',
  `enabled` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `sort_order` INT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_image_prompt_category` (`category_key`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型图像生成提示词模板';

-- ============================================================
-- 十、RAG 知识库（新增）
-- ============================================================

-- 知识库
CREATE TABLE IF NOT EXISTS `rag_knowledge_base` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `knowledge_name` VARCHAR(200) NULL COMMENT '知识库名称',
  `description` TEXT NULL COMMENT '描述',
  `doc_count` INT NULL DEFAULT 0 COMMENT '文档数量',
  `vector_count` INT NULL DEFAULT 0 COMMENT '向量数量',
  `storage_size` BIGINT NULL DEFAULT 0 COMMENT '存储大小（字节）',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` SMALLINT NULL DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG知识库';

-- 知识库文档
CREATE TABLE IF NOT EXISTS `rag_document` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `knowledge_base_id` BIGINT NOT NULL COMMENT '所属知识库ID',
  `file_name` VARCHAR(500) NULL COMMENT '文件名',
  `file_path` VARCHAR(1000) NULL COMMENT '文件路径',
  `file_size` BIGINT NULL DEFAULT 0 COMMENT '文件大小（字节）',
  `chunk_count` INT NULL DEFAULT 0 COMMENT '分块数量',
  `parse_status` VARCHAR(30) NULL DEFAULT 'pending' COMMENT '解析状态 pending/parsing/success/failed',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` SMALLINT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  INDEX `idx_rag_document_kb` (`knowledge_base_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG知识库文档';

-- 知识库分块
CREATE TABLE IF NOT EXISTS `rag_chunk` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `document_id` BIGINT NOT NULL COMMENT '所属文档ID',
  `knowledge_base_id` BIGINT NOT NULL COMMENT '所属知识库ID',
  `chunk_index` INT NULL DEFAULT 0 COMMENT '分块序号',
  `content` TEXT NULL COMMENT '分块文本内容',
  `embedding` LONGBLOB NULL COMMENT '向量 embedding',
  `token_count` INT NULL DEFAULT 0 COMMENT 'token数量',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_rag_chunk_document` (`document_id`),
  INDEX `idx_rag_chunk_kb` (`knowledge_base_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG知识库分块';

-- ============================================================
-- 十一、敏感词与定时任务（新增）
-- ============================================================

-- 敏感词
CREATE TABLE IF NOT EXISTS `sensitive_word` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `word` VARCHAR(200) NULL COMMENT '敏感词',
  `category` VARCHAR(50) NULL COMMENT '分类',
  `action` VARCHAR(50) NULL COMMENT '处理动作',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_sensitive_word_status` (`status`),
  INDEX `idx_sensitive_word_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='敏感词';

-- 定时任务
CREATE TABLE IF NOT EXISTS `scheduled_task` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `task_name` VARCHAR(200) NULL COMMENT '任务名称',
  `task_type` VARCHAR(80) NULL COMMENT '任务类型',
  `cron_expr` VARCHAR(120) NULL COMMENT 'cron 表达式',
  `config` JSON NULL COMMENT '任务配置',
  `last_run_time` DATETIME NULL COMMENT '上次执行时间',
  `next_run_time` DATETIME NULL COMMENT '下次执行时间',
  `status` SMALLINT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` SMALLINT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  INDEX `idx_scheduled_task_status` (`status`, `deleted`),
  INDEX `idx_scheduled_task_next_run` (`next_run_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时任务';

SET FOREIGN_KEY_CHECKS = 1;
