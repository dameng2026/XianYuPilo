-- 为 xianyu_account 表添加闲鱼主页资料字段
ALTER TABLE xianyu_account ADD COLUMN introduction TEXT NULL COMMENT '简介' AFTER account_level;
ALTER TABLE xianyu_account ADD COLUMN followers INT NULL COMMENT '粉丝数' AFTER introduction;
ALTER TABLE xianyu_account ADD COLUMN following INT NULL COMMENT '关注数' AFTER followers;
ALTER TABLE xianyu_account ADD COLUMN sold_count INT NULL COMMENT '已售数' AFTER following;
ALTER TABLE xianyu_account ADD COLUMN review_num INT NULL COMMENT '评价数' AFTER sold_count;
ALTER TABLE xianyu_account ADD COLUMN seller_level VARCHAR(50) NULL COMMENT '卖家等级' AFTER review_num;
ALTER TABLE xianyu_account ADD COLUMN praise_ratio VARCHAR(20) NULL COMMENT '好评率' AFTER seller_level;
ALTER TABLE xianyu_account ADD COLUMN fish_shop_score DECIMAL(3,1) NULL COMMENT '鱼小铺分数' AFTER praise_ratio;
ALTER TABLE xianyu_account ADD COLUMN fish_shop_user TINYINT NULL DEFAULT 0 COMMENT '是否开通鱼小铺' AFTER fish_shop_score;
