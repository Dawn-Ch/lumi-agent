"""入口 — Minimal SWE Agent 的启动脚本。

Usage:
    python main.py /path/to/project          # 交互式输入任务
    python main.py /path/to/project --task "找到所有 TODO"  # 直接指定任务
    python main.py /path/to/project --no-confirm  # 跳过命令确认 (危险, 仅测试用)
"""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Minimal SWE Agent — 一个用于学习 Agent 原理的最小实现",
    )
    parser.add_argument(
        "directory",
        help="工作目录 (Agent 将在此目录中操作)",
    )
    parser.add_argument(
        "--task", "-t",
        help="直接指定任务 (不指定则交互式输入)",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="跳过终端命令确认 (仅用于自动化测试)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="最大循环轮次 (默认 50)",
    )
    parser.add_argument(
        "--parser",
        choices=["xml", "json"],
        default="xml",
        help="Output parser 类型 (默认 xml)",
    )
    args = parser.parse_args()

    # 验证工作目录
    if not os.path.isdir(args.directory):
        print(f"错误: 目录不存在 — {args.directory}")
        sys.exit(1)

    # 导入 Agent (延迟导入, 让 argparse 先跑)
    from agent.agent import SWEAgent
    from agent.core.parser.xml_parser import XMLParser
    from agent.core.parser.json_parser import JSONParser
    from agent.core.loop import LoopConfig

    # 配置
    loop_config = LoopConfig(max_turns=args.max_turns)
    parser_impl = JSONParser() if args.parser == "json" else XMLParser()

    # 创建 Agent
    agent = SWEAgent(
        working_directory=args.directory,
        parser=parser_impl,
        loop_config=loop_config,
        requires_command_confirm=not args.no_confirm,
    )

    # 获取任务
    task = args.task
    if not task:
        task = input("\n请输入任务: ").strip()
        if not task:
            print("任务不能为空。")
            sys.exit(1)

    print(f"\n工作目录: {os.path.abspath(args.directory)}")
    print(f"任务: {task}")
    print(f"Parser: {args.parser}")
    print(f"命令确认: {'开' if not args.no_confirm else '关'}")

    # 运行
    result = agent.run(task)
    print(f"\n{'='*60}")
    print(f"最终结果:\n{result}")


if __name__ == "__main__":
    main()
