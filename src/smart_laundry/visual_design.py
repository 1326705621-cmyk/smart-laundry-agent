"""颜色与效果设计器的数据校验，以及将设置转换为安全 CSS。"""

from __future__ import annotations

from copy import deepcopy
import re


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
ELEMENT_DEFINITIONS = {
    "page": ("页面大背景", 0, 0, 220, 90, ".stApp"),
    "title": ("标题区域", 0, 0, 220, 90, ".app-title"),
    "account": ("账户与家庭栏", 0, 0, 220, 90, ".st-key-account_bar"),
    "info": ("城市日期天气栏", 0, 0, 220, 90, ".st-key-top_info_bar"),
    "city_select": ("城市选择框", 0, 0, 220, 90, '.st-key-top_info_bar [data-baseweb="select"] > div'),
    "attention": ("提醒小框", 0, 0, 220, 90, ".attention-pill"),
    "tab_status": ("物品状态标签", 0, 0, 220, 90, 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(1)[aria-selected="true"]'),
    "tab_agent": ("智能助手标签", 0, 0, 220, 90, 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(2)[aria-selected="true"]'),
    "tab_add": ("添加物品标签", 0, 0, 220, 90, 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(3)[aria-selected="true"]'),
    "status": ("物品状态大方框", 0, 0, 220, 90, ".st-key-status_shell"),
    "filters": ("筛选与搜索框", 0, 0, 220, 90, '.st-key-status_shell [data-baseweb="select"] > div, .st-key-status_shell [data-testid="stTextInput"] input'),
    "pager": ("翻页按钮与页码", 0, 0, 220, 90, ".st-key-status_shell .stButton > button, .pager-text"),
    "card_clothing": ("衣物卡片", 0, 0, 220, 90, '[class*="st-key-item_card_clothing_"]'),
    "card_bedding": ("床上用品卡片", 0, 0, 220, 90, '[class*="st-key-item_card_bedding_"]'),
    "card_toy": ("玩偶卡片", 0, 0, 220, 90, '[class*="st-key-item_card_toy_"]'),
    "card_pet": ("宠物用品卡片", 0, 0, 220, 90, '[class*="st-key-item_card_pet_"]'),
    "status_box": ("清洗晾晒状态框", 0, 0, 220, 90, '[class*="st-key-item_status_"]'),
    "image": ("物品图片框", 0, 0, 220, 90, '[class*="st-key-item_card_"] [data-testid="stImage"] img, .placeholder-art'),
    "category_pill": ("物品分类标签", 0, 0, 220, 90, ".category-pill"),
    "edit_button": ("编辑按钮", 0, 0, 220, 90, '[class*="st-key-item_card_"] .stButton > button'),
    "history": ("最近记录框", 0, 0, 220, 90, '[class*="st-key-item_card_"] [data-testid="stExpander"]'),
    "action_button": ("功能区操作按钮", 0, 0, 220, 90, '.st-key-agent_shell .stButton > button, .st-key-add_shell .stButton > button, .stFormSubmitButton > button'),
    "agent": ("智能助手内容区", 0, 0, 220, 90, ".st-key-agent_shell"),
    "add": ("添加物品内容区", 0, 0, 220, 90, ".st-key-add_shell"),
}

TEXT_TARGETS = {
    "page": ".stApp",
    "title": ".app-title strong",
    "account": ".st-key-account_bar p, .st-key-account_bar button, .st-key-account_bar span",
    "info": ".st-key-top_info_bar p, .st-key-top_info_bar div, .st-key-top_info_bar span",
    "city_select": '.st-key-top_info_bar [data-baseweb="select"]',
    "attention": ".attention-pill",
    "tab_status": 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(1) p',
    "tab_agent": 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(2) p',
    "tab_add": 'div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(3) p',
    "filters": '.st-key-status_shell [data-testid="stHorizontalBlock"]:first-of-type label, .st-key-status_shell [data-testid="stHorizontalBlock"]:first-of-type input',
    "status": ".st-key-status_shell p, .st-key-status_shell label",
    "pager": ".st-key-status_shell .stButton > button, .pager-text",
    "card_clothing": '[class*="st-key-item_card_clothing_"] p, [class*="st-key-item_card_clothing_"] label',
    "card_bedding": '[class*="st-key-item_card_bedding_"] p, [class*="st-key-item_card_bedding_"] label',
    "card_toy": '[class*="st-key-item_card_toy_"] p, [class*="st-key-item_card_toy_"] label',
    "card_pet": '[class*="st-key-item_card_pet_"] p, [class*="st-key-item_card_pet_"] label',
    "status_box": '[class*="st-key-item_status_"] p, [class*="st-key-item_status_"] label',
    "image": ".placeholder-art",
    "category_pill": ".category-pill",
    "edit_button": '[class*="st-key-item_card_"] .stButton > button',
    "history": '[class*="st-key-item_card_"] [data-testid="stExpander"] p',
    "action_button": '.st-key-agent_shell .stButton > button, .st-key-add_shell .stButton > button, .stFormSubmitButton > button',
    "agent": ".st-key-agent_shell p, .st-key-agent_shell label, .st-key-agent_shell button",
    "add": ".st-key-add_shell p, .st-key-add_shell label, .st-key-add_shell button",
}


def _element(
    element_id: str,
    *,
    fill_type: str,
    color1: str,
    color2: str,
    text_color: str = "#17263F",
    blur: int = 0,
    opacity: int = 96,
    border_width: int = 1,
    radius: int = 20,
    shadow: int = 10,
) -> dict:
    label, x, y, width, height, _ = ELEMENT_DEFINITIONS[element_id]
    return {
        "id": element_id,
        "label": label,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "fill_type": fill_type,
        "color1": color1,
        "color2": color2,
        "gradient_angle": 125,
        "opacity": opacity,
        "blur": blur,
        "border_color": "#DDE3EC",
        "border_width": border_width,
        "radius": radius,
        "shadow": shadow,
        "text_color": text_color,
    }


DEFAULT_VISUAL_DESIGN = {
    "version": 2,
    "canvas": {"width": 900, "height": 680},
    "elements": [
        _element("page", fill_type="solid", color1="#FFFFFF", color2="#FFFFFF", border_width=0, radius=0, shadow=0),
        _element(
            "title", fill_type="solid", color1="#FFFFFF", color2="#FFFFFF",
            opacity=0, border_width=0, radius=0, shadow=0,
        ),
        _element("account", fill_type="glass", color1="#FFFFFF", color2="#F4F6FA", blur=12, opacity=78),
        _element("info", fill_type="glass", color1="#FFFFFF", color2="#EEF2FF", blur=14, opacity=76),
        _element("city_select", fill_type="solid", color1="#F4F6FA", color2="#F4F6FA", opacity=100, radius=12, shadow=0),
        _element("attention", fill_type="solid", color1="#FFF5F7", color2="#FFF5F7", text_color="#BD405D", opacity=100),
        _element("tab_status", fill_type="gradient", color1="#AAA8FF", color2="#EEF1FF", opacity=88),
        _element("tab_agent", fill_type="gradient", color1="#FFDCE5", color2="#FFF8FA", text_color="#C95370", opacity=88),
        _element("tab_add", fill_type="gradient", color1="#D9F3EC", color2="#F7FCFA", text_color="#278D7D", opacity=88),
        _element("filters", fill_type="glass", color1="#FFFFFF", color2="#F3F4FF", blur=10, opacity=82),
        _element("status", fill_type="gradient", color1="#EEF0FF", color2="#FFF1F5", opacity=82),
        _element("pager", fill_type="solid", color1="#FFFFFF", color2="#FFFFFF", opacity=72),
        _element("card_clothing", fill_type="gradient", color1="#EDF8F5", color2="#DCEFEA", text_color="#399D8C", opacity=100),
        _element("card_bedding", fill_type="gradient", color1="#F0F1FF", color2="#E2E4FF", text_color="#6669D8", opacity=100),
        _element("card_toy", fill_type="gradient", color1="#FFF0F4", color2="#FFE2EA", text_color="#D85777", opacity=100),
        _element("card_pet", fill_type="gradient", color1="#EAF6FF", color2="#DCEEFF", text_color="#438BD5", opacity=100),
        _element("status_box", fill_type="glass", color1="#FFFFFF", color2="#FFFFFF", opacity=82, blur=8, radius=15, shadow=0),
        _element("image", fill_type="solid", color1="#FFFFFF", color2="#FFFFFF", opacity=0, radius=15, shadow=0),
        _element("category_pill", fill_type="glass", color1="#FFFFFF", color2="#FFFFFF", opacity=72, blur=6, radius=20, shadow=0),
        _element("edit_button", fill_type="glass", color1="#FFFFFF", color2="#FFFFFF", opacity=76, blur=8, radius=12, shadow=0),
        _element("history", fill_type="glass", color1="#FFFFFF", color2="#FFFFFF", opacity=58, blur=6, radius=12, shadow=0),
        _element("action_button", fill_type="gradient", color1="#7777DA", color2="#9C9DEB", text_color="#FFFFFF", opacity=100, radius=12, shadow=8),
        _element("agent", fill_type="gradient", color1="#FFF4F7", color2="#F9F4FF", text_color="#17263F", opacity=100),
        _element("add", fill_type="gradient", color1="#EDF9F5", color2="#F5FBF9", text_color="#17263F", opacity=100),
    ],
}


def _number(value: object, minimum: float, maximum: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须是数字。")
    if not minimum <= float(value) <= maximum:
        raise ValueError(f"{field} 超出允许范围。")
    return float(value)


def validate_visual_design(raw: object) -> dict:
    """只保留颜色与效果；布局和字体相关字段一律恢复固定默认值。"""

    if not isinstance(raw, dict) or not isinstance(raw.get("elements"), list):
        raise ValueError("设计数据格式不正确。")
    supplied = {item.get("id"): item for item in raw["elements"] if isinstance(item, dict)}
    if set(supplied) != set(ELEMENT_DEFINITIONS):
        raise ValueError("设计元素不完整，请恢复默认后重试。")

    safe_elements = []
    defaults = {item["id"]: item for item in DEFAULT_VISUAL_DESIGN["elements"]}
    for element_id in ELEMENT_DEFINITIONS:
        item = supplied[element_id]
        default = defaults[element_id]
        safe = {"id": element_id, "label": ELEMENT_DEFINITIONS[element_id][0]}
        # 几何参数仅供只读预览使用，用户保存的数据不能改变它们。
        for field in ("x", "y", "width", "height"):
            safe[field] = default[field]
        for field, minimum, maximum in (
            ("gradient_angle", 0, 360), ("opacity", 0, 100),
            ("blur", 0, 40), ("border_width", 0, 8),
            ("radius", 0, 48), ("shadow", 0, 40),
        ):
            value = _number(item.get(field, default[field]), minimum, maximum, field)
            safe[field] = int(value)
        for field in ("color1", "color2", "border_color", "text_color"):
            value = item.get(field, default[field])
            if not isinstance(value, str) or not HEX_COLOR_PATTERN.fullmatch(value):
                raise ValueError(f"{field} 颜色格式不正确。")
            safe[field] = value.upper()
        safe["fill_type"] = item.get("fill_type", default["fill_type"])
        if safe["fill_type"] not in {"solid", "gradient", "glass"}:
            raise ValueError("背景类型不正确。")
        safe_elements.append(safe)
    return {"version": 2, "canvas": deepcopy(DEFAULT_VISUAL_DESIGN["canvas"]), "elements": safe_elements}


def _rgba(hex_color: str, opacity: int) -> str:
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red},{green},{blue},{opacity / 100:.2f})"


def visual_design_css(design: object) -> str:
    """只映射颜色、透明度和装饰效果，绝不改变页面位置与尺寸。"""

    safe = validate_visual_design(design)
    rules = []
    for item in safe["elements"]:
        _, _, _, _, _, selector = ELEMENT_DEFINITIONS[item["id"]]
        if item["fill_type"] == "gradient":
            background = (
                f"linear-gradient({item['gradient_angle']}deg,"
                f"{_rgba(item['color1'], item['opacity'])},"
                f"{_rgba(item['color2'], item['opacity'])})"
            )
            backdrop = "none"
        else:
            background = _rgba(item["color1"], item["opacity"])
            backdrop = f"blur({item['blur']}px)" if item["fill_type"] == "glass" else "none"
        rules.append(
            f"""{selector} {{
              background:{background} !important;
              backdrop-filter:{backdrop}; -webkit-backdrop-filter:{backdrop};
              border:{item['border_width']}px solid {item['border_color']} !important;
              border-radius:{item['radius']}px !important;
              box-shadow:0 {max(2, item['shadow'] // 2)}px {item['shadow'] * 2}px rgba(39,48,78,{item['shadow'] / 160:.3f}) !important;
              color:{item['text_color']} !important;
            }}"""
        )
        text_selector = TEXT_TARGETS[item["id"]]
        rules.append(
            f"""{text_selector} {{
              color:{item['text_color']} !important;
            }}"""
        )
    return "<style>\n" + "\n".join(rules) + "\n</style>"
