"""Smart Laundry Agent 的 Streamlit 页面入口。"""

from __future__ import annotations

from html import escape
import json
import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st

from smart_laundry.accounts import (
    AccountError,
    AccountRepository,
    AppearancePreferences,
)
from smart_laundry.config import get_settings
from smart_laundry.agent import run_laundry_agent
from smart_laundry.database import initialize_database
from smart_laundry.demo_data import seed_demo_data
from smart_laundry.device_location import get_device_location
from smart_laundry.image_storage import ImageStorageError, save_item_image
from smart_laundry.item_views import filter_and_sort_items, search_items
from smart_laundry.models import (
    ITEM_CATEGORIES,
    ItemValidationError,
    parse_optional_interval,
)
from smart_laundry.recommendations import due_wash_item_names
from smart_laundry.repositories import ItemRepository
from smart_laundry.status_rules import (
    calculate_action_status,
    choose_item_emoji,
    elapsed_text,
    recorded_today,
)
from smart_laundry.tools import LaundryToolRegistry
from smart_laundry.weather import (
    WeatherError,
    WeatherService,
    WeatherSummary,
    compact_weather_label,
)
from smart_laundry.visual_design import DEFAULT_VISUAL_DESIGN, visual_design_css
from smart_laundry.visual_designer_component import render_visual_designer


st.set_page_config(page_title="AI 家庭洗晒助手", page_icon="🧺", layout="wide")

st.markdown(
    """
    <style>
    :root {
      --ink:#17263f; --muted:#718096; --line:#e3e7ef; --white:#ffffff;
      --lavender:#9f9df3; --lavender-pale:#d5d6f2;
      --rose:#e96a87; --rose-pale:#ffe7ed;
      --mint:#399d8c; --mint-pale:#e1f4ee;
      --sky:#4f91dd; --sky-pale:#e7f2ff;
    }
    html, body, .stApp, input, textarea, button {
      font-family: Arial, "Microsoft YaHei", "SimHei", sans-serif;
    }
    .material-symbols-rounded, .material-icons, [class*="material-symbols"] {
      font-family:"Material Symbols Rounded" !important;
    }
    .stApp { background:#fff; color:var(--ink); }
    [data-testid="stHeader"] { background:transparent; }
    [data-testid="stToolbar"] { visibility:hidden; }
    .block-container { max-width:1500px; padding-top:1.55rem; padding-bottom:4rem; }
    .app-title { margin:.1rem 0 .1rem; color:var(--ink); line-height:1.1; }
    .app-title strong { font-size:2rem; letter-spacing:.02em; }
    .app-title span { display:block; color:#8190a3; margin-top:.5rem; font-size:.88rem; }
    .compact-block { height:2.7rem; display:flex; flex-direction:row;
      align-items:center; justify-content:center; gap:.55rem; }
    .compact-label { color:#8b98a8; font-size:.78rem; line-height:1; margin:0; white-space:nowrap; }
    .compact-value { color:var(--ink); font-size:.95rem; line-height:1;
      font-weight:700; white-space:nowrap; margin:0; }
    .attention-pill { display:inline-flex; align-items:center; justify-content:center; gap:.3rem;
      min-height:2.45rem; padding:.45rem .75rem; border:1px solid #f4cad4; border-radius:13px;
      background:#fff5f7; color:#bd405d; font-size:.82rem; font-weight:700; white-space:nowrap; }
    .attention-pill.is-clear { background:#f7faf9; border-color:#dcebe6; color:#568276; }
    .weather-note { color:#8794a5; font-size:.78rem; text-align:right; margin:.15rem 0 .5rem; }
    .st-key-top_info_bar { background:#fff; border:1px solid var(--line); border-radius:18px;
      padding:.65rem 1.15rem; margin:.15rem 0;
      box-shadow:0 8px 24px rgba(35,55,85,.05); }
    .st-key-top_info_bar [data-testid="stHorizontalBlock"] { gap:1.25rem; }
    .st-key-top_info_bar [data-testid="stColumn"] { min-height:2.8rem; display:flex;
      align-items:center; justify-content:center; }
    .st-key-top_info_bar [data-testid="stColumn"] > div { width:100%; }
    .st-key-top_info_bar [data-testid="stMarkdown"] { width:100%; height:2.7rem;
      display:flex; align-items:center; justify-content:center; }
    .st-key-top_info_bar [data-testid="stMarkdownContainer"] { width:100%; }
    .st-key-top_info_bar [data-testid="stSelectbox"] label { display:none; }
    .st-key-top_info_bar [data-baseweb="select"] > div { border:0; background:#f4f6fa;
      min-height:2.7rem; border-radius:12px; }
    .st-key-top_info_bar [data-testid="stColumn"]:not(:last-child) {
      border-right:1px solid #edf0f4; padding-right:1.15rem; }
    .st-key-top_info_bar [data-testid="stMarkdownContainer"] p { margin:0; }
    .st-key-top_info_bar .attention-pill { width:100%; height:2.7rem; min-height:2.7rem;
      box-sizing:border-box; }
    .st-key-account_bar { max-width:52rem; margin:0 0 .8rem auto; padding:.42rem .6rem;
      border:1px solid #e5e8ef; border-radius:16px; background:#fbfcfe; }
    .st-key-account_bar [data-testid="stSelectbox"] label { display:none; }
    .st-key-account_bar [data-baseweb="select"] > div { min-height:2.35rem; background:#fff; }
    .account-name { min-height:2.35rem; display:flex; align-items:center; color:#536177; font-size:.83rem; }
    .st-key-auth_shell { padding:1.4rem 1.5rem; border:1px solid #dedff4; border-radius:26px;
      background:linear-gradient(140deg,#f0f1ff 0%,#fff 52%,#fff0f4 100%);
      box-shadow:0 18px 45px rgba(76,80,135,.12); }
    .auth-title { text-align:center; color:var(--ink); margin:.2rem 0 .35rem; font-size:1.85rem; font-weight:800; }
    .auth-subtitle { text-align:center; color:#7a8798; font-size:.86rem; margin-bottom:1rem; }

    div[data-testid="stTabs"] [role="tablist"] { display:grid; grid-template-columns:repeat(3,1fr);
      gap:.55rem; align-items:stretch; width:100%; }
    div[data-testid="stTabs"] [data-testid="stTab"] { justify-content:center; height:5rem;
      border:1px solid #dfe4ec; border-radius:17px 17px 4px 4px; background:#fff;
      color:var(--ink); font-size:1.08rem; transition:all .18s ease; }
    div[data-testid="stTabs"] [data-testid="stTab"] p { font-size:1.08rem; }
    div[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
      font-weight:700; box-shadow:0 9px 22px rgba(101,102,184,.13); }
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(1)[aria-selected="true"] {
      background:linear-gradient(110deg,#aaa8ff 0%,#d8daf9 58%,#eef1ff 100%); border-color:#a5a3f5; }
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(2)[aria-selected="true"] {
      background:linear-gradient(110deg,#ffdce5 0%,#fff0f4 62%,#fff 100%); border-color:#f1afbf; }
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(3)[aria-selected="true"] {
      background:linear-gradient(110deg,#d9f3ec 0%,#ecf9f5 62%,#fff 100%); border-color:#9ed9ca; }
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(2) { color:#c95370; }
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(3) { color:#278d7d; }
    div[data-testid="stTabs"] .react-aria-SelectionIndicator { display:none; }

    .st-key-status_shell { margin-top:.7rem; padding:1.25rem 1.35rem 1.45rem;
      border:1px solid #d9dcfa; border-radius:26px;
      background:linear-gradient(128deg,rgba(235,237,255,.92) 0%,rgba(255,255,255,.98) 42%,rgba(255,240,245,.78) 100%);
      box-shadow:0 15px 38px rgba(105,105,172,.10); }
    .st-key-status_shell [data-testid="stSelectbox"] label,
    .st-key-status_shell [data-testid="stTextInput"] label { color:#7b8798; font-size:.78rem; }
    .st-key-status_shell [data-baseweb="select"] > div,
    .st-key-status_shell [data-testid="stTextInput"] input { background:rgba(255,255,255,.95); border-color:#dde2ec; }
    .st-key-agent_shell { margin-top:.7rem; padding:1.2rem 1.3rem; border-radius:24px;
      border:1px solid #f2cbd5; background:linear-gradient(135deg,#fff4f7 0%,#fff 54%,#f9f4ff 100%);
      box-shadow:0 14px 34px rgba(183,89,115,.08); }
    .st-key-add_shell { margin-top:.7rem; padding:1.2rem 1.3rem; border-radius:24px;
      border:1px solid #cce8df; background:linear-gradient(135deg,#edf9f5 0%,#fff 58%,#f5fbf9 100%);
      box-shadow:0 14px 34px rgba(55,139,118,.08); }
    .item-card-title { font-size:1.02rem; line-height:1.25; font-weight:700; color:var(--ink);
      text-align:center; margin:.1rem 0 .55rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .category-pill { display:inline-block; padding:.2rem .52rem; border-radius:999px;
      background:rgba(255,255,255,.72); color:#68768a; font-size:.68rem; border:1px solid rgba(255,255,255,.9); }
    .status-label { font-size:.76rem; font-weight:700; color:var(--ink); margin-top:.1rem; }
    .status-main { font-size:.65rem; margin-top:.22rem; font-weight:700; color:#66758a;
      min-height:1.15rem; white-space:nowrap !important; }
    .status-main.is-due { color:#cf3f60; }
    .status-days { font-size:.69rem; color:#7c899a; margin-top:.2rem; white-space:nowrap; }
    .placeholder-art { display:flex; width:100%; aspect-ratio:1.16/1; min-height:0;
        align-items:center; justify-content:center; overflow:hidden;
        border-radius:15px; background:rgba(255,255,255,.58); font-size:3.2rem; }
    [class*="st-key-item_card_"] { border-radius:22px; padding:.72rem;
      box-shadow:0 10px 25px rgba(50,61,100,.08); min-height:36.25rem; }
    .st-key-status_shell [data-testid="stHorizontalBlock"]:has([class*="st-key-item_card_"]) {
      align-items:stretch; }
    .st-key-status_shell [data-testid="stHorizontalBlock"]:has([class*="st-key-item_card_"])
      > [data-testid="stColumn"] { display:flex; }
    .st-key-status_shell [data-testid="stHorizontalBlock"]:has([class*="st-key-item_card_"])
      > [data-testid="stColumn"] > div { width:100%; height:100%; }
    .st-key-status_shell [data-testid="stHorizontalBlock"]:has([class*="st-key-item_card_"])
      [class*="st-key-item_card_"] { height:100%; }
    [class*="st-key-item_card_"] [data-testid="stImage"] { width:100%; aspect-ratio:1.16/1;
        overflow:hidden; border-radius:15px; }
    [class*="st-key-item_card_"] [data-testid="stImage"] > div { height:100%; }
    [class*="st-key-item_card_"] [data-testid="stImage"] img { width:100% !important; height:100% !important;
        border-radius:15px; object-fit:cover; }
    [class*="st-key-item_card_"] [data-testid="stCheckbox"] label {
      gap:.2rem; font-size:.65rem; white-space:nowrap; }
    [class*="st-key-item_card_"] .stButton button { border-radius:12px; min-height:2.25rem; }
    [class*="st-key-item_card_"] [data-testid="stExpander"] { background:rgba(255,255,255,.58); border:0; }
    [class*="st-key-item_status_"] [data-testid="stMarkdownContainer"] { text-align:center; }
    [class*="st-key-item_status_"] [data-testid="stHorizontalBlock"] { gap:.18rem; }
    [class*="st-key-item_status_"] [data-testid="stCheckbox"] label {
      justify-content:center; text-align:center; width:100%; }
    .pager-text { height:2.35rem; display:flex; align-items:center; justify-content:center;
      color:#69778b; font-size:.82rem; font-weight:700; }
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
      background:linear-gradient(110deg,#7777da,#9c9deb); border:0; box-shadow:0 7px 16px rgba(115,115,210,.18); }
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
      background:linear-gradient(110deg,#6868cd,#8d8ee1); }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line); border-radius:20px; }
    @media (max-width:900px) {
      .app-title strong { font-size:1.55rem; }
      div[data-testid="stTabs"] [data-testid="stTab"] { height:4rem; }
      .st-key-status_shell { padding:.85rem; }
      [class*="st-key-item_card_"] { min-height:auto; }
      .st-key-top_info_bar [data-testid="stHorizontalBlock"] { flex-wrap:wrap; gap:.65rem; }
      .st-key-top_info_bar [data-testid="stColumn"] { min-width:calc(50% - .4rem);
        flex:1 1 calc(50% - .4rem); border-right:0 !important; padding-right:0 !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_weather(city: str) -> WeatherSummary:
    """同一城市天气缓存 30 分钟，避免页面每次重跑都请求网络。"""

    return WeatherService().get_today(city)


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_city_from_coordinates(latitude: float, longitude: float) -> str:
    """定位结果缓存一天，避免反复请求地址解析服务。"""

    return WeatherService().city_from_coordinates(latitude, longitude)


def _weekday_text(value: date) -> str:
    return ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")[
        value.weekday()
    ]


def _activity_text(action_type: str, source: str) -> tuple[str, str]:
    action = "清洗" if action_type == "wash" else "晾晒"
    source_label = {
        "manual": "手动勾选",
        "agent_confirmed": "助手确认",
        "seed": "演示数据",
    }.get(source, "其他方式")
    return action, source_label


def _mix_with_white(color: str, white_ratio: float) -> str:
    """把主题色向白色混合，用同一个颜色自动生成深浅层次。"""

    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(round(channel + (255 - channel) * white_ratio) for channel in (red, green, blue))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def _category_themes(preferences: AppearancePreferences) -> dict[str, tuple[str, ...]]:
    accents = {
        "衣物": preferences.clothing_color,
        "床上用品": preferences.bedding_color,
        "玩偶": preferences.toy_color,
        "宠物用品": preferences.pet_color,
    }
    return {
        category: (
            _mix_with_white(accent, .90),
            _mix_with_white(accent, .80),
            _mix_with_white(accent, .52),
            accent,
        )
        for category, accent in accents.items()
    }


def _appearance_css(preferences: AppearancePreferences) -> str:
    """只把颜色偏好转换为 CSS；布局、字号和间距保持固定。"""

    primary_pale = _mix_with_white(preferences.primary_color, .82)
    primary_soft = _mix_with_white(preferences.primary_color, .62)
    reminder_pale = _mix_with_white(preferences.reminder_color, .88)
    reminder_soft = _mix_with_white(preferences.reminder_color, .64)
    return f"""
    <style>
    :root {{
      --ink:{preferences.text_color}; --rose:{preferences.reminder_color};
      --lavender:{preferences.primary_color};
    }}
    .stApp {{ background:{preferences.background_color}; color:{preferences.text_color}; }}
    .app-title, .app-title strong, .compact-value, .item-card-title {{ color:{preferences.text_color}; }}
    .attention-pill {{ color:{preferences.reminder_color}; border-color:{reminder_soft};
      background:{reminder_pale}; }}
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(1)[aria-selected="true"] {{
      background:linear-gradient(110deg,{preferences.primary_color} 0%,{primary_soft} 48%,{primary_pale} 100%);
      border-color:{preferences.primary_color};
    }}
    div[data-testid="stTabs"] [data-testid="stTab"]:nth-child(2)[aria-selected="true"] {{
      background:linear-gradient(110deg,{reminder_soft} 0%,{reminder_pale} 68%,#fff 100%);
      border-color:{preferences.reminder_color};
    }}
    .st-key-status_shell {{
      background:linear-gradient(128deg,{primary_pale} 0%,rgba(255,255,255,.98) 45%,{reminder_pale} 100%); }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
      background:linear-gradient(110deg,{preferences.primary_color},{primary_soft});
      box-shadow:0 7px 16px rgba(70,75,130,.18);
    }}
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
      background:{preferences.primary_color};
    }}
    </style>
    """

DEMO_IMAGE_BY_NAME = {
    "主卧四季被": "main-bedroom-quilt.png",
    "冬季羽绒服": "everyday-clothes.png",
    "日常衣物": "everyday-clothes.png",
    "儿童毛绒熊": "teddy-bear.png",
    "客厅沙发垫": "sofa-cushion.png",
    "宠物睡垫": "pet-bed.png",
}


def _display_image_path(item_name: str, image_path: str | None) -> Path | None:
    """优先显示用户上传图片，否则为演示物品提供随项目附带的插画。"""

    if image_path:
        uploaded = Path(image_path)
        if uploaded.is_file():
            return uploaded
    demo_filename = DEMO_IMAGE_BY_NAME.get(item_name)
    if demo_filename:
        demo_path = Path(__file__).resolve().parent / "assets" / "demo" / demo_filename
        if demo_path.is_file():
            return demo_path
    return None


def _card_theme_css(
    item_id: int, category: str, preferences: AppearancePreferences
) -> str:
    """让 Streamlit 原生容器呈现分类渐变，同时保留内部按钮交互。"""

    category_themes = _category_themes(preferences)
    start, end, border, accent = category_themes.get(
        category, category_themes["床上用品"]
    )
    category_key = {
        "衣物": "clothing", "床上用品": "bedding",
        "玩偶": "toy", "宠物用品": "pet",
    }.get(category, "bedding")
    return f"""
    <style>
    .st-key-item_card_{category_key}_{item_id} {{
      background:linear-gradient(160deg,{start} 0%,{end} 100%);
      border:1px solid {border};
    }}
    .st-key-item_card_{category_key}_{item_id} .category-pill {{ color:{accent}; }}
    .st-key-item_card_{category_key}_{item_id} .stButton button {{ color:{accent}; border-color:{border}; background:rgba(255,255,255,.78); }}
    .st-key-item_card_{category_key}_{item_id} input[type="checkbox"] {{ accent-color:{accent}; }}
    .st-key-item_status_{category_key}_{item_id} {{
      margin-top:.45rem; padding:.5rem .52rem .25rem; border-radius:15px;
      border:1px solid rgba(255,255,255,.92); background:rgba(255,255,255,.82);
    }}
    .st-key-item_status_{category_key}_{item_id} [data-testid="stColumn"]:first-child {{
      border-right:1px solid {border}; padding-right:.35rem;
    }}
    </style>
    """


def _status_html(label: str, status) -> str:
    """把状态压缩成适合卡片的三行信息。"""

    due_class = " is-due" if status.is_due else ""
    return (
        f'<div class="status-label">{escape(label)}</div>'
        f'<div class="status-main{due_class}">{status.emoji} {escape(status.label)}</div>'
        f'<div class="status-days">距上次 {escape(elapsed_text(status))}</div>'
    )


def _render_auth_screen(accounts: AccountRepository) -> None:
    """未登录时只显示本地账户入口，避免跨账户看到物品。"""

    left, center, right = st.columns([1, 1.45, 1])
    with center:
        with st.container(key="auth_shell"):
            st.markdown('<div class="auth-title">家庭洗晒助手</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="auth-subtitle">先登录个人账户，再进入个人空间或共享家庭</div>',
                unsafe_allow_html=True,
            )
            auth_mode = st.radio(
                "账户操作", ["登录", "创建账户"], horizontal=True, label_visibility="collapsed"
            )
            if auth_mode == "登录":
                with st.form("login_form"):
                    identifier = st.text_input("手机号或邮箱")
                    password = st.text_input("密码", type="password")
                    submitted = st.form_submit_button("登录", type="primary", width="stretch")
                if submitted:
                    try:
                        user = accounts.authenticate(identifier, password)
                        st.session_state["user_id"] = user.id
                        st.session_state["workspace"] = "personal"
                        st.rerun()
                    except AccountError as error:
                        st.error(str(error))
                    except sqlite3.Error:
                        st.error("登录暂时失败，请稍后重试。")
            else:
                with st.form("register_form"):
                    identifier = st.text_input("手机号或邮箱")
                    display_name = st.text_input("昵称（可选）")
                    password = st.text_input("设置密码", type="password")
                    password_confirmation = st.text_input("再次输入密码", type="password")
                    submitted = st.form_submit_button(
                        "创建个人账户", type="primary", width="stretch"
                    )
                if submitted:
                    if password != password_confirmation:
                        st.error("两次输入的密码不一致。")
                    else:
                        try:
                            user = accounts.register(
                                identifier, password, display_name=display_name
                            )
                            st.session_state["user_id"] = user.id
                            st.session_state["workspace"] = "personal"
                            st.session_state["flash_message"] = "账户已创建，已进入个人空间。"
                            st.rerun()
                        except AccountError as error:
                            st.error(str(error))
                        except sqlite3.Error:
                            st.error("账户创建失败，请稍后重试。")
            st.caption("当前账户保存在本机 SQLite 中；部署到共享服务器后才能跨设备访问。")


settings = get_settings()
today = date.today()
upload_directory = settings.database_path.parent / "uploads"
try:
    initialize_database(settings.database_path)
    account_repository = AccountRepository(settings.database_path)
except sqlite3.Error:
    st.error("数据库暂时无法打开。请确认数据目录可写，然后刷新页面重试。")
    st.stop()

current_user = account_repository.get_user(st.session_state.get("user_id", -1))
if current_user is None:
    _render_auth_screen(account_repository)
    st.stop()

appearance_preferences = account_repository.get_site_appearance_preferences()
st.markdown(_appearance_css(appearance_preferences), unsafe_allow_html=True)
visual_design = account_repository.get_site_visual_design()
st.markdown(visual_design_css(visual_design), unsafe_allow_html=True)


def _clear_appearance_widget_state() -> None:
    for key in (
        "appearance_background", "appearance_text", "appearance_primary",
        "appearance_reminder", "appearance_clothing", "appearance_bedding",
        "appearance_toy", "appearance_pet",
    ):
        st.session_state.pop(key, None)


def _render_appearance_settings() -> None:
    """让非技术用户通过控件修改并保存账户主题。"""

    st.caption("下方预览会随选择更新；点击保存后应用到整个网页，并保留到下次登录。")
    basic_column, category_column = st.columns(2)
    with basic_column:
        st.markdown("#### 页面与强调色")
        background_color = st.color_picker(
            "页面背景", appearance_preferences.background_color, key="appearance_background"
        )
        text_color = st.color_picker(
            "主要文字", appearance_preferences.text_color, key="appearance_text"
        )
        primary_color = st.color_picker(
            "主色与物品状态标签", appearance_preferences.primary_color,
            key="appearance_primary",
        )
        reminder_color = st.color_picker(
            "提醒与智能助手", appearance_preferences.reminder_color,
            key="appearance_reminder",
        )
    with category_column:
        st.markdown("#### 四类物品颜色")
        clothing_color = st.color_picker(
            "衣物", appearance_preferences.clothing_color, key="appearance_clothing"
        )
        bedding_color = st.color_picker(
            "床上用品", appearance_preferences.bedding_color, key="appearance_bedding"
        )
        toy_color = st.color_picker(
            "玩偶", appearance_preferences.toy_color, key="appearance_toy"
        )
        pet_color = st.color_picker(
            "宠物用品", appearance_preferences.pet_color, key="appearance_pet"
        )

    preview_colors = (
        ("衣物", clothing_color), ("床上用品", bedding_color),
        ("玩偶", toy_color), ("宠物用品", pet_color),
    )
    preview_cards = "".join(
        '<div style="flex:1;min-width:110px;padding:.75rem;text-align:center;'
        f'border-radius:22px;color:{text_color};border:1px solid {_mix_with_white(color, .5)};'
        f'background:linear-gradient(145deg,{_mix_with_white(color, .9)},{_mix_with_white(color, .72)});">'
        f'<strong>{label}</strong><br><small>渐变卡片</small></div>'
        for label, color in preview_colors
    )
    st.markdown(
        '<div style="margin:.8rem 0;padding:1rem;border:1px solid #e3e7ef;'
        f'border-radius:22px;background:{background_color};">'
        f'<div style="color:{text_color};font-weight:700;margin-bottom:.7rem;">主题预览 '
        f'<span style="color:{reminder_color};font-size:.8em;">需要关注 2 项</span></div>'
        f'<div style="display:flex;gap:.55rem;flex-wrap:wrap;">{preview_cards}</div></div>',
        unsafe_allow_html=True,
    )

    save_column, reset_column = st.columns(2)
    with save_column:
        if st.button("保存并应用", type="primary", width="stretch"):
            try:
                account_repository.update_appearance_preferences(
                    current_user.id,
                    AppearancePreferences(
                        background_color=background_color,
                        text_color=text_color,
                        primary_color=primary_color,
                        reminder_color=reminder_color,
                        clothing_color=clothing_color,
                        bedding_color=bedding_color,
                        toy_color=toy_color,
                        pet_color=pet_color,
                    ),
                )
                st.session_state["flash_message"] = "外观设置已保存并应用。"
                st.rerun()
            except (AccountError, sqlite3.Error) as error:
                st.error(f"外观保存失败：{error}")
    with reset_column:
        if st.button("恢复默认主题", width="stretch"):
            try:
                account_repository.reset_appearance_preferences(current_user.id)
                _clear_appearance_widget_state()
                st.session_state["flash_message"] = "已恢复默认主题。"
                st.rerun()
            except sqlite3.Error:
                st.error("暂时无法恢复默认主题，请稍后重试。")


def _render_visual_design_settings() -> None:
    """挂载颜色与效果画布，并在用户明确保存时写入主题。"""

    st.caption(
        "点击模块后可设置颜色、透明度、渐变、毛玻璃、边框、圆角和阴影。"
        "位置、尺寸、字体和间距固定，始终保持整齐的响应式排列。"
    )
    component_key = f"visual_designer_{current_user.id}"

    def _persist_visual_design() -> None:
        component_state = st.session_state.get(component_key, {})
        design_json = component_state.get("save_requested") if component_state else None
        if not design_json:
            st.session_state["flash_message"] = "设计尚未同步，请再点击一次保存。"
            return
        try:
            account_repository.update_visual_design(
                current_user.id, json.loads(design_json)
            )
            st.session_state["flash_message"] = "高级页面设计已保存并应用。"
            st.session_state["design_saved_notice"] = True
        except (AccountError, json.JSONDecodeError, sqlite3.Error) as error:
            st.session_state["flash_message"] = f"设计保存失败：{error}"

    result = render_visual_designer(
        design=visual_design,
        default_design=DEFAULT_VISUAL_DESIGN,
        key=component_key,
        on_save=_persist_visual_design,
    )
    if result.get("save_requested"):
        st.rerun(scope="app")


@st.dialog("🎨 外观设计", width="large")
def _manage_design() -> None:
    """在一个连续面板中统一编辑各区域颜色与效果。"""

    _render_visual_design_settings()


@st.dialog("家庭与共享")
def _manage_families() -> None:
    """创建或加入家庭；家庭码可交给同一部署中的其他账户。"""

    families_now = account_repository.list_families(current_user.id)
    if families_now:
        st.markdown("#### 已加入的家庭")
        for family in families_now:
            role_text = "创建者" if family.role == "owner" else "成员"
            st.markdown(f"**{escape(family.name)}** · {role_text}")
            st.code(family.join_code, language=None)
    else:
        st.caption("你还没有加入家庭，可以创建一个或输入家庭码加入。")

    st.divider()
    with st.form("create_family_form"):
        family_name = st.text_input("家庭名称", placeholder="例如：幸福小家")
        create_family_submitted = st.form_submit_button(
            "创建家庭并生成家庭码", type="primary", width="stretch"
        )
    if create_family_submitted:
        try:
            family = account_repository.create_family(current_user.id, family_name)
            st.session_state["workspace"] = f"family:{family.id}"
            st.session_state["flash_message"] = (
                f"已创建“{family.name}”，家庭码为 {family.join_code}。"
            )
            st.rerun()
        except AccountError as error:
            st.error(str(error))
        except sqlite3.Error:
            st.error("家庭创建失败，请稍后重试。")

    with st.form("join_family_form"):
        join_code = st.text_input("家庭码", placeholder="输入 8 位家庭码")
        join_family_submitted = st.form_submit_button("加入家庭", width="stretch")
    if join_family_submitted:
        try:
            family = account_repository.join_family(current_user.id, join_code)
            st.session_state["workspace"] = f"family:{family.id}"
            st.session_state["flash_message"] = f"已加入“{family.name}”。"
            st.rerun()
        except AccountError as error:
            st.error(str(error))
        except sqlite3.Error:
            st.error("加入家庭失败，请稍后重试。")


families = account_repository.list_families(current_user.id)
workspace_labels = {"personal": "我的个人空间"}
workspace_labels.update({f"family:{family.id}": family.name for family in families})
selected_workspace = st.session_state.get("workspace", "personal")
if selected_workspace not in workspace_labels:
    selected_workspace = "personal"
    st.session_state["workspace"] = selected_workspace

active_family_id = (
    int(selected_workspace.split(":", 1)[1])
    if selected_workspace.startswith("family:")
    else None
)
active_owner_user_id = current_user.id if active_family_id is None else None
repository = ItemRepository(
    settings.database_path,
    owner_user_id=active_owner_user_id,
    family_id=active_family_id,
)
try:
    items = repository.list_items()
except sqlite3.Error:
    st.error("当前空间的物品暂时无法读取，请稍后刷新。")
    st.stop()


@st.dialog("编辑物品")
def _quick_edit_item(item_id: int) -> None:
    """从状态卡片直接打开的轻量编辑窗口。"""

    item = repository.get_item(item_id)
    if item is None:
        st.warning("该物品已不存在，请刷新页面。")
        return
    with st.form(f"quick_edit_{item_id}"):
        edit_name = st.text_input("物品名称", value=item.name)
        edit_category = st.selectbox(
            "类别", ITEM_CATEGORIES, index=ITEM_CATEGORIES.index(item.category)
        )
        edit_wash = st.text_input(
            "建议清洗周期（天，可选）",
            value="" if item.wash_interval_days is None else str(item.wash_interval_days),
        )
        edit_dry = st.text_input(
            "建议晾晒周期（天，可选）",
            value="" if item.dry_interval_days is None else str(item.dry_interval_days),
        )
        replacement_image = st.file_uploader(
            "替换照片（可选）",
            type=["jpg", "jpeg", "png", "webp"],
            max_upload_size=5,
            key=f"quick_replace_image_{item_id}",
        )
        edit_notes = st.text_area("备注（可选）", value=item.notes, max_chars=500)
        submitted = st.form_submit_button("保存修改", type="primary", width="stretch")
    if submitted:
        saved_replacement: Path | None = None
        try:
            if replacement_image is not None:
                saved_replacement = save_item_image(
                    replacement_image.getvalue(), upload_directory
                )
            repository.update_item(
                item.id,
                name=edit_name,
                category=edit_category,
                wash_interval_days=parse_optional_interval(edit_wash, "清洗周期"),
                dry_interval_days=parse_optional_interval(edit_dry, "晾晒周期"),
                notes=edit_notes,
                image_path=str(saved_replacement) if saved_replacement else item.image_path,
            )
            st.session_state["flash_message"] = f"已更新“{edit_name.strip()}”。"
            st.rerun()
        except (ItemValidationError, ImageStorageError) as error:
            if saved_replacement:
                saved_replacement.unlink(missing_ok=True)
            st.error(str(error))
        except sqlite3.Error:
            if saved_replacement:
                saved_replacement.unlink(missing_ok=True)
            st.error("修改保存失败，请稍后重试。")

    st.divider()
    confirm_delete = st.checkbox(
        f"我确认删除“{item.name}”", key=f"quick_confirm_delete_{item.id}"
    )
    if st.button(
        "删除这个物品",
        disabled=not confirm_delete,
        key=f"quick_delete_{item.id}",
        width="stretch",
    ):
        try:
            if repository.delete_item(item.id):
                st.session_state["flash_message"] = f"已删除“{item.name}”。"
                st.rerun()
            st.warning("该物品已不存在，请刷新页面。")
        except sqlite3.Error:
            st.error("删除失败，数据库可能正忙，请稍后重试。")

statuses = [
    (
        item,
        calculate_action_status(item.last_washed_at, item.wash_interval_days, today=today),
        calculate_action_status(item.last_dried_at, item.dry_interval_days, today=today),
    )
    for item in items
]
attention_names = due_wash_item_names(items, today=today)

weather: WeatherSummary | None = None
weather_error: str | None = None
city_options = ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京", "武汉", "西安"]
if settings.default_city not in city_options:
    city_options.insert(0, settings.default_city)

city_state_key = f"preferred_city_{current_user.id}"
location_result = get_device_location(
    enabled=not bool(current_user.preferred_city),
    key=f"device_location_{current_user.id}",
)
if (
    not current_user.preferred_city
    and location_result
    and location_result.get("status") == "ok"
):
    try:
        located_city = _cached_city_from_coordinates(
            round(float(location_result["latitude"]), 4),
            round(float(location_result["longitude"]), 4),
        )
        account_repository.update_preferred_city(current_user.id, located_city)
        st.session_state[city_state_key] = located_city
        st.session_state["flash_message"] = f"已根据当前位置切换到{located_city}。"
        st.rerun()
    except (KeyError, TypeError, ValueError, AccountError, WeatherError) as error:
        st.session_state["location_notice"] = str(error)

preferred_city = current_user.preferred_city or settings.default_city
if preferred_city not in city_options:
    city_options.insert(0, preferred_city)
if city_state_key not in st.session_state:
    st.session_state[city_state_key] = preferred_city

with st.container(key="account_bar"):
    if current_user.is_ui_admin:
        account_column, workspace_column, design_column, family_column, logout_column = st.columns(
            [1.08, 1.2, .82, .72, .56], vertical_alignment="center"
        )
    else:
        account_column, workspace_column, family_column, logout_column = st.columns(
            [1.2, 1.35, .78, .6], vertical_alignment="center"
        )
    with account_column:
        st.markdown(
            f'<div class="account-name">你好，{escape(current_user.display_name)}</div>',
            unsafe_allow_html=True,
        )
    with workspace_column:
        new_workspace = st.selectbox(
            "当前空间",
            list(workspace_labels),
            index=list(workspace_labels).index(selected_workspace),
            format_func=workspace_labels.get,
            label_visibility="collapsed",
        )
        if new_workspace != selected_workspace:
            st.session_state["workspace"] = new_workspace
            st.rerun()
    if current_user.is_ui_admin:
        with design_column:
            if st.button("外观设计", width="stretch"):
                _manage_design()
    with family_column:
        if st.button("家庭管理", width="stretch"):
            _manage_families()
    with logout_column:
        if st.button("退出", width="stretch"):
            st.session_state.clear()
            st.rerun()

header_title_column, header_info_column = st.columns(
    [1, 1.45], vertical_alignment="center"
)
with header_title_column:
    st.markdown(
        '<div class="app-title"><strong>家庭洗晒助手</strong>'
        '<span>把清洗周期、晾晒记录和今天的天气放在一起</span></div>',
        unsafe_allow_html=True,
    )
with header_info_column:
    with st.container(key="top_info_bar"):
        city_column, date_column, weather_column, attention_column = st.columns(
            [1.15, 1, 1, 1.35], vertical_alignment="center"
        )
        with city_column:
            city = st.selectbox(
                "城市",
                city_options,
                accept_new_options=True,
                help=(
                    "手机首次使用会请求定位授权；坐标仅用于通过 OpenStreetMap "
                    "Nominatim 识别城市，不写入数据库。也可手动选择，城市会保存到账户。"
                ),
                label_visibility="collapsed",
                key=city_state_key,
            )
            if str(city).strip() != preferred_city:
                try:
                    current_user = account_repository.update_preferred_city(
                        current_user.id, str(city)
                    )
                    preferred_city = current_user.preferred_city
                except (AccountError, sqlite3.Error) as error:
                    st.session_state["location_notice"] = str(error)
        try:
            weather = _cached_weather(str(city))
        except WeatherError as error:
            weather_error = str(error)
        with date_column:
            st.markdown(
                '<div class="compact-block"><div class="compact-label">日期</div>'
                f'<div class="compact-value">{today.month}月{today.day}日</div></div>',
                unsafe_allow_html=True,
            )
        with weather_column:
            weather_text = (
                f"{compact_weather_label(weather.weather_code)} · {weather.current_temperature:.0f}°"
                if weather
                else "暂不可用"
            )
            st.markdown(
                '<div class="compact-block"><div class="compact-label">天气</div>'
                f'<div class="compact-value">{escape(weather_text)}</div></div>',
                unsafe_allow_html=True,
            )
        with attention_column:
            attention_class = "" if attention_names else " is-clear"
            attention_text = f"需要关注 {len(attention_names)} 项" if attention_names else "需要关注：无"
            st.markdown(
                f'<div class="attention-pill{attention_class}">🔔 {escape(attention_text)}</div>',
                unsafe_allow_html=True,
            )

if location_notice := st.session_state.pop("location_notice", None):
    st.caption(f"定位提示：{location_notice}；可以继续手动选择城市。")

if weather_error:
    st.markdown(
        f'<div class="weather-note">天气暂不可用：{escape(weather_error)}，当前仅按周期判断。</div>',
        unsafe_allow_html=True,
    )
if flash_message := st.session_state.pop("flash_message", None):
    st.success(flash_message)
if st.session_state.pop("design_saved_notice", False):
    st.toast("设计已保存，正式页面已经刷新。", icon="✅")

dashboard_tab, agent_tab, add_tab = st.tabs(
    ["🏠 物品状态", "🤖 智能助手", "➕ 添加物品"]
)

with dashboard_tab:
    with st.container(key="status_shell"):
        if not items:
            with st.container(border=True):
                st.subheader("先建立你的家庭物品清单")
                st.write("添加物品后，这里会自动显示距上次清洗、晾晒的天数和智能建议。")
                if st.button("载入演示数据", type="primary"):
                    try:
                        inserted = seed_demo_data(
                            settings.database_path,
                            owner_user_id=active_owner_user_id,
                            family_id=active_family_id,
                        )
                        st.session_state["flash_message"] = f"已新增 {inserted} 条演示物品。"
                        st.rerun()
                    except sqlite3.Error:
                        st.error("演示数据写入失败，请稍后重试。")

        if items:
            category_column, sort_action_column, sort_order_column, search_column = st.columns(
                [1, 1, .8, 1.45], vertical_alignment="bottom"
            )
            categories_present = sorted({item.category for item in items})
            with category_column:
                category_filter = st.selectbox("物品分类", ["全部", *categories_present])
            with sort_action_column:
                sort_action_text = st.selectbox("排序项目", ["清洗", "晾晒"])
            with sort_order_column:
                sort_order_text = st.selectbox("天数顺序", ["降序", "升序"])
            with search_column:
                search_query = st.text_input(
                    "搜索物品", placeholder="搜索名称、分类或备注", icon="🔎"
                )

            searched_items = search_items(items, search_query)
            visible_items = filter_and_sort_items(
                searched_items,
                action="wash" if sort_action_text == "清洗" else "dry",
                descending=sort_order_text == "降序",
                category=None if category_filter == "全部" else category_filter,
                today=today,
            )
            visible_statuses = [
                (
                    item,
                    calculate_action_status(
                        item.last_washed_at, item.wash_interval_days, today=today
                    ),
                    calculate_action_status(
                        item.last_dried_at, item.dry_interval_days, today=today
                    ),
                )
                for item in visible_items
            ]
            st.caption(f"显示 {len(visible_statuses)} / {len(items)} 件物品")
        else:
            visible_statuses = []

        if items and not visible_statuses:
            st.info("没有找到符合条件的物品，可以清空搜索或更换分类。")

        page_size = 5
        total_pages = max(1, (len(visible_statuses) + page_size - 1) // page_size)
        current_page = min(max(st.session_state.get("item_page", 1), 1), total_pages)
        st.session_state["item_page"] = current_page
        pager_left, pager_center, pager_right = st.columns([1, 1.2, 1])
        with pager_left:
            if st.button(
                "← 上一页",
                disabled=current_page <= 1,
                key="items_previous_page",
                width="stretch",
            ):
                st.session_state["item_page"] = current_page - 1
                st.rerun()
        with pager_center:
            st.markdown(
                f'<div class="pager-text">第 {current_page} / {total_pages} 页 · 每页最多 {page_size} 件</div>',
                unsafe_allow_html=True,
            )
        with pager_right:
            if st.button(
                "下一页 →",
                disabled=current_page >= total_pages,
                key="items_next_page",
                width="stretch",
            ):
                st.session_state["item_page"] = current_page + 1
                st.rerun()

        category_emoji = {
            "衣物": "👕", "床上用品": "🛏️", "玩偶": "🧸", "宠物用品": "🐾"
        }
        page_start = (current_page - 1) * page_size
        row_items = visible_statuses[page_start : page_start + page_size]
        if row_items:
            # 始终保留五个等宽槽位，末页不足五件时留空，避免卡片被横向放大。
            card_columns = st.columns(page_size, gap="small")
            for card_column, (item, wash_status, dry_status) in zip(card_columns, row_items):
                category_key = {
                    "衣物": "clothing", "床上用品": "bedding",
                    "玩偶": "toy", "宠物用品": "pet",
                }.get(item.category, "bedding")
                sunny_due = bool(
                    weather and weather.is_sunny and (wash_status.is_due or dry_status.is_due)
                )
                face = choose_item_emoji(
                    wash_status,
                    dry_status,
                    is_sunny=bool(weather and weather.is_sunny),
                )
                st.markdown(
                    _card_theme_css(item.id, item.category, appearance_preferences),
                    unsafe_allow_html=True,
                )
                with card_column:
                    with st.container(key=f"item_card_{category_key}_{item.id}"):
                        st.markdown(
                            f'<div class="item-card-title">{escape(face)} {escape(item.name)}</div>',
                            unsafe_allow_html=True,
                        )
                        display_image = _display_image_path(item.name, item.image_path)
                        if display_image:
                            st.image(str(display_image), width="stretch")
                        else:
                            st.markdown(
                                f'<div class="placeholder-art">{category_emoji.get(item.category, "🧺")}</div>',
                                unsafe_allow_html=True,
                            )
                        st.markdown(
                            f'<span class="category-pill">{escape(item.category)}</span>',
                            unsafe_allow_html=True,
                        )

                        washed_today = recorded_today(item.last_washed_at, today=today)
                        dried_today = recorded_today(item.last_dried_at, today=today)
                        with st.container(key=f"item_status_{category_key}_{item.id}"):
                            wash_column, dry_column = st.columns(2, gap="small")
                            with wash_column:
                                st.markdown(_status_html("清洗", wash_status), unsafe_allow_html=True)
                                wash_checked = st.checkbox(
                                    "今天完成" if not washed_today else "今日已完成",
                                    value=washed_today,
                                    disabled=washed_today,
                                    key=f"wash_today_{item.id}_{today.isoformat()}",
                                )
                            with dry_column:
                                st.markdown(_status_html("晾晒", dry_status), unsafe_allow_html=True)
                                dry_checked = st.checkbox(
                                    "今天完成" if not dried_today else "今日已完成",
                                    value=dried_today,
                                    disabled=dried_today,
                                    key=f"dry_today_{item.id}_{today.isoformat()}",
                                )

                        if sunny_due:
                            st.markdown(
                                '<div class="status-main is-due">☀ 晴天且已到周期，今天适合处理</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                '<div class="status-main is-due" aria-hidden="true" '
                                'style="visibility:hidden">☀ 晴天且已到周期，今天适合处理</div>',
                                unsafe_allow_html=True,
                            )
                        if st.button(
                            "✎ 编辑",
                            key=f"quick_edit_{item.id}",
                            width="stretch",
                        ):
                            _quick_edit_item(item.id)
                        history = repository.list_activity_records(item.id, limit=5)
                        with st.expander(f"最近记录 · {len(history)}"):
                            if not history:
                                st.caption("暂无清洗或晾晒记录。")
                            for record in history:
                                action_label, source_label = _activity_text(
                                    record.action_type, record.source
                                )
                                st.write(f"**{record.performed_at[:10]}**　{action_label}")
                                st.caption(
                                    f"来源：{source_label}"
                                    + (f"　·　{record.notes}" if record.notes else "")
                                )
                        if item.notes:
                            st.caption(item.notes)

                        try:
                            if wash_checked and not washed_today:
                                created = repository.record_activity(
                                    item.id, "wash", performed_at=today
                                )
                                st.session_state["flash_message"] = (
                                    f"已记录“{item.name}”今天完成清洗。"
                                    if created
                                    else f"“{item.name}”今天的清洗记录已经存在，没有重复写入。"
                                )
                                st.rerun()
                            if dry_checked and not dried_today:
                                created = repository.record_activity(
                                    item.id, "dry", performed_at=today
                                )
                                st.session_state["flash_message"] = (
                                    f"已记录“{item.name}”今天完成晾晒。"
                                    if created
                                    else f"“{item.name}”今天的晾晒记录已经存在，没有重复写入。"
                                )
                                st.rerun()
                        except (sqlite3.Error, ItemValidationError):
                            st.error("完成记录写入失败，请稍后重新勾选。")

with agent_tab:
    with st.container(key="agent_shell"):
        st.subheader("结合天气与周期安排洗晒")
        st.caption("助手会先读取当前城市天气和物品记录；雨天或湿度过高时不会安排户外晾晒。")
        agent_request = st.text_area(
            "你想做什么？",
            value="帮我安排今天的洗晒计划",
            placeholder="例如：今天适合处理哪些物品？哪些应该暂缓？",
        )
        if st.button("开始安排", type="primary", width="stretch", key="run_agent"):
            with st.spinner("正在读取天气和物品状态……"):
                st.session_state["agent_result"] = run_laundry_agent(
                    agent_request,
                    city=str(city),
                    repository=repository,
                    weather=weather,
                    today=today,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    base_url=settings.openai_base_url,
                )
        agent_result = st.session_state.get("agent_result")
        if agent_result:
            st.markdown(f"**当前模式：{agent_result.mode}**")
            if agent_result.fallback_reason:
                st.caption(agent_result.fallback_reason)
            st.markdown(agent_result.answer)
            with st.expander("查看工具调用摘要"):
                for trace in agent_result.trace:
                    st.write(f"{'✓' if trace.ok else '·'} `{trace.name}`：{trace.summary}")
            for index, action in enumerate(agent_result.pending_actions):
                st.info(
                    f"待确认：{action['performed_at']} {action['action_label']}“{action['item_name']}”"
                )
                if st.button(
                    "确认并写入记录",
                    key=f"confirm_agent_action_{index}_{action['item_id']}_{action['action_type']}",
                ):
                    result = LaundryToolRegistry(repository, today=today).execute(
                        "complete_laundry_task",
                        {
                            "item_id": action["item_id"],
                            "action_type": action["action_type"],
                            "performed_at": action["performed_at"],
                        },
                        allow_write=True,
                    )
                    if result.get("ok"):
                        st.session_state.pop("agent_result", None)
                        st.session_state["flash_message"] = str(
                            result.get("message", "已确认并更新物品记录。")
                        )
                        st.rerun()
                    st.error(str(result.get("error", "写入失败，请稍后重试。")))

with add_tab:
    center_left, form_column, center_right = st.columns([1, 2, 1])
    with form_column:
        with st.container(key="add_shell"):
            st.subheader("添加物品")
            with st.form("create_item_form", clear_on_submit=True):
                name = st.text_input("物品名称", placeholder="例如：主卧四季被")
                category = st.selectbox("类别", ITEM_CATEGORIES)
                wash_interval_days = st.text_input(
                    "建议清洗周期（天，可选）", placeholder="例如：30；不提醒可留空"
                )
                dry_interval_days = st.text_input(
                    "建议晾晒周期（天，可选）", placeholder="例如：14；不提醒可留空"
                )
                uploaded_image = st.file_uploader(
                    "物品照片（可选）",
                    type=["jpg", "jpeg", "png", "webp"],
                    max_upload_size=5,
                    help="用于区分相似物品；图片只保存在本地 data/uploads。",
                )
                notes = st.text_area("备注（可选）", max_chars=500)
                create_submitted = st.form_submit_button("添加物品", type="primary", width="stretch")
            if create_submitted:
                saved_image: Path | None = None
                try:
                    if uploaded_image is not None:
                        saved_image = save_item_image(
                            uploaded_image.getvalue(), upload_directory
                        )
                    created = repository.create_item(
                        name=name,
                        category=category,
                        wash_interval_days=parse_optional_interval(
                            wash_interval_days, "清洗周期"
                        ),
                        dry_interval_days=parse_optional_interval(
                            dry_interval_days, "晾晒周期"
                        ),
                        notes=notes,
                        image_path=str(saved_image) if saved_image else None,
                    )
                    st.session_state["flash_message"] = f"已添加“{created.name}”。"
                    st.rerun()
                except (ItemValidationError, ImageStorageError) as error:
                    if saved_image:
                        saved_image.unlink(missing_ok=True)
                    st.error(str(error))
                except sqlite3.Error:
                    if saved_image:
                        saved_image.unlink(missing_ok=True)
                    st.error("物品保存失败，请确认数据库未被其他程序占用后重试。")

with st.expander("数据与运行说明"):
    st.write(f"数据库：`{settings.database_path}`")
    st.write("清洗、晾晒日期以运行设备的今天为准；天气每 30 分钟刷新缓存。")
    st.write("建议周期是可以自行调整的生活管理参考，不构成卫生或医学建议。")
    st.info("当前不需要模型密钥；状态和天气规则可以独立运行。")
