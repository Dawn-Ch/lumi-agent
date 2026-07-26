"""Loop 控制器 + 状态机 — Agent 运行时的核心调度器。

设计要点:
- 状态机: THINKING → ACTING → THINKING → ... → DONE
- 每个状态明确接受什么 ParsedOutput
- ParseError 自动喂回 LLM 修正 (不计入 max_turns 的正常轮次)
- 兜圈子检测: 最近 N 个 action 完全相同 → 警告 LLM
"""

from dataclasses import dataclass
from enum import Enum, auto

from agent.core.parser.base import ParsedOutput


class AgentStatus(Enum):
    """Agent 状态机的状态。"""
    THINKING = auto()   # 等待 LLM 输出
    ACTING = auto()     # 执行工具中
    DONE = auto()       # 任务完成或异常终止
    CANCELLED = auto()  # 用户取消


@dataclass
class LoopConfig:
    """Loop 控制器的配置。"""
    max_turns: int = 50
    duplicate_action_limit: int = 3   # 连续相同 action 多少次触发警告
    parse_error_limit: int = 3        # 连续解析失败多少次强制终止


class LoopController:
    """Agent 主循环的控制器。

    管理状态机、轮次计数、兜圈子检测、解析失败处理。
    """

    def __init__(self, config: LoopConfig | None = None):
        self.config = config or LoopConfig()
        self.status: AgentStatus = AgentStatus.THINKING
        self.turn: int = 0
        self.parse_errors: int = 0
        self.recent_actions: list[str] = []  # 最近 N 次 action, 用于兜圈子检测

    def next_turn(self) -> None:
        """进入下一轮。"""
        self.turn += 1

    def check_done(self) -> tuple[bool, str]:
        """检查循环是否应该终止。

        返回 (should_stop, reason)。
        """
        if self.turn >= self.config.max_turns:
            self.status = AgentStatus.DONE
            return True, f"达到最大轮次数 ({self.config.max_turns})"

        if self.parse_errors >= self.config.parse_error_limit:
            self.status = AgentStatus.DONE
            return True, f"连续解析失败 {self.parse_errors} 次，强制终止"

        return False, ""

    def transition_to(self, new_status: AgentStatus) -> None:
        """状态转换。"""
        self.status = new_status

    def record_action(self, action_str: str) -> str | None:
        """记录 action，检测是否兜圈子。

        返回警告消息 (如果检测到兜圈子)，否则返回 None。
        """
        self.recent_actions.append(action_str)

        # 只保留最近 N 个
        if len(self.recent_actions) > self.config.duplicate_action_limit:
            self.recent_actions.pop(0)

        # 检查最近 N 个是否完全相同
        if len(self.recent_actions) >= self.config.duplicate_action_limit:
            if len(set(self.recent_actions)) == 1:
                return (
                    f"警告: 你已经连续 {self.config.duplicate_action_limit} 次执行了相同的操作 "
                    f"'{action_str}'。这说明你可能在兜圈子。请换一种方法，或检查之前的 observation "
                    f"是否有你遗漏的信息。如果确实无法完成任务，请输出 final_answer 说明情况。"
                )
        return None

    def handle_parse_result(self, parsed: ParsedOutput) -> str | None:
        """处理 Parser 的输出结果。

        返回应该以 observation 形式注入 messages 的文本。
        如果返回 None，说明 parsed 是正常的 Thought/Action/FinalAnswer，不需要注入。
        """
        if parsed.type == "parse_error":
            self.parse_errors += 1
            return f"格式错误 ({self.parse_errors}/{self.config.parse_error_limit}): {parsed.error_reason}\n请修正格式后重新输出。"
        else:
            # 解析成功，重置错误计数
            self.parse_errors = 0
            return None
