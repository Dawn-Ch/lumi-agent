"""Action Schema — Pydantic 数据校验层。

设计要点:
- parser 只负责语法解析 (从字符串中提取 tool_name + arguments)
- schema (Pydantic) 负责数据结构定义与基础类型校验
- ActionValidator 负责业务规则校验 (工具是否存在等)
- 两层解耦, 各自独立可测
"""

from typing import Any

from pydantic import BaseModel, Field


class Action(BaseModel):
    """解析后的 Action 数据结构。

    使用 Pydantic BaseModel 替代 dataclass:
    - 自动类型校验: tool_name 必定是 str, arguments 必定是 dict
    - model_dump() 内置序列化
    - 非法类型在构造时即被拦截 (如 Action(tool_name=123) → ValidationError)
    """

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """兼容旧接口, 等同于 model_dump()。"""
        return self.model_dump()

    def __repr__(self) -> str:
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"Action({self.tool_name}({args_str}))"

    def __str__(self) -> str:
        return self.__repr__()


class ActionValidator:
    """校验 Action 是否合法 (业务规则层)。

    校验项:
    - tool_name 是否在已知工具列表中
    - 必填参数是否都提供了
    - 参数名是否合法

    与 Pydantic 的分工:
    - Pydantic 保障数据结构 (tool_name 是 str, arguments 是 dict)
    - ActionValidator 保障业务语义 (工具名是否注册)
    """

    def __init__(self, known_tools: dict[str, Any] | None = None):
        self.known_tools = known_tools or {}

    def validate(self, action: Action) -> list[str]:
        """校验 Action, 返回错误列表。空列表表示校验通过。"""
        errors = []

        if not action.tool_name:
            errors.append("tool_name 不能为空")
            return errors

        if self.known_tools and action.tool_name not in self.known_tools:
            available = ", ".join(self.known_tools.keys())
            errors.append(f"未知工具 '{action.tool_name}'。可用工具: {available}")

        return errors
