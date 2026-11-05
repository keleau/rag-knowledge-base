from __future__ import annotations

import re

PHONE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ID_CARD = re.compile(r"(?<!\d)(\d{6})(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
BANK_CARD = re.compile(r"(?<!\d)(\d{4})\d{10,15}(\d{4})(?!\d)")


def mask(text: str) -> str:
    """把简历/文档里的手机号、邮箱、身份证、银行卡做遮罩，再发给模型。"""
    value = str(text or "")
    value = EMAIL.sub(lambda m: f"{m.group(0)[0]}***@{m.group(0).split('@')[-1]}", value)
    value = PHONE.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[-4:]}", value)
    value = ID_CARD.sub(lambda m: f"{m.group(1)}**********{m.group(0)[-4:]}", value)
    value = BANK_CARD.sub(lambda m: f"{m.group(1)}**********{m.group(2)}", value)
    return value


def contains_pii(text: str) -> bool:
    value = str(text or "")
    return any(p.search(value) for p in (PHONE, ID_CARD, BANK_CARD))


SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)(?:api[_-]?key|secret|access[_-]?token|password|passwd)\s*[:=]\s*['\"]?[^\s'\"]{6,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
]


def scan_secrets(text: str) -> list[str]:
    """返回命中的敏感串类别标签；空列表表示通过。"""
    value = str(text or "")
    hits: list[str] = []
    labels = ["api_key", "credential", "private_key", "bearer_token"]
    for label, pattern in zip(labels, SENSITIVE_PATTERNS):
        if pattern.search(value):
            hits.append(label)
    return hits
