"""ASTActionParser — 使用 Python AST 解析 action 字符串。

设计要点:
- 利用 Python 自己的解析器处理函数调用语法, 不再手写状态机
- ast.parse(mode="eval") 安全地解析表达式, 不执行代码
- ast.literal_eval 安全地提取字面量值
"""

import ast
from typing import Any

from agent.core.schemas.action import Action


class ASTActionParser:
    """使用 Python AST 解析 action 字符串。

    LLM 输出的 action 字符串 (如 write_file(file_path="/x", content="hello"))
    是合法的 Python 函数调用语法。直接用 ast.parse 解析, 不需要手写状态机。
    """

    def parse(self, action_str: str) -> Action:
        """解析 action 字符串, 返回 Action。解析失败抛 ValueError。"""
        # 1. 用 Python AST 解析 (mode="eval" 只解析表达式, 不执行)
        try:
            tree = ast.parse(action_str.strip(), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Action 字符串语法错误: {e}") from e

        # 2. 安全检查: 只允许 ast.Call (函数调用)
        if not isinstance(tree.body, ast.Call):
            raise ValueError(
                f"只能包含函数调用, 不能是 {type(tree.body).__name__}。"
                f"正确格式: tool_name(arg1=\"v1\", arg2=\"v2\")"
            )

        call = tree.body

        # 3. 提取函数名
        if not isinstance(call.func, ast.Name):
            raise ValueError(
                f"不支持的调用形式: {ast.dump(call.func)}。"
                f"只支持简单的 tool_name(...) 格式。"
            )
        tool_name = call.func.id

        # 4. 拒绝位置参数 (只允许关键字参数)
        if call.args:
            raise ValueError(
                "不支持位置参数, 请使用关键字参数。"
                f"正确格式: {tool_name}(arg_name=\"value\")"
            )

        # 5. 提取关键字参数 (使用 ast.literal_eval 安全求值)
        arguments: dict[str, Any] = {}
        for kw in call.keywords:
            if kw.arg is None:
                raise ValueError("不支持 **kwargs 展开语法")
            try:
                value = ast.literal_eval(kw.value)
            except ValueError as e:
                raise ValueError(
                    f"参数 '{kw.arg}' 的值无法解析: {e}。"
                    f"只支持字面量 (字符串、数字、布尔值、None、列表、字典)。"
                ) from e
            arguments[kw.arg] = value

        return Action(tool_name=tool_name, arguments=arguments)
