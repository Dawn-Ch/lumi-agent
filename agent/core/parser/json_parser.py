"""JSONParser — 基于 JSON 的 LLM 输出解析器 (备选 protocol)。

与 XMLParser 的区别:
- 使用 JSON 作为 LLM 输出格式
- 支持 markdown code block 包裹的 JSON
"""

import json
import re

from agent.core.parser.base import Parser, ParsedOutput
from agent.core.schemas.action import Action


class JSONParser(Parser):
    """基于 JSON 的 Parser。

    LLM 输出格式:
    {"thought": "...", "action": "read_file", "args": {"file_path": "/tmp/x"}}
    或
    {"thought": "...", "final_answer": "任务完成"}
    """

    def parse(self, raw_text: str) -> ParsedOutput:
        raw_text = raw_text.strip()

        # 尝试从 markdown code block 中提取 JSON
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = raw_text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return ParsedOutput.parse_error(
                f"JSON 解析失败: {e}。请输出合法的 JSON。"
            )

        if not isinstance(data, dict):
            return ParsedOutput.parse_error("JSON 必须是对象 (dict)。")

        if "final_answer" in data:
            return ParsedOutput.final_answer(str(data["final_answer"]))

        if "action" in data:
            tool_name = str(data["action"])
            args = data.get("args", {})
            if not isinstance(args, dict):
                return ParsedOutput.parse_error("'args' 字段必须是对象 (dict)。")
            return ParsedOutput.action_output(
                Action(tool_name=tool_name, arguments=args)
            )

        return ParsedOutput.parse_error(
            "JSON 中缺少 'action' 或 'final_answer' 字段。"
        )
