
import re
from pathlib import Path

import pandas as pd
import streamlit as st


# ----------------------------
# Page config
# ----------------------------
st.set_page_config(
    page_title="MSA Domain Query Tool",
    page_icon="🔎",
    layout="wide",
)

# ✅ 隐藏输入框右下角的提示：Press Ctrl+Enter to apply
st.markdown(
    """
    <style>
    [data-testid="InputInstructions"] { display: none !important; }
    /* 兜底：部分版本/主题下提示可能在 text_area 内部 small 标签里 */
    div[data-testid="stTextArea"] small { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_FILE = "cleaned_text.csv"
MAX_INPUT = 1000  # 只允许提示这一条：建议一次输入不超过 1000 个 domain


# ----------------------------
# Helpers
# ----------------------------
def resolve_data_file(preferred_name: str) -> str:
    """
    兜底处理文件名大小写问题（适配 Linux/Streamlit Cloud）：
    - 优先用 preferred_name
    - 如果不存在，尝试同名但 .CSV / .csv 大小写变体
    - 仍不存在则返回 preferred_name（后续 load_data 会返回空DF并静默）
    """
    p = Path(preferred_name)
    if p.exists():
        return preferred_name

    alt_names = []
    if preferred_name.lower().endswith(".csv"):
        base = preferred_name[:-4]
        alt_names = [base + ".CSV", base + ".Csv", base + ".cSv", base + ".csV"]
    else:
        alt_names = [preferred_name.lower(), preferred_name.upper()]

    for name in alt_names:
        if Path(name).exists():
            return name

    return preferred_name


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def clean_domain_token(token: str) -> str:
    """
    将输入清洗为“纯域名”：
    - 去掉 http:// https://
    - 去掉 www.
    - 去掉路径 /xxx、参数 ?a=b、hash #xx
    """
    if not token:
        return ""
    t = token.strip()
    t = re.sub(r"^\s*https?://", "", t, flags=re.IGNORECASE)
    t = re.split(r"[/?#]", t, maxsplit=1)[0].strip()
    t = re.sub(r"^www\.", "", t, flags=re.IGNORECASE)
    t = t.strip(".")
    return t


@st.cache_data(show_spinner=False)
def load_data(csv_name: str) -> pd.DataFrame:
    """读取单列 domain CSV。若不存在/读取失败：返回空DF（不向用户展示任何技术提示）"""
    csv_name = resolve_data_file(csv_name)
    p = Path(csv_name)
    if not p.exists():
        return pd.DataFrame(columns=["domain"])

    try:
        df = pd.read_csv(p, header=None, names=["domain"], dtype=str, encoding="utf-8")
    except Exception:
