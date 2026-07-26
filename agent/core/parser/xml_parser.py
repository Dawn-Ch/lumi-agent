"""XMLParser — 基于 XML 标签的 LLM 输出解析器。

解析流程:
1. 用正则提取 <thought>, <action>, <final_answer> 标签
2. <action> 内的字符串交给 ASTActionParser 解析 (不再手写状态机)
3. 解析失败统一返回 ParseError (喂回 LLM 修正)
"""

import re

from agent.core.parser.base import Parser, ParsedOutput
from agent.core.parser.ast_parser import ASTActionParser


class XMLParser(Parser):
    """基于 XML 标签的 Parser。

    LLM 输出格式:
    <thought>思考内容</thought>
    <action>tool_name(arg1="v1", arg2="v2")</action>
    或
    <thought>思考内容</thought>
    <final_answer>最终答案</final_answer>
    """

    def __init__(self):
        self.action_parser = ASTActionParser()

    def parse(self, raw_text: str) -> ParsedOutput:
        raw_text = raw_text.strip()

        # 1. 检查 final_answer (优先级最高 — 一旦 LLM 声明完成, 直接返回)
        fa_match = re.search(r"<final_answer>(.*?)</final_answer>", raw_text, re.DOTALL)
        if fa_match:
            # 提取可选的 thought (如果有的话, 仅用于日志)
            return ParsedOutput.final_answer(fa_match.group(1).strip())

        # 2. 检查 action
        action_match = re.search(r"<action>(.*?)</action>", raw_text, re.DOTALL)
        if action_match:
            action_str = action_match.group(1).strip()
            try:
                action = self.action_parser.parse(action_str)
                return ParsedOutput.action_output(action)
            except ValueError as e:
                return ParsedOutput.parse_error(
                    f"无法解析 action: {e}\n"
                    f"正确格式: tool_name(arg1=\"v1\", arg2=\"v2\")\n"
                    f"action 字符串参数中如有换行, 请用 \\n 表示。"
                )

        # 3. 检查 thought (单独出现, 没有 action 或 final_answer)
        thought_match = re.search(r"<thought>(.*?)</thought>", raw_text, re.DOTALL)
        if thought_match:
            return ParsedOutput.parse_error(
                "你只输出了 <thought>，但没有接 <action> 或 <final_answer>。"
                "请输出 <action> 来执行操作，或输出 <final_answer> 来完成任务。"
            )

        # 4. 什么都没匹配到
        return ParsedOutput.parse_error(
            "无法从你的输出中解析出有效的 <action> 或 <final_answer> 标签。"
            "请确保包含 <action>tool_name(...)</action> 或 <final_answer>...</final_answer>。"
        )
