"""文本分块：按句切分，累计到约 max_len 字符后成块，块间 overlap 重叠。"""
import re


def split_text(text: str, max_len: int = 300, overlap: int = 50) -> list[str]:
    sentences = re.split(r"(?<=[。！？\n])", text)
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) <= max_len:
            cur += s
        else:
            if cur:
                chunks.append(cur)
            cur = (cur[-overlap:] if overlap else "") + s
    if cur:
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]
