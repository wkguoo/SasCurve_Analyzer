from __future__ import annotations

import pytest

from app.core.user_messages import format_user_message, UserMessage


def test_user_message_formats_fact_only_layers() -> None:
    text = format_user_message(
        UserMessage(
            title="导入失败",
            what_happened="当前文件没有成功转换为一条可用曲线。",
            facts=("row_count=0。", "current_curve is None: True。"),
            technical_detail="ValueError: empty file",
            severity="error",
        )
    )

    assert "导入失败" in text
    assert "级别：错误" in text
    assert "发生了什么：" in text
    assert "相关事实：" in text
    assert "是否影响原始数据：" in text
    assert "技术细节：" in text
    assert "建议操作" not in text
    assert "可能原因" not in text


def test_user_message_rejects_unknown_severity() -> None:
    with pytest.raises(ValueError, match="Unsupported message severity"):
        UserMessage(title="x", what_happened="y", severity="fatal")
