"""Parser 抽象基类 + ParsedOutput 数据结构。

设计要点:
- Parser 只负责从 LLM 文本中提取结构化信息
- 解析失败返回 ParseError (不抛异常), 由 Loop 控制器喂回 LLM
- Action 使用独立的 Action 数据结构 (而非散落的 tool_name/args 字段)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent.core.schemas.action import Action


@dataclass
class ParsedOutput:
    """Parser 的统一输出类型。

    四种类型:
    - thought:       LLM 的推理过程 (纯文本)
    - action:        LLM 想调用工具 (包含结构化的 Action)
    - final_answer:  LLM 认为任务完成
    - parse_error:   格式无法解析, 需要 LLM 修正
    """

    type: str  # "thought" | "action" | "final_answer" | "parse_error"
    content: str = ""
    action: Action | None = None
    error_reason: str = ""

    # LLM 的思考文本 — XMLParser 在解析 action/final_answer 时同步提取
    # 面向日志记录，不参与 Loop 决策
    # 命名为 thought_text 而非 thought，避免和工厂方法名冲突 (getattr 陷阱)
    thought_text: str = ""

    # ---- 工厂方法 ----

    @classmethod
    def thought_output(cls, text: str) -> "ParsedOutput":
        """创建 thought 类型输出。"""
        return cls(type="thought", content=text, thought_text=text)

    @classmethod
    def action_output(cls, action: Action, thought_text: str = "") -> "ParsedOutput":
        """创建 action 类型输出。"""
        return cls(type="action", action=action, thought_text=thought_text)

    @classmethod
    def final_answer(cls, text: str, thought_text: str = "") -> "ParsedOutput":
        """创建 final_answer 类型输出。"""
        return cls(type="final_answer", content=text, thought_text=thought_text)

    @classmethod
    def parse_error(cls, reason: str) -> "ParsedOutput":
        return cls(type="parse_error", error_reason=reason)


class Parser(ABC):
    """Parser 抽象基类。实现新的 Parser 只需继承此类。"""

    @abstractmethod
    def parse(self, raw_text: str) -> ParsedOutput:
        """解析 LLM 原始输出, 返回 ParsedOutput。"""
        ...
