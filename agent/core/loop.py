"""Loop 控制器 + 状态机 — Agent 运行时的核心调度器。

设计要点:
- 状态机: THINKING → ACTING → THINKING → ... → DONE
- 状态转换有合法性校验 (非法跳转抛异常)
- ParseError 自动喂回 LLM 修正 (不计入 max_turns 的正常轮次)
- 兜圈子检测: 最近 N 个 (action, observation) 完全相同 → 警告 LLM
- 连续 STUCK 警告超限 → 强制终止
"""

from dataclasses import dataclass
from enum import Enum, auto

from agent.core.parser.base import ParsedOutput


class AgentStatus(Enum):
    """Agent 状态机的状态。"""
    THINKING = auto()   # 等待 LLM 输出
    ACTING = auto()     # 执行工具中
    DONE = auto()       # 任务完成或异常终止
    STUCK = auto()      # 兜圈子无法跳出, 强制终止
    CANCELLED = auto()  # 用户取消


# 合法状态转换白名单
_VALID_TRANSITIONS: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.THINKING:  frozenset({AgentStatus.ACTING, AgentStatus.DONE, AgentStatus.CANCELLED}),
    AgentStatus.ACTING:    frozenset({AgentStatus.THINKING, AgentStatus.CANCELLED}),
    AgentStatus.DONE:      frozenset(),          # 终态, 不可跳转
    AgentStatus.STUCK:     frozenset(),          # 终态, 不可跳转
    AgentStatus.CANCELLED: frozenset(),          # 终态, 不可跳转
}


@dataclass
class LoopConfig:
    """Loop 控制器的配置。"""
    max_turns: int = 50
    duplicate_action_limit: int = 3   # 连续相同 (action, observation) 多少次触发警告
    stuck_warning_limit: int = 2     # 连续 stuck 警告多少次 → 强制 STUCK 终止
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
        self.stuck_warnings: int = 0

        # 兜圈子检测: 记录最近 N 个 (action_str, observation_summary) 对
        self.recent_action_obs: list[tuple[str, str]] = []

    def reset(self) -> None:
        """重置所有状态 (用于新一轮 run())。"""
        self.status = AgentStatus.THINKING
        self.turn = 0
        self.parse_errors = 0
        self.stuck_warnings = 0
        self.recent_action_obs.clear()

    def next_turn(self) -> None:
        """进入下一轮。"""
        self.turn += 1

    def check_done(self) -> tuple[bool, str]:
        """检查循环是否应该终止。

        返回 (should_stop, reason)。
        """
        if self.status == AgentStatus.STUCK:
            return True, f"Agent 陷入死循环被强制终止 (连续 {self.stuck_warnings} 次重复操作)"

        if self.turn >= self.config.max_turns:
            self.status = AgentStatus.DONE
            return True, f"达到最大轮次数 ({self.config.max_turns})"

        if self.parse_errors >= self.config.parse_error_limit:
            self.status = AgentStatus.DONE
            return True, f"连续解析失败 {self.parse_errors} 次，强制终止"

        return False, ""

    def transition_to(self, new_status: AgentStatus) -> None:
        """状态转换 (有合法性校验)。

        非法转换抛出 ValueError。
        """
        allowed = _VALID_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {self.status.name} → {new_status.name}。"
                f"从 {self.status.name} 只能跳转到: "
                f"{', '.join(s.name for s in allowed) or '(无 — 终态)'}"
            )
        self.status = new_status

    def record_action(self, action_str: str, observation_summary: str = "") -> str | None:
        """记录 (action, observation) 对，检测是否兜圈子。

        返回警告消息 (如果检测到兜圈子)，否则返回 None。

        改进点:
        - 同时比对 action 和 observation，避免"同一个 action + 不同 observation"被误判
        - stuck_warnings 只在连续重复时累计; 一旦窗口内出现不同操作, 计数清零
        - 连续 stuck 超限 → 进入 STUCK 终态
        """
        pair = (action_str, observation_summary[:200])  # 截断 obs 用于比对
        self.recent_action_obs.append(pair)

        # 只保留最近 N 个
        limit = self.config.duplicate_action_limit
        if len(self.recent_action_obs) > limit:
            self.recent_action_obs.pop(0)

        # 检查最近 N 个 (action, observation) 是否完全相同
        is_duplicate = (
            len(self.recent_action_obs) >= limit
            and len(set(self.recent_action_obs)) == 1
        )

        if not is_duplicate:
            # 窗口内出现不同操作 → 说明已跳出上一个循环, 计数清零
            self.stuck_warnings = 0
            return None

        # 连续重复 → 累计警告
        self.stuck_warnings += 1

        # 超限 → STUCK 终态
        if self.stuck_warnings >= self.config.stuck_warning_limit:
            self.status = AgentStatus.STUCK
            return (
                f"警告: 你已经连续 {limit} 次执行了相同的操作 '{action_str}' "
                f"且得到了相同的结果。已连续 {self.stuck_warnings} 次警告，"
                f"触发 STUCK 终止。最后执行的操作和结果:\n"
                f"  Action: {action_str}\n"
                f"  Observation: {observation_summary[:300]}"
            )

        return (
            f"警告 ({self.stuck_warnings}/{self.config.stuck_warning_limit}): "
            f"你已经连续 {limit} 次执行了相同的操作 '{action_str}'，"
            f"且得到了相同的结果。这说明你可能在兜圈子。请换一种方法，"
            f"或检查之前的 observation 是否有你遗漏的信息。"
            f"如果确实无法完成任务，请输出 final_answer 说明情况。"
        )

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
