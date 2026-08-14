"""LLM Client — 封装 LLM API 调用。

设计要点:
- 薄封装, 只负责调用和重试
- 不负责 prompt 组装 (那是 PromptManager 的事)
- 不负责解析输出 (那是 Parser 的事)
"""

import os
import time

import httpx
from dotenv import load_dotenv
from openai import OpenAI


class LLMClient:
    """LLM API 调用的薄封装。"""

    def __init__(self):
        load_dotenv(override=True)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "未找到 OPENAI_API_KEY 环境变量。\n"
                "请在 .env 文件中设置, 或复制 .env.example 为 .env 并填入你的 API key。"
            )

        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        # 使用 trust_env=False 的 http client, 让 httpx 不读取系统代理环境变量
        # 避免 socks 代理 (如 all_proxy) 导致 httpx 初始化崩溃
        # 注意: 不修改全局 os.environ — 进程内其他代码仍可正常使用代理
        http_client = httpx.Client(trust_env=False)

        self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        self.model = os.getenv("LLM_MODEL", "gpt-4o")
        self.max_retries = 3

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        """发送消息给 LLM, 返回模型输出文本。自动重试。"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                content = response.choices[0].message.content or ""
                return content
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    print(f"  [LLM 调用失败, {wait}s 后重试... ({e})]")
                    time.sleep(wait)

        raise RuntimeError(f"LLM 调用失败 (重试 {self.max_retries} 次): {last_error}")
