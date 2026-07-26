"""Prompt Manager — 组装和渲染发送给 LLM 的 prompt。

设计要点:
- 系统 prompt 和工具描述分离 (工具列表动态注入)
- 环境信息 (OS, 工作目录, 文件列表) 在运行时注入
- 模板使用 Python 原生字符串拼接 (简单直接, 不需要引入模板引擎)
"""

from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.base import Tool


SYSTEM_PROMPT_TEMPLATE = Template("""\
你是一个软件工程 Agent，负责通过执行工具来解决编程任务。

## 工作方式
对于每个任务，使用以下循环模式:
1. <thought> — 分析当前状态，推理下一步该做什么
2. <action> — 调用一个工具来执行操作
3. 你会收到 <observation> — 工具执行的实际结果
4. 重复这个循环，直到任务完成
5. <final_answer> — 任务完成时给出最终答案

## 重要规则
- 每次回复必须包含 <thought> + <action> 或 <thought> + <final_answer>
- 输出 <action> 后立即停止，等待真实的环境反馈
- 不要自己编造 observation! 等待真正的工具执行结果
- 文件路径必须使用绝对路径
- 如果你连续 3 次执行了相同的操作，说明你在兜圈子，请换一种方法
- 操作前先理解当前状态: 先读文件再改文件，先 ls 再 cd

## 可用工具
${tool_list}

## 环境信息
- 操作系统: ${operating_system}
- 工作目录: ${working_directory}
- 工作目录下的文件: ${file_list}
""")


USER_MESSAGE_TEMPLATE = Template("""\
<question>${user_input}</question>
""")


class PromptManager:
    """管理 prompt 的组装和渲染。"""

    def __init__(self, working_directory: str):
        self.working_directory = working_directory

    def render_system_prompt(self, tools: list["Tool"]) -> str:
        """渲染系统 prompt,注入工具列表和环境信息。"""
        import os
        import platform

        tool_list = "\n".join(t.to_prompt_description() for t in tools)

        try:
            files = os.listdir(self.working_directory)
        except OSError:
            files = ["(无法读取目录)"]
        file_list = ", ".join(files[:50])  # 限制数量，避免 prompt 过长

        os_map = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}
        operating_system = os_map.get(platform.system(), "Unknown")

        return SYSTEM_PROMPT_TEMPLATE.substitute(
            tool_list=tool_list,
            operating_system=operating_system,
            working_directory=self.working_directory,
            file_list=file_list,
        )

    def render_user_message(self, user_input: str) -> str:
        """渲染用户输入消息。"""
        return USER_MESSAGE_TEMPLATE.substitute(user_input=user_input)
