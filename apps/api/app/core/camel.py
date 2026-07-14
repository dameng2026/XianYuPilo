from typing import Any
from pydantic import BaseModel, ConfigDict


def to_camel(snake: str) -> str:
    """将 snake_case 转换为 camelCase"""
    if not snake or '_' not in snake:
        return snake
    first, *rest = snake.split('_')
    return first + ''.join(word.capitalize() for word in rest)


class CamelModel(BaseModel):
    """基类模型，自动在序列化时将 snake_case 字段名转换为 camelCase"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault('by_alias', True)
        return super().model_dump(*args, **kwargs)
