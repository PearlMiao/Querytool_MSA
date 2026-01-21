
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

# ✅ 隐藏 “Press Ctrl+Enter to apply”
st.markdown(
    """
    <style>
    /* Hide the "Press Ctrl+Enter to apply" / input instructions text */
    [data-testid="InputInstructions"] { display: none !important; }
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

    # 常见大小写变体兜底
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
