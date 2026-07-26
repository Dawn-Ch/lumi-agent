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
import sys
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
    """

    def __init__(
        self,
        working_directory: str,
        parser: Parser | None = None,
        loop_config: LoopConfig | None = None,
        requires_command_confirm: bool = True,
    ):
        self.working_directory = os.path.abspath(working_directory)

        # 初始化所有模块
        self.prompt_manager = PromptManager(self.working_directory)
        self.llm = LLMClient()
        self.parser = parser or XMLParser()
        self.loop = LoopController(loop_config)
        self.logger = AgentLogger()
        self.command_checker = CommandChecker()
        self.requires_command_confirm = requires_command_confirm

        # 注册工具
        self.tools: list[Tool] = [
            ReadFile(),
            WriteFile(),
            SearchContent(),
            RunTerminal(),
        ]
        self._tool_map = {t.name: t for t in self.tools}

    def run(self, user_input: str) -> str:
        """运行 Agent，返回最终答案。"""

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

        self.loop.transition_to(AgentStatus.THINKING)

        while self.loop.status not in (AgentStatus.DONE, AgentStatus.CANCELLED):
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
            # 解析失败 — 把错误信息喂回 LLM
            print(f"  [解析失败] {error_msg}")
            messages.append({"role": "user", "content": error_msg})
            return  # 保持 THINKING 状态，让 LLM 修正

        # 4. 根据解析结果行动
        if parsed.type == "thought":
            print(f"  [Thought] {parsed.content[:200]}...")
            # 纯 thought (没有 action) — 已经由 Parser 转为 parse_error 了
            return

        elif parsed.type == "final_answer":
            print(f"  [Final Answer] {parsed.content[:200]}...")
            self.loop.transition_to(AgentStatus.DONE)
            self.logger.log_turn(
                self.loop.turn, final_answer=parsed.content
            )
            return

        elif parsed.type == "action":
            action = parsed.action
            print(f"  [Action] {action}")
            # 将 action 信息暂存，供 ACTING 状态使用
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
                            action=f"{tool_name}({tool_args})",
                            observation=observation,
                        )
                        return

                # 常规确认 (非高危终端命令也需要确认，安全起见)
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

        # 4. 兜圈子检测
        action_key = f"{tool_name}({tool_args})"
        loop_warning = self.loop.record_action(action_key)
        if loop_warning:
            observation = loop_warning + "\n\n原始结果:\n" + observation
            print(f"  [兜圈子检测] {loop_warning}")

        # 5. 注入 observation
        messages.append({
            "role": "user",
            "content": f"<observation>{observation}</observation>",
        })

        # 6. 记录日志
        # 注意: 不能用 getattr(parsed, 'thought', '') — ParsedOutput.thought 是 classmethod
        self.logger.log_turn(
            self.loop.turn,
            thought="",
            action=action_key,
            observation=observation,
        )

        # 7. 回到 THINKING 状态
        self.loop.transition_to(AgentStatus.THINKING)

    def _finalize(self) -> str:
        """收尾: 打印日志摘要, 返回最终结果。"""
        print(self.logger.get_summary())

        # 从 messages 中提取最后一个 final_answer (如果有的话)
        for msg in reversed(self.logger.turns):
            if msg.final_answer:
                return msg.final_answer

        if self.loop.turn >= self.loop.config.max_turns:
            return "任务未完成 (达到最大轮次限制)"
        return "任务已终止"
