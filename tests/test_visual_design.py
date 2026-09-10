from copy import deepcopy

import pytest

from smart_laundry.visual_design import (
    DEFAULT_VISUAL_DESIGN,
    validate_visual_design,
    visual_design_css,
)


def test_default_visual_design_is_valid_and_generates_css() -> None:
    validated = validate_visual_design(DEFAULT_VISUAL_DESIGN)
    css = visual_design_css(validated)

    assert len(validated["elements"]) == 24
    assert "backdrop-filter:blur(12px)" in css
    assert ".stApp" in css
    assert ".st-key-top_info_bar" in css
    assert "衣物卡片" in {item["label"] for item in validated["elements"]}
    assert "宠物用品卡片" in {item["label"] for item in validated["elements"]}
    assert "@media (min-width:901px)" not in css
    assert "transform:translate" not in css
    assert "font-size:" not in css
    assert "width:min(" not in css


def test_visual_design_ignores_saved_layout_and_typography_fields() -> None:
    custom = deepcopy(DEFAULT_VISUAL_DESIGN)
    custom["elements"][0].update(
        {"x": 999, "width": 100, "font_size": 48, "text_x": 240}
    )

    validated = validate_visual_design(custom)
    css = visual_design_css(validated)

    assert validated["elements"][0]["x"] == 0
    assert validated["elements"][0]["width"] == 220
    assert "font_size" not in validated["elements"][0]
    assert "text_x" not in validated["elements"][0]
    assert "translate" not in css


def test_visual_design_rejects_unknown_colors_and_missing_elements() -> None:
    invalid_color = deepcopy(DEFAULT_VISUAL_DESIGN)
    invalid_color["elements"][0]["color1"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="颜色格式"):
        validate_visual_design(invalid_color)

    missing_element = deepcopy(DEFAULT_VISUAL_DESIGN)
    missing_element["elements"].pop()
    with pytest.raises(ValueError, match="不完整"):
        validate_visual_design(missing_element)
