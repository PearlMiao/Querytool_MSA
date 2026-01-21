
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

# ✅ 隐藏输入框右下角提示：Press Ctrl+Enter to apply
st.markdown(
    """
    <style>
    [data-testid="InputInstructions"] { display: none !important; }
    div[data-testid="stTextArea"] small { display: none !important; } /* 兜底 */
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
    """
    p = Path(preferred_name)
    if p.exists():
        return preferred_name

    if preferred_name.lower().endswith(".csv"):
        base = preferred_name[:-4]
        for name in (base + ".CSV", base + ".Csv", base + ".cSv", base + ".csV"):
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

    # ✅ 这里是你报错最常见的区域：确保 except 下方有正确缩进的代码块
    try:
        df = pd.read_csv(p, header=None, names=["domain"], dtype=str, encoding="utf-8")
    except Exception:
        try:
            df = pd.read_csv(p, header=None, names=["domain"], dtype=str, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame(columns=["domain"])

    # 标准化数据库里的 domain：去空、去重、并清洗为纯域名（与输入规则一致）
    df["domain"] = (
        df["domain"]
        .fillna("")
        .astype(str)
        .str.strip()
        .apply(clean_domain_token)
    )
    df = df[df["domain"] != ""]
    df = df.drop_duplicates().reset_index(drop=True)
    return df


def is_match(text: str, q: str, mode: str) -> bool:
    if not q:
        return False
    t = normalize(text)
    qn = normalize(q)

    if mode == "完全匹配":
        return t == qn
    if mode == "前缀一致":
        return t.startswith(qn)

    return False


def parse_queries(raw: str) -> list[str]:
    """
    多 domain 输入：每行一个。
    兼容：同一行里用逗号/分号分隔也会拆开。
    自动清洗：去掉 http(s)://、www.、路径参数等，只保留域名。
    """
    if not raw:
        return []

    items: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[，,;；]+", line)
        for p in parts:
            p = clean_domain_token(p)
            if p:
                items.append(p)

    # 去重但保持顺序
    seen = set()
    uniq: list[str] = []
    for x in items:
        key = normalize(x)
        if key not in seen:
            seen.add(key)
            uniq.append(x)
    return uniq


# ----------------------------
# UI
# ----------------------------
st.title("🔎 MSA Domain Query Tool")
st.caption("数据：自2025/01/01至2025/12/31 在MSA有投放历史的Domain")

df = load_data(DATA_FILE)

st.subheader("查询")

# 初始化状态
if "run_query" not in st.session_state:
    st.session_state["run_query"] = False

# 输入框 + 按钮（同一行）
col_inp, col_btn = st.columns([6, 1], gap="small")

with col_inp:
    # ✅ 用 key 让输入内容在 rerun/切换匹配方式时保持不丢
    st.text_area(
        "输入 domain（支持换行批量，每行一个）",
        placeholder="例如：\nabc.com\nshop.cn",
        height=130,
        key="domain_input",
    )

with col_btn:
    st.write("")
    if st.button("🔍 开始查询", use_container_width=True):
        st.session_state["run_query"] = True
        st.rerun()

    if st.button("🧹 全部清空", use_container_width=True):
        st.session_state["domain_input"] = ""
        st.session_state["run_query"] = False
        st.rerun()

# ✅ 两种匹配方式：完全匹配 / 前缀一致
mode = st.selectbox(
    "匹配方式",
    ["完全匹配", "前缀一致"],
    index=0,
    key="match_mode",
)

# ----------------------------
# 解析输入（仅在点击“开始查询”后）
# ----------------------------
if st.session_state["run_query"]:
    queries_all = parse_queries(st.session_state.get("domain_input", ""))
else:
    queries_all = []

# 输入上限提示（只允许出现这一条）
if len(queries_all) > MAX_INPUT:
    st.info(f"建议一次输入不超过 {MAX_INPUT} 个 domain")
    queries = queries_all[:MAX_INPUT]
else:
    queries = queries_all

# ----------------------------
# Filter
# ----------------------------
if df.empty:
    filtered = df.iloc[0:0].copy()
else:
    if not st.session_state["run_query"]:
        filtered = df.iloc[0:0].copy()
    else:
        if not queries:
            filtered = df.iloc[0:0].copy()
        else:
            mask = df["domain"].apply(lambda x: any(is_match(x, q, mode) for q in queries))
            filtered = df[mask].copy()

# ----------------------------
# Sort（固定自动升序）
# ----------------------------
if not filtered.empty:
    filtered["__k"] = filtered["domain"].str.lower()
    filtered = filtered.sort_values("__k", ascending=True).drop(columns=["__k"])

# ----------------------------
# Results
# ----------------------------
st.markdown("---")
st.subheader("查询结果")

if filtered.empty:
    st.write("未找到匹配的 Domain")
else:
    st.write(f"共 **{len(filtered):,}** 条匹配结果")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    csv_bytes = filtered["domain"].to_csv(index=False, header=False).encode("utf-8")
    st.download_button(
        label="⬇️ 下载匹配结果（CSV）",
        data=csv_bytes,
        file_name="matched_domains.csv",
        mime="text/csv",
    )
