"""Agent 主类 — 将所有模块组装成完整的 SWE Agent。

这是整个项目的编排层。每个模块职责单一:
- PromptManager → 组装 prompt
- LLMClient → 调用 LLM
- Parser → 解析 LLM 输出
- LoopController → 管理状态和循环
- Tools → 执行具体操作
- CommandChecker → 高危命令拦截
- AgentLogger → 记录日志
"""

import os
from typing import Any

from agent.core.parser.base import Parser, ParsedOutput
from agent.core.parser.xml_parser import XMLParser
from agent.core.schemas.action import Action
from agent.core.prompt import PromptManager
from agent.core.loop import LoopController, AgentStatus, LoopConfig
from agent.tools.base import Tool, ToolResult
from agent.tools.terminal import RunTerminal
from agent.tools.file_ops import ReadFile, WriteFile, SearchContent
from agent.checker.command_checker import CommandChecker
from agent.checker.logger import AgentLogger
from agent.llm.client import LLMClient


class SWEAgent:
    """Minimal SWE Agent。

    Usage:
        agent = SWEAgent(working_directory="/path/to/project")
        agent.run("找到所有 TODO 注释并列出它们")
        agent.run("现在修复这些 TODO")  # 同一实例可多次调用, 每次自动重置状态
    """

    def __init__(
        self,
        working_directory: str,
        parser: Parser | None = None,
        loop_config: LoopConfig | None = None,
        requires_command_confirm: bool = True,
    ):
        self.working_directory = os.path.abspath(working_directory)
        self._loop_config = loop_config or LoopConfig()

        # 长生命周期模块 (不随 run() 重置)
        self.prompt_manager = PromptManager(self.working_directory)
        self.llm = LLMClient()
        self.parser = parser or XMLParser()
        self.command_checker = CommandChecker()
        self.requires_command_confirm = requires_command_confirm

        # 短生命周期模块 (构造时创建, 每次 run() 重置)
        self.loop: LoopController = LoopController(self._loop_config)
        self.logger: AgentLogger = AgentLogger()

        # 注册工具
        self.tools: list[Tool] = [
            ReadFile(),
            WriteFile(),
            SearchContent(),
            RunTerminal(),
        ]
        self._tool_map = {t.name: t for t in self.tools}

    def run(self, user_input: str) -> str:
        """运行 Agent，返回最终答案。

        每次调用自动重置 loop 和 logger 状态，支持同一实例多次调用。
        """
        # 每次 run() 重置 loop 状态、创建新的 logger, 确保同一实例多次调用互不污染
        # 注意: loop 刚重置完就是 THINKING 状态, 不要再调用 transition_to(THINKING)
        # (THINKING → THINKING 不在合法转换白名单中, 会抛 ValueError)
        self.loop.reset()
        self.logger = AgentLogger()

        # 构建初始 messages
        messages: list[dict] = [
            {
                "role": "system",
                "content": self.prompt_manager.render_system_prompt(self.tools),
            },
            {
                "role": "user",
                "content": self.prompt_manager.render_user_message(user_input),
            },
        ]

        while self.loop.status not in (
            AgentStatus.DONE, AgentStatus.STUCK, AgentStatus.CANCELLED
        ):
            # 检查终止条件
            should_stop, reason = self.loop.check_done()
            if should_stop:
                print(f"\n  [{reason}]")
                self.logger.log_turn(
                    self.loop.turn, thought="", action="", observation=reason
                )
                return f"Agent 终止: {reason}"

            if self.loop.status == AgentStatus.THINKING:
                self._handle_thinking(messages)

            elif self.loop.status == AgentStatus.ACTING:
                self._handle_acting(messages)

        return self._finalize()

    def _handle_thinking(self, messages: list[dict]) -> None:
        """处理 THINKING 状态: 调用 LLM → 解析输出 → 决定下一步。"""
        is_parse_retry = self.loop.parse_errors > 0
        if not is_parse_retry:
            self.loop.next_turn()

        print(f"\n{'='*60}")
        print(f"第 {self.loop.turn} 轮 (THINKING)")

        # 1. 调用 LLM
        print("  [请求 LLM...]")
        raw_output = self.llm.chat(messages)
        messages.append({"role": "assistant", "content": raw_output})

        # 2. 解析输出
        parsed = self.parser.parse(raw_output)

        # 3. 处理解析结果
        error_msg = self.loop.handle_parse_result(parsed)
        if error_msg:
            print(f"  [解析失败] {error_msg}")
            messages.append({"role": "user", "content": error_msg})
            return  # 保持 THINKING 状态，让 LLM 修正

        # 4. 根据解析结果行动
        if parsed.type == "thought":
            print(f"  [Thought] {parsed.content[:200]}...")
            # LLM 只输出了 thought 就停止 (常见于输出被截断)
            # 提示其继续输出 action 或 final_answer
            messages.append({
                "role": "user",
                "content": (
                    "你只输出了 <thought> 就停止了。"
                    "请继续输出 <action> 执行操作，或输出 <final_answer> 完成任务。"
                ),
            })
            return  # 保持 THINKING 状态

        elif parsed.type == "final_answer":
            print(f"  [Final Answer] {parsed.content[:200]}...")
            self.loop.transition_to(AgentStatus.DONE)
            self.logger.log_turn(
                self.loop.turn,
                thought=parsed.thought_text,
                final_answer=parsed.content,
            )
            return

        elif parsed.type == "action":
            action = parsed.action
            print(f"  [Action] {action}")
            self._pending_action = parsed
            self.loop.transition_to(AgentStatus.ACTING)

    def _handle_acting(self, messages: list[dict]) -> None:
        """处理 ACTING 状态: 检查安全性 → 执行工具 → 注入 observation → 回到 THINKING。"""
        parsed: ParsedOutput = self._pending_action
        action: Action = parsed.action
        tool_name = action.tool_name
        tool_args = action.arguments

        # 1. 查找工具
        tool = self._tool_map.get(tool_name)
        if tool is None:
            observation = (
                f"未知工具: '{tool_name}'。"
                f"可用工具: {', '.join(self._tool_map.keys())}。"
            )
            print(f"  [错误] {observation}")
        else:
            # 2. 终端命令特殊处理: 高危检查 + 用户确认
            if tool_name == "run_terminal":
                command = tool_args.get("command", "")

                # 高危检查
                danger = self.command_checker.check(command)
                if danger.is_dangerous:
                    print(f"\n  ⚠️  高危命令检测: {danger.reason}")
                    print(f"  命令: {command}")
                    if self.requires_command_confirm:
                        confirm = input("  是否执行? (y/N): ").strip().lower()
                    else:
                        confirm = "y"
                    if confirm != "y":
                        observation = f"用户拒绝了高危命令: {command}"
                        messages.append({
                            "role": "user",
                            "content": f"<observation>{observation}</observation>",
                        })
                        self.loop.transition_to(AgentStatus.THINKING)
                        self.logger.log_turn(
                            self.loop.turn,
                            thought=parsed.thought_text,
                            action=f"{tool_name}({tool_args})",
                            observation=observation,
                        )
                        return

                # 常规确认
                elif self.requires_command_confirm:
                    print(f"\n  命令: {command}")
                    confirm = input("  是否执行? (y/N): ").strip().lower()
                    if confirm != "y":
                        observation = f"用户取消了命令: {command}"
                        messages.append({
                            "role": "user",
                            "content": f"<observation>{observation}</observation>",
                        })
                        self.loop.transition_to(AgentStatus.THINKING)
                        self.logger.log_turn(
                            self.loop.turn,
                            thought=parsed.thought_text,
                            action=f"{tool_name}({tool_args})",
                            observation=observation,
                        )
                        return

            # 3. 执行工具
            print(f"  [执行 {tool_name}...]")
            result: ToolResult = tool.execute(**tool_args)
            observation = result.to_observation()

            if result.success:
                print(f"  [成功] {observation[:150]}...")
            else:
                print(f"  [失败] {observation[:150]}...")

        # 4. 兜圈子检测 — 联合比对 action + observation
        action_key = f"{tool_name}({tool_args})"
        loop_warning = self.loop.record_action(
            action_key, observation_summary=observation
        )
        if loop_warning:
            observation = loop_warning + "\n\n原始结果:\n" + observation
            print(f"  [兜圈子检测] {loop_warning}")

        # 5. 注入 observation
        messages.append({
            "role": "user",
            "content": f"<observation>{observation}</observation>",
        })

        # 6. 记录日志 — 传递 thought_text 字段
        self.logger.log_turn(
            self.loop.turn,
            thought=parsed.thought_text,
            action=action_key,
            observation=observation,
        )

        # 7. 回到 THINKING 状态
        # 兜圈子检测可能已将状态置为 STUCK (终态, 不可再跳转), 此时跳过转换
        if self.loop.status != AgentStatus.STUCK:
            self.loop.transition_to(AgentStatus.THINKING)

    def _finalize(self) -> str:
        """收尾: 打印日志摘要, 返回最终结果。"""
        print(self.logger.get_summary())

        # 从日志中提取最后一个 final_answer
        for turn in reversed(self.logger.turns):
            if turn.final_answer:
                return turn.final_answer

        if self.loop.status == AgentStatus.STUCK:
            return "Agent 陷入死循环, 已强制终止"

        if self.loop.turn >= self.loop.config.max_turns:
            return "任务未完成 (达到最大轮次限制)"

        return "任务已终止"
