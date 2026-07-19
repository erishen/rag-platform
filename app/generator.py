"""LLM 生成：OpenAI 兼容接口，强制要求真实 key（本项目不提供 mock）。

system prompt 限定「只从给定内容回答，
不知道就说不知道」，并支持流式（本学习版先用非流式，便于理解）。
"""
from openai import OpenAI

from app.config import settings

_SYSTEM = (
    "你是一个严谨的知识库问答助手。"
    "只能依据下面提供的【参考内容】回答用户问题；"
    "如果参考内容中没有相关信息，请明确说「根据现有资料无法回答」，**不要编造**。 "
    "回答要简洁、基于事实。"
)


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY 未配置：本项目要求真实 LLM（见 .env.example）。"
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def generate(question: str, chunks: list) -> str:
    client = _client()
    context = "\n\n".join(f"[片段 {i + 1}] {c}" for i, c in enumerate(chunks))
    user_prompt = f"【参考内容】\n{context}\n\n【问题】\n{question}"
    resp = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content.strip()
