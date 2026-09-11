"""Build the relationship guide settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from ._shared import _card, _heading


def _install_relationship_guide(panel: Any) -> None:
    page = panel.add_navigation_page(
        "relationship_guide",
        "relationship",
        "關係教學",
        "關係教學",
        "了解好感度、心情與記憶如何影響對話",
    )
    for title, body in (
        (
            "好感度",
            "0–24 偏緊張、25–39 偏疏離、40–54 自然相處、55–69 漸漸熟悉、70–84 親近、85–100 非常親近。",
        ),
        (
            "長期記憶",
            "LLM 會從聊天中挑選與製作人相關、長期有用的明確資訊，也可手動新增；記憶按偶像分開保存。",
        ),
        (
            "角色人格",
            "角色扮演 Markdown 是基本人格；介面中的人格預設可作為本機覆寫，且不會混用其他偶像設定。",
        ),
        ("製作人", "每位偶像都擁有對製作人獨立的好感度、心情和記憶。"),
    ):
        _, layout = _card(page)
        _heading(layout, title, body)
    page.layout().addStretch()
