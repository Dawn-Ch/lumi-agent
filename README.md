# Minimal SWE Agent

从零手写一个最小化软件工程 Agent，学习 Agent 的底层原理。

## 我为什么做这个

一直觉得，当代做 AI/CS 的学生应该自己手写一个 minimal SWE Agent —— 就像老一辈程序员手写编译器、操作系统、数据库一样。这是理解"Agent 到底是什么"最直接的方式。看论文、读博客都能懂个大概，但只有亲手把 Thought → Action → Observation 的循环写成代码，才知道每一环节到底在干什么、哪里会出问题、出了问题怎么修。

## 阶段 1：搞懂基本概念

先读了两篇核心论文：

- **ReAct**（Yao et al., 2022）：提出 Reasoning + Acting 交错模式。和 Chain-of-Thought 最大的区别是，CoT 想错了就一条路走到黑，ReAct 每想一步就拿真实环境反馈纠正自己。
- **SWE-Agent**（Yang et al., 2024）：把 ReAct 专门用在软件工程任务上，提出了 ACI（Agent-Computer Interface）概念 —— 给 Agent 设计工具，就像给人类设计 UI 一样重要。

同时看了一个 GitHub 上的参考实现，发现它的设计有几个坑：

1. `while True` 死循环，没有任何停止条件
2. Output parser 用正则硬匹配，嵌套引号、多行字符串全都会炸
3. Tool 注册是往 list 里 append 裸函数，靠 `func.__name__` 当 tool name，这导致工具行为不可控
4. `write_file` 返回固定的 `"写入成功"`，写错了也告诉你成功

这几个问题我在自己实现时全部绕开了。

## 阶段 2：从设计到实现，再到重构

### 先画架构

不写代码，先在纸上把模块划清楚：

| 模块 | 职责 |
|---|---|
| Prompt 管理器 | 组装 system prompt + 工具列表 + 环境信息，和 Agent 核心逻辑解耦 |
| LLM Client | 薄封装，只管调 API 和重试 |
| Parser | 从 LLM 的非结构化文本中提取结构化指令，可插拔（XML / JSON） |
| Tools | 统一接口，新增工具不改 Agent 代码 |
| Loop 控制器 | 状态机 (THINKING → ACTING → DONE) + 轮次限制 + 兜圈子检测 |
| Checker | 高危命令黑名单 + 运行日志 |

### 实现 —— 第一版遇到的坑

第一版跑集成测试时，给 Agent 一个真实任务：找到代码里的 TODO 并修复一个 bug。本以为没什么问题，结果 15 轮跑完，文件被写坏了。

根因定位：LLM 在 `write_file` 时，content 参数里用了 Python docstring（`"""..."""`）。我手写的字符串状态机在解析 `content="""hello"""` 时，看到第二个 `"` 就以为引号闭合了，把 content 解析成了空字符串。于是 Agent 写了一个空文件（然后自己验证"空 == 空"，告诉我写入成功），后面 10+ 轮全在兜圈子试图 workaround。

### 重构：从手写状态机到 AST Parser

一开始想继续给状态机打补丁（处理三引号、转义引号……），但每遇到一种就加一种，代码会变成穷举边界 case 的屎山。

后来想通了一个关键点：**LLM 输出的 action 字符串 `write_file(file_path="/x", content="""hello""")` 就是合法的 Python 函数调用语法**。那为什么不用 Python 自己的解析器来解析？

```
ast.parse(mode="eval")  → 只解析表达式，不执行代码
ast.literal_eval()      → 安全提取字面量，不允许 eval
```

55 行代码替代了原来 110 行的手写状态机，而且：
- 三引号、转义引号、括号嵌套、逗号 —— 全部交给 Python 语法引擎处理
- 位置参数被显式拒绝（要求 LLM 用关键字参数，输出更可读）
- 非函数调用的输入被 `ast.Call` 检查拦截

重构后同样的任务 2 轮就跑通了。

### 另一个意想不到的 bug：classmethod 命名冲突

`ParsedOutput` 里有一个 `thought()` classmethod，用来创建 thought 类型的输出。在日志记录时用了 `getattr(parsed, 'thought', '')` 想获取 thought 文本。但 `getattr` 在实例上找不到字段时会往类上找 —— 找到了 classmethod，返回了一个 bound method 对象而不是默认值 `''`。于是 logger 尝试对 method 对象做切片操作，直接 crash。

教训：dataclass 的工厂方法不要和字段同名。这类问题写单元测测不出来（单独测 logger 时 TurnLog.thought 是正常的字符串），只在集成时暴露。

## 最终成果

```
19 个源文件，~1300 行代码，零重型框架依赖
```

核心功能：
- ReAct Loop（Thought → Action → Observation）
- 状态机驱动的流程控制，轮次限制 + 兜圈子检测
- 解析失败自动重试（ParseError 直接喂回 LLM）
- AST-based action parser（可插拔，支持 XML / JSON 两种 protocol）
- 4 个基础工具：Shell 执行、文件读写、内容搜索
- 高危命令拦截（17 条黑名单正则）+ 人在回路确认
- 写入后自动验证 + 搜索结果截断防 context 污染
- 完整运行日志

## 快速开始

```bash
git clone https://github.com/Dawn-Ch/minimal-swe-agent.git
cd minimal-swe-agent
cp .env.example .env
# 编辑 .env 填入 API Key

python main.py /path/to/your/project --task "你的任务"
```

## 下一步

分析 Claude Code、Codex CLI 等现代 Coding Agent 的源码，把 memory、multi-agent、background tasks、skills、context compression、sandbox 等机制逐步加进来。从"马车"到"高铁"。
