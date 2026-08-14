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

        def extract_thought(text_before: str) -> str:
            """只从指定文本片段中提取 <thought>。

            锚定在 action/final_answer 标签之前, 避免把标签内部内容
            (如 final_answer 里出现的 "<thought>" 字样) 误当作思考文本。
            """
            m = re.search(r"<thought>(.*?)</thought>", text_before, re.DOTALL)
            return m.group(1).strip() if m else ""

        # 1. 检查 final_answer (优先级最高 — 一旦 LLM 声明完成, 直接返回)
        fa_match = re.search(r"<final_answer>(.*?)</final_answer>", raw_text, re.DOTALL)
        if fa_match:
            thought_text = extract_thought(raw_text[:fa_match.start()])
            return ParsedOutput.final_answer(
                fa_match.group(1).strip(), thought_text=thought_text
            )

        # 2. 检查 action
        action_match = re.search(r"<action>(.*?)</action>", raw_text, re.DOTALL)
        if action_match:
            thought_text = extract_thought(raw_text[:action_match.start()])
            action_str = action_match.group(1).strip()
            try:
                action = self.action_parser.parse(action_str)
                return ParsedOutput.action_output(action, thought_text=thought_text)
            except ValueError as e:
                return ParsedOutput.parse_error(
                    f"无法解析 action: {e}\n"
                    f"正确格式: tool_name(arg1=\"v1\", arg2=\"v2\")\n"
                    f"action 字符串参数中如有换行, 请用 \\n 表示。"
                )

        # 3. 检查 thought (单独出现, 没有 action 或 final_answer)
        # 常见于 LLM 输出被截断 (达到 max_tokens) — 返回 thought 类型,
        # 由 Loop 控制器提示 LLM 继续输出, 不当作格式错误
        thought_match = re.search(r"<thought>(.*?)</thought>", raw_text, re.DOTALL)
        if thought_match:
            return ParsedOutput.thought_output(thought_match.group(1).strip())

        # 4. 什么都没匹配到
        return ParsedOutput.parse_error(
            "无法从你的输出中解析出有效的 <action> 或 <final_answer> 标签。"
            "请确保包含 <action>tool_name(...)</action> 或 <final_answer>...</final_answer>。"
        )
