"""
SSE 事件广播模块。

提供应用内的事件广播机制，让 SSE 端点可以接收并推送业务事件。
"""

import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SSEBroadcaster:
    """SSE 事件广播器。
    
    管理所有活跃的 SSE 订阅者，支持推送业务事件到所有订阅者。
    """
    
    def __init__(self, max_subscribers: int = 100):
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._max_subscribers = max(1, int(max_subscribers))
    
    async def subscribe(self, subscriber_id: str) -> asyncio.Queue:
        """订阅事件，返回一个队列用于接收事件。
        
        Args:
            subscriber_id: 订阅者唯一标识
            
        Returns:
            事件队列
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            if (
                subscriber_id not in self._subscribers
                and len(self._subscribers) >= self._max_subscribers
            ):
                raise RuntimeError("SSE_SUBSCRIBER_CAPACITY_REACHED")
            self._subscribers[subscriber_id] = queue
        logger.debug("SSE 订阅者 %s 已注册，当前订阅者数: %d", subscriber_id, len(self._subscribers))
        return queue
    
    async def unsubscribe(self, subscriber_id: str):
        """取消订阅。
        
        Args:
            subscriber_id: 订阅者唯一标识
        """
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)
        logger.debug("SSE 订阅者 %s 已注销", subscriber_id)
    
    async def broadcast(self, event_type: str, data: dict[str, Any]):
        """广播事件到所有订阅者。
        
        Args:
            event_type: 事件类型（如 "message", "heartbeat"）
            data: 事件数据
        """
        payload = {
            "type": event_type,
            **data,
        }
        message = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        
        async with self._lock:
            dead_subs = []
            for sub_id, queue in self._subscribers.items():
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    # 队列满了，丢弃最旧的事件
                    try:
                        queue.get_nowait()
                        queue.put_nowait(message)
                    except asyncio.QueueEmpty:
                        dead_subs.append(sub_id)
            for sub_id in dead_subs:
                self._subscribers.pop(sub_id, None)
        
        logger.debug("SSE 广播 %s 事件到 %d 个订阅者", event_type, len(self._subscribers))
    
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# 全局 SSE 广播器实例
broadcaster = SSEBroadcaster()
