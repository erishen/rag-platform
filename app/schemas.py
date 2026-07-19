"""请求 / 响应数据模型。"""
from pydantic import BaseModel


class IngestRequest(BaseModel):
    title: str
    content: str


class ChatRequest(BaseModel):
    question: str


class SearchResultItem(BaseModel):
    chunk_id: int
    score: float
    text: str


class ChatResponse(BaseModel):
    answer: str
    source: str  # blocked / direct_qa / llm
    context: list[SearchResultItem] = []
