-- Migration 027: 补全 xianyu_conversation 表缺失的 goods_cover_pic 列，并新增 s_id 列
-- 解决问题：
--   1. goods_cover_pic 列在 entities.py 模型中已定义，但 001_init.sql 建表时遗漏，
--      导致 ws_storage.py 中引用 conv.goods_cover_pic 的 SQL 报错（Unknown column）。
--   2. 新增 s_id 列用于持久化会话的闲鱼 sId，解决 _save_conversation_user_info
--      在 peer_key 从 sid:xxx 升级为真实买家 UID 后无法匹配会话的问题，
--      该问题导致头像查询结果无法写回数据库。

SET NAMES utf8mb4;

-- 补全 goods_cover_pic 列（商品封面图URL）
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 'goods_cover_pic'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `goods_cover_pic` TEXT NULL COMMENT ''商品封面图URL'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 新增 s_id 列（闲鱼会话sId，用于头像查询等场景的稳定匹配）
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND column_name = 's_id'),
  'SELECT 1',
  'ALTER TABLE `xianyu_conversation` ADD COLUMN `s_id` VARCHAR(200) NULL COMMENT ''闲鱼会话sId（头像查询稳定匹配键）'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 为 s_id 列添加索引（加速头像查询时的会话匹配）
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_conversation'
      AND index_name = 'idx_conversation_sid'),
  'SELECT 1',
  'CREATE INDEX `idx_conversation_sid` ON `xianyu_conversation` (`account_id`, `s_id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 回填已有会话的 s_id：从 peer_key 提取（格式为 sid:xxx 的会话）
-- 注意：避免使用 LIKE 'sid:%'，因为 aiomysql 驱动会把 % 当作 Python 格式化符
UPDATE `xianyu_conversation`
SET `s_id` = SUBSTRING(`peer_key`, 5)
WHERE `s_id` IS NULL
  AND LEFT(`peer_key`, 4) = 'sid:'
  AND LENGTH(`peer_key`) > 4;
