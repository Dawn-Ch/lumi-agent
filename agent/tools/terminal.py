"""Terminal 工具 — 执行 shell 命令。

设计要点:
- 返回 stdout + stderr + exit_code, 不只返回"成功"或"失败"
- 用户在 .env 中可配置命令确认策略
"""

import subprocess
import os

from agent.tools.base import Tool, ToolResult


class RunTerminal(Tool):
    name = "run_terminal"
    description = "执行 shell 命令，返回标准输出、错误输出和退出码。对于长时间运行的命令(如 npm install), 会等待完成。"
    parameters = {
        "command": {
            "type": "string",
            "description": "要执行的 shell 命令",
            "required": True,
        },
    }

    def execute(self, command: str, **kwargs) -> ToolResult:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
                cwd=os.getcwd(),
            )

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout.strip())
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr.strip()}")

            output = "\n".join(output_parts) if output_parts else "(无输出)"

            if result.returncode == 0:
                return ToolResult(success=True, output=f"命令执行成功 (exit=0)\n\n{output}")
            else:
                return ToolResult(
                    success=False,
                    output=output,
                    error=f"命令退出码: {result.returncode}",
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"命令超时 (300s): {command}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"命令执行异常: {str(e)}",
            )
