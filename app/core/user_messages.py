from __future__ import annotations

from dataclasses import dataclass, field


SEVERITY_LABELS = {
    "info": "信息",
    "warning": "警告",
    "error": "错误",
}


DEFAULT_DATA_SAFETY = "不影响。该操作失败或提示只影响当前软件操作，不会修改原始实验数据。"


@dataclass(frozen=True)
class UserMessage:
    title: str
    what_happened: str
    data_safety: str = DEFAULT_DATA_SAFETY
    facts: tuple[str, ...] = field(default_factory=tuple)
    technical_detail: str | None = None
    severity: str = "info"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_LABELS:
            raise ValueError(f"Unsupported message severity: {self.severity}")


def exception_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def format_user_message(message: UserMessage) -> str:
    lines = [
        message.title,
        f"级别：{SEVERITY_LABELS[message.severity]}",
        "",
        f"发生了什么：{message.what_happened}",
        f"是否影响原始数据：{message.data_safety}",
    ]
    if message.facts:
        lines.extend(["", "相关事实："])
        lines.extend(f"- {fact}" for fact in message.facts)
    if message.technical_detail:
        lines.append(f"技术细节：{message.technical_detail}")
    return "\n".join(lines)
