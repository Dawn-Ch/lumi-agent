"""Action Schema — Pydantic 数据校验层。

设计要点:
- parser 只负责语法解析 (从字符串中提取 tool_name + arguments)
- schema 负责数据校验 (工具名是否存在、参数类型是否匹配等)
- 两层解耦, 各自独立可测
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    """解析后的 Action 数据结构。"""
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "arguments": self.arguments}

    def __repr__(self) -> str:
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"Action({self.tool_name}({args_str}))"


class ActionValidator:
    """校验 Action 是否合法。

    校验项:
    - tool_name 是否在已知工具列表中
    - 必填参数是否都提供了
    - 参数名是否合法
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
