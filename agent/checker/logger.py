"""Logger — 记录 Agent 运行日志。

设计要点:
- 记录每一轮的 thought, action, observation (debug 的关键来源)
- 记录工具调用的时间、参数、结果
"""

import time
from dataclasses import dataclass, field


@dataclass
class TurnLog:
    """单轮循环的日志记录。"""
    turn_number: int
    timestamp: float
    thought: str = ""
    action: str = ""
    observation: str = ""
    final_answer: str = ""


class AgentLogger:
    """Agent 运行日志器。"""

    def __init__(self):
        self.turns: list[TurnLog] = []
        self._start_time = time.time()

    def log_turn(self, turn_number: int, **kwargs) -> None:
        """记录一轮循环。"""
        self.turns.append(TurnLog(
            turn_number=turn_number,
            timestamp=time.time(),
            **kwargs,
        ))

    def get_summary(self) -> str:
        """生成运行摘要。"""
        lines = [f"\n{'='*60}", "Agent 运行摘要", f"{'='*60}"]
        lines.append(f"总轮次: {len(self.turns)}")
        lines.append(f"总耗时: {time.time() - self._start_time:.1f}s")

        for turn in self.turns:
            lines.append(f"\n--- 第 {turn.turn_number} 轮 ---")
            if turn.thought:
                lines.append(f"  Thought: {turn.thought[:100]}...")
            if turn.action:
                lines.append(f"  Action: {turn.action}")
            if turn.observation:
                # 截断过长的 observation
                obs = turn.observation[:200].replace("\n", " ")
                lines.append(f"  Observation: {obs}...")
            if turn.final_answer:
                lines.append(f"  Final Answer: {turn.final_answer[:200]}...")

        return "\n".join(lines)
