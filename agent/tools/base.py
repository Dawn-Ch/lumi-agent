"""Tool 基类 — 所有工具的抽象接口。

设计要点:
- 每个 Tool 有 name, description, parameters (JSON Schema 格式)
- execute() 统一返回 ToolResult (包含 success, output, error)
- 新工具只需继承 Tool 类, Agent 代码零改动
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果。统一格式,不管成功还是失败都返回这个。"""
    success: bool
    output: str = ""
    error: str = ""

    def to_observation(self) -> str:
        """转为注入 messages 的 observation 文本。"""
        if self.success:
            return self.output
        return f"错误: {self.error}"


class Tool(ABC):
    """工具的抽象基类。

    子类只需要实现 execute() 方法。
    name / description / parameters 作为类属性定义。
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具,返回 ToolResult。子类必须实现。"""
        ...

    def to_prompt_description(self) -> str:
        """生成给 LLM 看的工具描述 (注入 system prompt 用)。"""
        params_desc = ""
        for pname, pinfo in self.parameters.items():
            required = " (必填)" if pinfo.get("required", False) else ""
            params_desc += f"    - {pname}: {pinfo.get('type', 'any')} — {pinfo.get('description', '')}{required}\n"

        return f"- {self.name}: {self.description}\n  参数:\n{params_desc}"
