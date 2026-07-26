"""Command Checker — 检测并拦截高危命令。

设计要点:
- 基于规则引擎 (黑名单正则), 不用 LLM (节省 token)
- 高危命令列表是可扩展的
- 只做检测, 不做决策 (是否继续由 Loop 控制器决定)
"""

import re
from dataclasses import dataclass


@dataclass
class DangerCheckResult:
    is_dangerous: bool
    reason: str = ""


class CommandChecker:
    """高危命令检测器。"""

    # 高危命令模式列表
    DANGEROUS_PATTERNS: list[tuple[str, str]] = [
        # (正则模式, 风险说明)
        (r"\brm\s+(-[rRf]+\s+)*[/~]", "删除系统文件或目录"),
        (r"\bsudo\b", "需要 root 权限"),
        (r"\bchmod\s+777", "危险的权限设置"),
        (r"\bchown\b", "更改文件所有者"),
        (r"curl.*\|\s*(ba)?sh", "管道执行远程脚本"),
        (r"wget.*\|\s*(ba)?sh", "管道执行远程脚本"),
        (r">\s*/dev/sd[a-z]", "直接写入磁盘设备"),
        (r"\bdd\s+if=", "磁盘操作"),
        (r"\bmkfs\.", "格式化文件系统"),
        (r"\bfork\s+bomb\b", "Fork 炸弹"),
        (r":\(\)\s*\{", "Fork 炸弹 (shell 语法)"),
        (r"\bgit\s+push\s+--force", "强制推送到远程仓库"),
        (r"\bdocker\s+rm\b", "删除 Docker 容器"),
        (r"\bdocker\s+rmi\b", "删除 Docker 镜像"),
        (r"\biptables\b", "修改防火墙规则"),
        (r"\bshutdown\b", "关闭/重启系统"),
        (r"\breboot\b", "重启系统"),
    ]

    def check(self, command: str) -> DangerCheckResult:
        """检查命令是否危险。返回 DangerCheckResult。"""
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return DangerCheckResult(is_dangerous=True, reason=reason)
        return DangerCheckResult(is_dangerous=False)
