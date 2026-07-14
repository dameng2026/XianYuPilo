"""
闲鱼商品自动分类服务
负责：
1. 上传封面图到闲鱼 CDN
2. 调用闲鱼分类推荐接口 mtop.taobao.idle.kgraph.property.recommend
3. 自动选择最佳分类
4. 返回推荐分类和候选分类，失败时返回明确的 fallback 状态
"""

import hashlib
import io
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image

from ..core.config import settings

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

H5_API_BASE = "https://h5api.m.goofish.com/h5"
UPLOAD_URL = settings.xianyu_mtop_upload_url or "https://stream-upload.goofish.com/api/upload.api?floderId=0&appkey=xy_chat"
CATEGORY_API = settings.xianyu_mtop_category_api or "mtop.taobao.idle.kgraph.property.recommend"
CATEGORY_VERSION = settings.xianyu_mtop_category_version or "2.0"
MTOP_APP_KEY = settings.xianyu_mtop_app_key or "34839810"
MIN_SCORE = settings.auto_category_min_score or 0.08
MIN_MARGIN = settings.auto_category_min_margin or 0.03

UPLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.goofish.com/",
    "Origin": "https://www.goofish.com",
}

CATEGORY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.goofish.com/",
    "Origin": "https://www.goofish.com",
}


# ==================== 工具函数 ====================


def _parse_cookie(cookie_str: str) -> dict:
    """解析 Cookie 字符串为字典"""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


def _get_token_from_cookie(cookie_str: str) -> Optional[str]:
    """从 Cookie 中提取 _m_h5_tk 的 token 部分"""
    cookies = _parse_cookie(cookie_str)
    m_h5_tk = cookies.get("_m_h5_tk", "")
    if not m_h5_tk:
        return None
    return m_h5_tk.split("_")[0]


def _build_sign(token: str, t_ms: int, data_json: str) -> str:
    """构建 MTOP 签名"""
    raw = f"{token}&{t_ms}&{MTOP_APP_KEY}&{data_json}"
    return hashlib.md5(raw.encode()).hexdigest()


def _compress_image(image_data: bytes, max_size: int = 2048, target_bytes: int = 500 * 1024) -> bytes:
    """
    压缩图片。
    最长边 <= max_size px
    转 JPEG
    质量从 85 逐步压缩到 20
    目标大小 <= target_bytes
    """
    img = Image.open(io.BytesIO(image_data))

    # 转换 RGB 模式
    if img.mode in ("RGBA", "P", "PA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 缩放最长边
    w, h = img.size
    if max(w, h) > max_size:
        if w >= h:
            new_w = max_size
            new_h = int(h * max_size / w)
        else:
            new_h = max_size
            new_w = int(w * max_size / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # 逐步压缩
    for quality in range(85, 15, -5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= target_bytes:
            return data

    # 如果压缩到 20 质量仍然超过目标大小，直接返回
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=20, optimize=True)
    return buf.getvalue()


def _extract_cdn_url(response: dict) -> Optional[str]:
    """
    从上传响应中提取 CDN URL。
    兼容多种返回格式：
    { "url": "..." }
    { "data": { "url": "..." } }
    { "object": { "url": "..." } }
    { "result": { "url": "..." } }
    [ { "url": "..." } ]
    兜底正则提取 img.alicdn.com 链接
    """
    # 尝试遍历各种可能的 key
    for top_key in ("url", "data", "object", "result"):
        val = response.get(top_key)
        if isinstance(val, dict):
            url = val.get("url") or val.get("cdnUrl") or val.get("cdn_url") or ""
            if url:
                return url
        elif isinstance(val, str) and val.startswith("http"):
            return val

    # 尝试数组格式
    for top_key in response:
        val = response[top_key]
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, dict):
                url = first.get("url") or ""
                if url:
                    return url

    # 兜底：正则提取
    response_str = json.dumps(response, ensure_ascii=False)
    m = re.search(r'https://img\.alicdn\.com[^"\'\\\s,]+', response_str)
    if m:
        return m.group(0)

    return None


# ==================== 核心服务 ====================


def upload_image_to_xianyu(
    cookie_str: str,
    image_data: bytes,
) -> Tuple[str, int, int]:
    """
    上传图片到闲鱼 CDN。
    返回 (cdn_url, width, height)
    """
    # 压缩图片
    compressed = _compress_image(image_data)

    # 获取宽高
    img = Image.open(io.BytesIO(compressed))
    width, height = img.size

    # 构建 multipart 请求
    session = requests.Session()
    session.trust_env = False
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            session.cookies.set(key.strip(), value.strip(), domain=".goofish.com")

    files = {
        "file": ("image.jpg", compressed, "image/jpeg"),
    }

    logger.info(
        "正在上传图片到闲鱼 CDN, 压缩后大小=%dKB, 尺寸=%dx%d",
        len(compressed) // 1024, width, height,
    )

    try:
        resp = session.post(
            UPLOAD_URL,
            headers=UPLOAD_HEADERS,
            files=files,
            timeout=60,
        )
    finally:
        session.close()
    resp.raise_for_status()

    result = resp.json()
    cdn_url = _extract_cdn_url(result)

    if not cdn_url:
        logger.error(
            "上传图片后未能提取到 CDN URL responseKeys=%s",
            sorted(str(key) for key in result.keys())[:30] if isinstance(result, dict) else [],
        )
        raise RuntimeError("UPLOAD_NO_CDN_URL")

    logger.info("图片上传成功, 尺寸=%dx%d", width, height)
    return cdn_url, width, height


def call_category_recommend(
    cookie_str: str,
    cdn_url: str,
    width: int = 1024,
    height: int = 1024,
) -> dict:
    """
    调用闲鱼分类推荐接口。
    返回解析后的响应体。
    """
    token = _get_token_from_cookie(cookie_str)
    if not token:
        raise RuntimeError("COOKIE_MISSING_M_H5_TK")

    t_ms = int(time.time() * 1000)
    unique_code = f"{t_ms}{int(time.time() * 1000000) % 100000}"

    data = {
        "lockCpv": False,
        "multiSKU": False,
        "publishScene": "mainPublish",
        "scene": "newPublishChoice",
        "imageInfos": [
            {
                "extraInfo": {
                    "isH": "false",
                    "isT": "false",
                    "raw": "false",
                },
                "isQrCode": False,
                "url": cdn_url,
                "heightSize": height,
                "widthSize": width,
                "major": True,
                "type": 0,
                "status": "done",
            }
        ],
        "uniqueCode": unique_code,
    }

    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    sign = _build_sign(token, t_ms, data_json)

    url = f"{H5_API_BASE}/{CATEGORY_API}/{CATEGORY_VERSION}/"

    form_data = {
        "jsv": "2.7.2",
        "appKey": MTOP_APP_KEY,
        "t": str(t_ms),
        "sign": sign,
        "v": CATEGORY_VERSION,
        "type": "originaljson",
        "dataType": "json",
        "timeout": "30000",
        "api": CATEGORY_API,
        "data": data_json,
    }

    logger.info("正在调用分类推荐接口, 图片尺寸=%dx%d", width, height)

    session = requests.Session()
    session.trust_env = False
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            session.cookies.set(key.strip(), value.strip(), domain=".goofish.com")

    try:
        resp = session.post(url, headers=CATEGORY_HEADERS, data=form_data, timeout=60)
    finally:
        session.close()
    resp.raise_for_status()

    result = resp.json()

    ret = result.get("ret", [])
    ret_msg = str(ret[0]) if isinstance(ret, list) and ret else str(ret)

    # 检查签名错误
    if "SIGN_FAILED" in ret_msg or "ILLEGAL_SIGN" in ret_msg:
        logger.error("分类接口签名失败，请检查服务端配置")
        raise RuntimeError("CATEGORY_SIGN_FAILED")

    if "SUCCESS" not in ret_msg:
        logger.error("分类接口调用失败")
        raise RuntimeError("CATEGORY_API_FAILED")

    logger.info("分类推荐接口调用成功")
    return result


def select_best_category(
    result: dict,
    min_score: float = MIN_SCORE,
    min_margin: float = MIN_MARGIN,
) -> dict:
    """
    从分类推荐结果中自动选择最佳分类。

    返回结构:
    {
        "auto_select": bool,
        "reason": str,
        "category": dict | None,
        "candidates": list
    }

    选择优先级:
    1. 优先使用 data.categoryPredictResult
    2. 到 cardList 中找 propertyName == "分类" 的卡片
    3. 在分类卡片 valuesList 中匹配 categoryPredictResult 的 channelCatId/catId/tbCatId
    4. 如果没有 categoryPredictResult，则选 isClicked == "1" 的项
    5. 如果仍没有，则选择 score 最高的项
    6. 低置信度时标记需要 fallback
    """
    data = result.get("data", {}) if isinstance(result, dict) else {}
    if not isinstance(data, dict):
        return _no_category_result("接口返回数据格式异常")

    # 提取 categoryPredictResult
    predict_result = data.get("categoryPredictResult")

    # 提取 cardList
    card_list = data.get("cardList", [])
    if not isinstance(card_list, list):
        card_list = []

    # 找到 propertyName == "分类" 的卡片
    category_card = None
    for card in card_list:
        if not isinstance(card, dict):
            continue
        card_data = card.get("cardData") or card
        if isinstance(card_data, dict):
            prop_name = card_data.get("propertyName", "")
            if prop_name == "分类":
                category_card = card_data
                break

    if not category_card:
        logger.warning("未找到 propertyName='分类' 的卡片，无候选分类")
        return _no_category_result("CATEGORY_NO_CANDIDATES")

    # 提取 valuesList
    values_list = category_card.get("valuesList", [])
    if not isinstance(values_list, list):
        values_list = []

    if not values_list:
        logger.warning("分类卡片 valuesList 为空")
        return _no_category_result("CATEGORY_NO_CANDIDATES")

    # 构建候选分类列表
    # 保留闲鱼 4 级层级信息：channelCat1Name → channelCat2Name → channelCat3Name → catName
    # 供当前请求的自动选择和前端候选路径展示；不会修改版本化分类文件。
    candidates = []
    for val in values_list:
        if not isinstance(val, dict):
            continue
        candidate = {
            "catId": val.get("catId", ""),
            "catName": val.get("catName", val.get("name", "")),
            "channelCatId": val.get("channelCatId", ""),
            "channelCatName": val.get("channelCatName", val.get("channelName", "")),
            "channelCat1Id": val.get("channelCat1Id", ""),
            "channelCat1Name": val.get("channelCat1Name", ""),
            "channelCat2Id": val.get("channelCat2Id", ""),
            "channelCat2Name": val.get("channelCat2Name", ""),
            "channelCat3Id": val.get("channelCat3Id", ""),
            "channelCat3Name": val.get("channelCat3Name", ""),
            "tbCatId": val.get("tbCatId", ""),
            "leafId": val.get("leafId"),
            "score": _safe_float(val.get("score")),
            "isClicked": val.get("isClicked", "0"),
            "transportData": val.get("transportData", {}),
        }
        candidates.append(candidate)

    # 按 score 降序排序
    candidates.sort(key=lambda x: x["score"], reverse=True)

    selected = None
    selected_from_predict = False  # 标记是否来自 categoryPredictResult（闲鱼官方首选）

    # 优先级 1: 优先使用 categoryPredictResult（闲鱼官方首选推荐，直接采用，跳过置信度检查）
    if predict_result and isinstance(predict_result, dict):
        predict_channel_cat_id = str(predict_result.get("channelCatId", ""))
        predict_cat_id = str(predict_result.get("catId", ""))
        predict_tb_cat_id = str(predict_result.get("tbCatId", ""))

        for c in candidates:
            if (predict_channel_cat_id and str(c.get("channelCatId", "")) == predict_channel_cat_id) or \
               (predict_cat_id and str(c.get("catId", "")) == predict_cat_id) or \
               (predict_tb_cat_id and str(c.get("tbCatId", "")) == predict_tb_cat_id):
                selected = c
                selected_from_predict = True
                break

    # 优先级 2: 选 isClicked == "1" 的项
    if not selected:
        for c in candidates:
            if c.get("isClicked") == "1":
                selected = c
                break

    # 优先级 3: 选 score 最高的项
    if not selected and candidates:
        selected = candidates[0]

    # 闲鱼官方首选推荐：直接采用，跳过 score/margin/名称过滤
    # 这是闲鱼发布页面的真实行为，categoryPredictResult 是官方算法的首选分类
    if selected and selected_from_predict:
        logger.info(
            "采用闲鱼官方首选推荐分类( categoryPredictResult ): catName=%s, catId=%s, channelCatId=%s, tbCatId=%s",
            selected.get("catName", ""), selected.get("catId", ""),
            selected.get("channelCatId", ""), selected.get("tbCatId", ""),
        )
        return {
            "auto_select": True,
            "reason": "官方首选推荐",
            "category": selected,
            "candidates": candidates,
        }

    # 置信度检查（仅对非官方首选的候选）
    if selected:
        top1_score = selected["score"]
        top2_score = candidates[1]["score"] if len(candidates) > 1 else 0

        # 检查最低分阈值
        if top1_score < min_score:
            logger.warning(
                "分类置信度不足: top1_score=%.4f < min_score=%.4f, 分类名称=%s",
                top1_score, min_score, selected.get("catName", ""),
            )
            return {
                "auto_select": False,
                "reason": "LOW_CONFIDENCE",
                "category": None,
                "candidates": candidates,
            }

        # 检查 top1 与 top2 差距
        margin = top1_score - top2_score
        if margin < min_margin:
            logger.warning(
                "分类置信度 margin 不足: top1_score=%.4f, top2_score=%.4f, margin=%.4f < min_margin=%.4f",
                top1_score, top2_score, margin, min_margin,
            )
            return {
                "auto_select": False,
                "reason": "LOW_CONFIDENCE",
                "category": None,
                "candidates": candidates,
            }

        # 仅过滤完全等于"其他"或"其他闲置"的兜底分类
        # 注意：闲鱼很多细分类名包含"其他"前缀（如"其他技能培训"、"其他医美项目"），这些是有效分类，不应过滤
        cat_name = (selected.get("catName") or "").strip()
        if cat_name == "其他" or cat_name == "其他闲置":
            logger.warning("分类为兜底分类'%s'，不自动强选", cat_name)
            return {
                "auto_select": False,
                "reason": "LOW_CONFIDENCE",
                "category": None,
                "candidates": candidates,
            }

        logger.info(
            "自动分类选择成功: catName=%s, catId=%s, score=%.4f, margin=%.4f",
            selected.get("catName", ""), selected.get("catId", ""),
            top1_score, margin,
        )
        return {
            "auto_select": True,
            "reason": "自动选择成功",
            "category": selected,
            "candidates": candidates,
        }

    return _no_category_result("CATEGORY_NO_CANDIDATES", candidates)


def _no_category_result(reason: str = "", candidates: Optional[List[dict]] = None) -> dict:
    """返回无分类结果"""
    return {
        "auto_select": False,
        "reason": reason,
        "category": None,
        "candidates": candidates or [],
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全地转换为 float"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ==================== 主入口 ====================


def auto_category(
    cookie_str: str,
    image_data: bytes,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    自动分类主入口。

    Args:
        cookie_str: 闲鱼账号 Cookie
        image_data: 封面图二进制数据
        title: 商品标题（可选）
        description: 商品描述（可选）

    Returns:
        {
            "success": bool,
            "source": str,  # "xianyu_auto" | "local_category" | "manual"
            "autoSelected": bool,
            "selectedCategory": dict | None,
            "candidates": list,
            "cdnImageUrl": str | None,
            "fallbackRequired": bool,
            "fallbackReason": str | None,
        }
    """
    start_time = time.time()
    logger.info("开始自动分类流程, image_data_size=%d字节", len(image_data))

    # 检查 Cookie
    token = _get_token_from_cookie(cookie_str)
    if not token:
        logger.warning("Cookie 中缺少 _m_h5_tk")
        return _build_response(
            success=False, source="manual", auto_selected=False,
            fallback_required=True, fallback_reason="COOKIE_MISSING_M_H5_TK",
        )

    # 步骤 1: 上传图片到闲鱼 CDN
    try:
        cdn_url, width, height = upload_image_to_xianyu(cookie_str, image_data)
        logger.info("步骤1-图片上传CDN成功, 耗时=%.2fs", time.time() - start_time)
    except Exception:
        error_msg = "UPLOAD_FAILED"
        logger.error("步骤1-图片上传 CDN 失败", exc_info=True)
        return _build_response(
            success=False, source="local_category", auto_selected=False,
            fallback_required=True, fallback_reason=error_msg,
            cdn_image_url=None,
        )

    # 步骤 2: 调用分类推荐接口
    try:
        recommend_result = call_category_recommend(cookie_str, cdn_url, width, height)
        logger.info("步骤2-分类推荐接口调用成功, 耗时=%.2fs", time.time() - start_time)
    except Exception:
        error_msg = "CATEGORY_RECOMMEND_UNAVAILABLE"
        logger.error("步骤2-分类推荐接口调用失败", exc_info=True)
        return _build_response(
            success=False, source="local_category", auto_selected=False,
            fallback_required=True, fallback_reason=error_msg,
            cdn_image_url=cdn_url,
        )

    # 步骤 3: 自动选择最佳分类
    try:
        selection = select_best_category(recommend_result)
        logger.info(
            "步骤3-分类选择结果: auto_select=%s, reason=%s, 候选数=%d, 耗时=%.2fs",
            selection["auto_select"], selection["reason"],
            len(selection.get("candidates", [])),
            time.time() - start_time,
        )
    except Exception:
        error_msg = "CATEGORY_SELECTION_FAILED"
        logger.error("步骤3-分类选择异常", exc_info=True)
        return _build_response(
            success=False, source="manual", auto_selected=False,
            fallback_required=True, fallback_reason=error_msg,
            cdn_image_url=cdn_url,
        )

    if selection["auto_select"]:
        elapsed = time.time() - start_time
        logger.info(
            "自动分类成功: category=%s, candidates=%d, 总耗时=%.2fs",
            selection["category"].get("catName", "") if selection["category"] else "",
            len(selection["candidates"]),
            elapsed,
        )
        return _build_response(
            success=True, source="xianyu_auto", auto_selected=True,
            selected_category=selection["category"],
            candidates=selection["candidates"],
            cdn_image_url=cdn_url,
        )

    # 自动选择失败，需要 fallback
    logger.warning(
        "自动分类未达到置信度阈值: reason=%s, candidates=%d",
        selection["reason"], len(selection.get("candidates", [])),
    )
    return _build_response(
        success=False, source="local_category", auto_selected=False,
        fallback_required=True, fallback_reason=selection["reason"],
        candidates=selection.get("candidates", []),
        cdn_image_url=cdn_url,
    )


def _build_response(
    success: bool,
    source: str,
    auto_selected: bool,
    fallback_required: bool = False,
    fallback_reason: Optional[str] = None,
    selected_category: Optional[dict] = None,
    candidates: Optional[List[dict]] = None,
    cdn_image_url: Optional[str] = None,
) -> dict:
    """构建统一响应"""
    return {
        "success": success,
        "source": source,
        "autoSelected": auto_selected,
        "selectedCategory": selected_category,
        "candidates": candidates or [],
        "cdnImageUrl": cdn_image_url,
        "fallbackRequired": fallback_required,
        "fallbackReason": fallback_reason,
        "raw": None,
    }
