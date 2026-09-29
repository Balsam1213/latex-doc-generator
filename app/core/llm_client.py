"""OpenAI 兼容协议的 LLM 客户端（默认智谱 GLM，可在 .env 换任意兼容平台）。

- stream_chat: 文本生成，流式输出
- describe_images: 视觉模型识别图片（上传附件用）
"""
from typing import Iterator, Optional

import openai
from openai import OpenAI

from . import config, prompts


class LLMError(RuntimeError):
    """对用户可读的模型调用异常。"""


def _explain(e: Exception) -> str:
    if isinstance(e, openai.AuthenticationError):
        return "API Key 无效或未通过认证，请检查 .env 中的 LLM_API_KEY。"
    if isinstance(e, openai.RateLimitError):
        return "已触发模型服务的速率/额度限制（免费档并发有限），请稍等片刻再试。"
    if isinstance(e, openai.NotFoundError):
        return (
            "接口或模型不存在。请检查 .env 中 LLM_BASE_URL 与"
            f" LLM_MODEL（{config.LLM_MODEL}）/ LLM_VISION_MODEL（{config.LLM_VISION_MODEL}）"
            "是否为该平台支持的模型名。"
        )
    if isinstance(e, openai.APIConnectionError):
        return f"无法连接模型服务（{config.LLM_BASE_URL}），请检查网络连接。"
    return f"{e}"


def _make_client() -> OpenAI:
    if not config.llm_configured():
        raise LLMError(
            "尚未配置 API Key：请打开项目根目录的 .env 文件，"
            "把 LLM_API_KEY= 后面换成你的智谱 API Key（open.bigmodel.cn 创建），保存后重启服务。"
        )
    return OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
        timeout=300.0,
        max_retries=2,
    )


def stream_chat(
    messages: list[dict],
    cancel_event: Optional[object] = None,
    temperature: float = 0.35,
) -> Iterator[str]:
    """流式对话，逐段 yield 文本增量。失败抛 LLMError。"""
    client = _make_client()
    try:
        stream = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=config.LLM_MAX_TOKENS,
        )
        for chunk in stream:
            if cancel_event is not None and cancel_event.is_set():
                break
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        stream.close()
    except openai.OpenAIError as e:
        raise LLMError(_explain(e)) from e
    except Exception as e:
        raise LLMError(_explain(e)) from e


def chat_once(messages: list[dict], temperature: float = 0.2) -> str:
    """一次性（非流式）对话，返回完整回复文本。失败抛 LLMError。"""
    client = _make_client()
    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=config.LLM_MAX_TOKENS,
        )
        return resp.choices[0].message.content or ""
    except openai.OpenAIError as e:
        raise LLMError(_explain(e)) from e
    except Exception as e:
        raise LLMError(_explain(e)) from e


def describe_images(data_url: str) -> str:
    """调用视觉模型识别单张图片（data URL 形式），返回描述文本。失败抛 LLMError。"""
    client = _make_client()
    try:
        resp = client.chat.completions.create(
            model=config.LLM_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompts.VISION_PROMPT},
                    ],
                }
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""
    except openai.OpenAIError as e:
        raise LLMError(f"视觉模型 {config.LLM_VISION_MODEL} 调用失败：" + _explain(e)) from e
    except Exception as e:
        raise LLMError(f"视觉模型调用失败：{e}") from e
