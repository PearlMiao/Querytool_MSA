
import re
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================
# Page config
# =========================
st.set_page_config(
    page_title="MSA CBA Domain Query Tool",
    page_icon="🔎",
    layout="wide",
)

# 隐藏 “Press Ctrl + Enter...” 这类输入框提示（可选）
st.markdown(
    """
    <style>
      div[data-testid="InputInstructions"] {display:none !important;}
      div[data-testid="stTextArea"] small {display:none !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# Constants
# =========================
DATA_FILE = "cleaned_text.csv"
MAX_INPUT = 1000  # 单次输入不超过1000个

COL_DB = "纯域名"     # 数据库列名（中文）
COL_IN = "根域名"     # 输入列名（中文）
COL_RES = "匹配结果"  # 结果列名（中文）

# =========================
# Helpers
# =========================
def resolve_data_file(preferred_name: str) -> str:
    """处理文件名大小写问题，适配 Linux / Streamlit Cloud。"""
    p = Path(preferred_name)
    if p.exists():
        return preferred_name

    if preferred_name.lower().endswith(".csv"):
        base = preferred_name[:-4]
        candidates = [
            base + ".csv",
            base + ".CSV",
            base + ".Csv",
            base + ".cSv",
            base + ".csV",
        ]
        for name in candidates:
            if Path(name).exists():
                return name

    return preferred_name


def normalize(s: str) -> str:
    """统一：去多余空白 + 小写"""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@st.cache_data
def load_data(csv_name: str) -> pd.DataFrame:
    """
    读取 CSV（单列域名库） -> 中文列名 COL_DB
    注意：按你的要求，这里不做“清洗”，只做 strip()、去空、去重。
    """
    csv_name = resolve_data_file(csv_name)
    p = Path(csv_name)
    if not p.exists():
        return pd.DataFrame(columns=[COL_DB])

    # 尝试多种编码读取
    df = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            df = pd.read_csv(csv_name, encoding=enc, header=None)
            break
        except Exception:
            df = None

    if df is None or df.empty:
        return pd.DataFrame(columns=[COL_DB])

    # SOP 里导出的 cleaned_text.csv 通常是无表头单列，这里取第一列即可。[1](https://learn.microsoft.com/zh-cn/deployedge/microsoft-edge-browser-policies/browsersignin)
    s = df.iloc[:, 0]

    df2 = pd.DataFrame({COL_DB: s.fillna("").astype(str).str.strip()})
    df2 = df2[df2[COL_DB] != ""].drop_duplicates().reset_index(drop=True)
    return df2


def parse_queries(raw: str) -> list[str]:
    """
    多输入：每行一个，或逗号/空格分隔
    不做清洗：只 strip()，并去重保序
    """
    if not raw:
        return []

    items: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[,\s]+", line)
        for p in parts:
            p = p.strip()
            if p:
                items.append(p)

    # 去重保序
    seen = set()
    uniq: list[str] = []
    for x in items:
        k = normalize(x)
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def build_result_table(df_db: pd.DataFrame, raw_input: str) -> pd.DataFrame:
    """
    仅精确匹配（已删除模糊匹配）：
      根域名：用户输入（strip + 去重保序后）
      匹配结果：域名已使用 / 域名未使用
    """
    queries_all = parse_queries(raw_input)

    if len(queries_all) > MAX_INPUT:
        st.info(f"输入不超过 {MAX_INPUT} 个域名，本次仅取前 {MAX_INPUT} 个。")
        queries_all = queries_all[:MAX_INPUT]

    if not queries_all:
        return pd.DataFrame(columns=[COL_IN, COL_RES])

    # 数据库为空：全部未使用
    if df_db.empty:
        return pd.DataFrame({COL_IN: queries_all, COL_RES: ["域名未使用"] * len(queries_all)})

    db_series = df_db[COL_DB].fillna("").astype(str)
    db_norm_set = set(db_series.map(normalize).tolist())

    results = []
    for q in queries_all:
        qn = normalize(q)
        ok = qn in db_norm_set
        results.append({COL_IN: q, COL_RES: "域名已使用" if ok else "域名未使用"})

    return pd.DataFrame(results)


# =========================
# UI
# =========================
st.title("MSA CBA Domain Query Tool")
st.caption("数据源：2025/07 至 2026/01 代理消耗域名库（cleaned_text.csv）")  # 数据来源描述来自你们现有工具背景/文档[1](https://learn.microsoft.com/zh-cn/deployedge/microsoft-edge-browser-policies/browsersignin)

df_db = load_data(DATA_FILE)

st.subheader("查询")

if "last_result" not in st.session_state:
    st.session_state["last_result"] = pd.DataFrame(columns=[COL_IN, COL_RES])

col_inp, col_btn = st.columns([6, 1], gap="small")

with col_inp:
    raw_input = st.text_area(
        "输入根域名批量查询（每行一个，或逗号/空格分隔）",
        placeholder="abc\nshop",  # ✅ 灰色提示只给 abc、shop
        height=130,
        key="domain_input",
    )

with col_btn:
    st.write("")
    st.write("")
    clicked = st.button("开始查询", use_container_width=True)

if clicked:
    st.session_state["last_result"] = build_result_table(df_db, raw_input)

st.markdown("---")
st.subheader("查询结果")

result_df = st.session_state["last_result"]

if result_df.empty:
    st.write("暂无结果：请输入域名并点击“开始查询”。")
else:
    # 筛选：全部 / 已使用 / 未使用
    col_f1, col_f2 = st.columns([2, 4], gap="small")
    with col_f1:
        filter_option = st.selectbox(
            "筛选结果",
            ["全部", "域名已使用", "域名未使用"],
            index=0,
            key="result_filter",
        )
    with col_f2:
        keyword = st.text_input(
            "关键词过滤（可选）",
            value="",
            placeholder="输入片段，例如：abc / shop",
            key="result_keyword",
        )

    view_df = result_df.copy()

    if filter_option != "全部":
        view_df = view_df[view_df[COL_RES] == filter_option].copy()

    if keyword.strip():
        k = normalize(keyword)
        mask = (
            view_df[COL_IN].fillna("").astype(str).map(normalize).str.contains(k, regex=False)
            | view_df[COL_RES].fillna("").astype(str).map(normalize).str.contains(k, regex=False)
        )
        view_df = view_df[mask].copy()

    st.write(f"显示 {len(view_df)} 条（原始结果 {len(result_df)} 条）")
    st.dataframe(view_df, use_container_width=True, hide_index=True)

    # 下载筛选后的结果（中文表头）
    csv_bytes = view_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="下载结果（CSV）",
        data=csv_bytes,
        file_name="域名查询结果.csv",
        mime="text/csv",
    )
