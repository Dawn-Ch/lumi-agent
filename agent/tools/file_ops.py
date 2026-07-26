"""File I/O 工具 — 读取、写入、搜索文件。

设计要点:
- 所有路径操作都在工作目录内 (沙箱约束的最简实现)
- search_content 不仅搜索, 还限制返回行数 (避免 context 污染)
"""

import os
import re

from agent.tools.base import Tool, ToolResult


class ReadFile(Tool):
    name = "read_file"
    description = "读取文件的全部内容。先读文件再修改，不要自己猜测文件内容。"
    parameters = {
        "file_path": {
            "type": "string",
            "description": "文件的绝对路径",
            "required": True,
        },
    }

    def execute(self, file_path: str, **kwargs) -> ToolResult:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 如果文件太长，截断并提示
            max_lines = 500
            lines = content.split("\n")
            if len(lines) > max_lines:
                truncated = "\n".join(lines[:max_lines])
                return ToolResult(
                    success=True,
                    output=(
                        f"{truncated}\n\n"
                        f"[文件共 {len(lines)} 行，仅显示前 {max_lines} 行。"
                        f"可用 search_content 搜索特定内容。]"
                    ),
                )
            return ToolResult(success=True, output=content)
        except FileNotFoundError:
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=f"读取文件失败: {str(e)}")


class WriteFile(Tool):
    name = "write_file"
    description = "将内容写入文件（覆盖写入）。修改代码后应读取文件验证内容是否正确。"
    parameters = {
        "file_path": {
            "type": "string",
            "description": "文件的绝对路径",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "要写入的内容",
            "required": True,
        },
    }

    def execute(self, file_path: str, content: str, **kwargs) -> ToolResult:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 写入后验证
            with open(file_path, "r", encoding="utf-8") as f:
                written = f.read()

            if written == content:
                return ToolResult(
                    success=True,
                    output=f"写入成功: {file_path} ({len(content)} 字符)。验证通过。",
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"写入验证失败: 文件内容与预期不一致。",
                )
        except Exception as e:
            return ToolResult(success=False, error=f"写入文件失败: {str(e)}")


class SearchContent(Tool):
    name = "search_content"
    description = "在文件中搜索匹配的内容（支持正则表达式）。返回匹配行及行号。"
    parameters = {
        "pattern": {
            "type": "string",
            "description": "搜索的正则表达式或普通文本",
            "required": True,
        },
        "directory": {
            "type": "string",
            "description": "搜索的目录路径（绝对路径）",
            "required": True,
        },
        "file_pattern": {
            "type": "string",
            "description": "文件名过滤，如 '*.py'，默认搜索所有文件",
            "required": False,
        },
    }

    def execute(
        self, pattern: str, directory: str, file_pattern: str = "*", **kwargs
    ) -> ToolResult:
        import fnmatch

        results = []
        max_total_lines = 30  # 总共最多返回 30 行匹配

        try:
            for root, dirs, files in os.walk(directory):
                # 跳过隐藏目录和常见的非代码目录
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".git")]

                for fname in files:
                    if not fnmatch.fnmatch(fname, file_pattern):
                        continue

                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for lineno, line in enumerate(f, 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    results.append(f"{fpath}:{lineno}: {line.strip()}")
                                    if len(results) >= max_total_lines:
                                        truncated_msg = f"\n\n[达到搜索上限 {max_total_lines} 行，结果已截断]"
                                        return ToolResult(
                                            success=True,
                                            output="\n".join(results) + truncated_msg,
                                        )
                    except Exception:
                        continue

            if not results:
                return ToolResult(
                    success=True,
                    output=f"未找到匹配 '{pattern}' 的内容。",
                )
            return ToolResult(success=True, output="\n".join(results))
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {str(e)}")
