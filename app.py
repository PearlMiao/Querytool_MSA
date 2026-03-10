
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
    layout="wide"
)

# 隐藏 text_area 输入框下方的提示（如 Press Ctrl+Enter...）
st.markdown(
    """
    <style>
      div[data-testid="stTextArea"] small {display:none !important;}
      div[data-testid="InputInstructions"] {display:none !important;}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# Constants
# =========================
DATA_FILE = "cleaned_text.csv"
MAX_INPUT = 1000  # 建议一次输入不超过 1000 个 domain

# =========================
# Helpers
# =========================
def resolve_data_file(preferred_name: str) -> str:
    """
    处理文件名大小写问题，适配 Linux / Streamlit Cloud。
    优先用 preferred_name 同名；否则尝试 CSV/.csv 等大小写变体。
    """
    p = Path(preferred_name)
    if p.exists():
        return preferred_name

    # 如果已经是 .csv 结尾，尝试各种大小写变体
    if preferred_name.lower().endswith(".csv"):
        base = preferred_name[:-4]
        candidates = [
            base + ".csv",
            base + ".CSV",
            base + ".Csv",
            base + ".cSv",
            base + ".csV",
            base + ".cSV",
            base + ".CsV",
            base + ".CSv",
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


def clean_domain_token(token: str) -> str:
    """
    输入清洗：尽量抽取“纯域名”
    - 去掉 http/https
    - 去掉路径、参数
    - 去掉前缀 www.
    """
    if not token:
        return ""
    t = token.strip()

    # 去掉 http(s)://
    t = re.sub(r"^\s*https?://", "", t, flags=re.IGNORECASE)

    # 只保留域名部分（遇到 / ? # 断开）
    t = re.split(r"[/?#]", t, maxsplit=1)[0].strip()

    # 去掉 www.
    t = re.sub(r"^www\.", "", t, flags=re.IGNORECASE)

    return t.strip()


@st.cache_data(show_spinner=False)
def load_data(csv_name: str) -> pd.DataFrame:
    """
    读取单列 domain 的 CSV
    约定 CSV 至少包含一列：domain
    """
    csv_name = resolve_data_file(csv_name)
    p = Path(csv_name)
    if not p.exists():
        return pd.DataFrame(columns=["domain"])

    # 兼容 utf-8 / utf-8-sig
    try:
        df = pd.read_csv(csv_name, dtype={"domain": str}, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(csv_name, dtype={"domain": str}, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame(columns=["domain"])
    except Exception:
        return pd.DataFrame(columns=["domain"])

    if "domain" not in df.columns:
        # 如果列名不是 domain，尽量取第一列
        if len(df.columns) >= 1:
            df = df.rename(columns={df.columns[0]: "domain"})
        else:
            return pd.DataFrame(columns=["domain"])

    # 标准化数据库 domain：去空、去重、清洗成纯域名
    df["domain"] = (
        df["domain"]
        .fillna("")
        .astype(str)
        .str.strip()
        .apply(clean_domain_token)
    )

    df = df[df["domain"] != ""].drop_duplicates().reset_index(drop=True)
    return df


def is_match(db_domain: str, q: str, mode: str) -> bool:
    """
    匹配：精确 / 模糊
    - 精确：normalize(db_domain) == normalize(q)
    - 模糊：normalize(q) 是否为 normalize(db_domain) 的子串（或反向也可）
      这里采用：db_domain 包含 q（更符合“查 q 是否存在于库域名”）
    """
    d = normalize(db_domain)
    qn = normalize(q)
    if not d or not qn:
        return False

    if mode == "精确匹配":
        return d == qn
    else:
        return qn in d


def parse_queries(raw: str) -> list[str]:
    """
    多 domain 输入：
    - 每行一个
    - 或逗号分隔
    自动清洗：去 http(s)、www、路径参数，仅保留域名
    去重（保持顺序）
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
            p = clean_domain_token(p)
            if p:
                items.append(p)

    # 去重保持顺序
    seen = set()
    uniq: list[str] = []
    for x in items:
        k = normalize(x)
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def build_result_table(df: pd.DataFrame, raw_input: str, mode: str) -> pd.DataFrame:
    """
    返回两列中文结果表：
    - 根域名：输入域名（清洗后）
    - 匹配结果：域名已使用 / 域名未使用
    """
    queries_all = parse_queries(raw_input)

    if len(queries_all) > MAX_INPUT:
        st.info(f"输入不超过 {MAX_INPUT} 个 domain，本次仅取前 {MAX_INPUT} 个。")
        queries_all = queries_all[:MAX_INPUT]

    if not queries_all:
        return pd.DataFrame(columns=["根域名", "匹配结果"])

    # 数据库为空：全部未使用
    if df is None or df.empty:
        return pd.DataFrame(
            {"根域名": queries_all, "匹配结果": ["域名未使用"] * len(queries_all)}
        )

    # 为了性能：构造 normalize 的集合（精确匹配用）
    norm_set = set(df["domain"].fillna("").astype(str).map(normalize).tolist())

    # 模糊匹配需要 contains：预先准备一列 normalize
    db_norm_series = df["domain"].fillna("").astype(str).map(normalize)

    results = []
    for q in queries_all:
        qn = normalize(q)
        if mode == "精确匹配":
            ok = (qn in norm_set)
        else:
            # 模糊：数据库任意 domain 包含 q
            ok = db_norm_series.str.contains(qn, regex=False).any()

        results.append({"根域名": q, "匹配结果": ("域名已使用" if ok else "域名未使用")})

    return pd.DataFrame(results)


# =========================
# UI
# =========================
st.title("MSA CBA Domain Query Tool")
st.caption("数据自 2025/07 至 2026/01（代理消耗根域名）")

df = load_data(DATA_FILE)

st.subheader("查询")

# session state：保存上次结果
if "last_result" not in st.session_state:
    st.session_state["last_result"] = pd.DataFrame(columns=["根域名", "匹配结果"])

# 输入框 + 按钮同行
col_inp, col_btn = st.columns([6, 1], gap="small")

with col_inp:
    raw_input = st.text_area(
        "输入根域名批量查询（每行一个，或逗号/空格分隔）",
        placeholder="abc.com\nshop.example.com\nhttps://www.test.com/path?a=1",
        height=130,
        key="domain_input"
    )

with col_btn:
    st.write("")
    clicked_query = st.button("开始查询", use_container_width=True)

# 匹配方式
mode = st.selectbox(
    "匹配方式",
    options=["精确匹配", "模糊匹配"],
    index=0,
    key="match_mode"
)

# 点击开始查询 -> 计算
if clicked_query:
    st.session_state["last_result"] = build_result_table(
        df=df,
        raw_input=st.session_state.get("domain_input", ""),
        mode=mode
    )

# =========================
# Results
# =========================
st.markdown("---")
st.subheader("查询结果")

result_df = st.session_state["last_result"]

if result_df.empty:
    st.write("未找到匹配结果（请先输入域名并点击开始查询）。")
else:
    # 筛选：全部/已使用/未使用
    col_f1, col_f2 = st.columns([2, 4], gap="small")
    with col_f1:
        filter_option = st.selectbox(
            "筛选结果",
            options=["全部", "域名已使用", "域名未使用"],
            index=0,
            key="result_filter"
        )
    with col_f2:
        keyword = st.text_input(
            "关键字过滤（可选）",
            value="",
            placeholder="输入 domain 片段，如 shop 或 .com",
            key="result_keyword"
        )

    view_df = result_df.copy()

    if filter_option != "全部":
        view_df = view_df[view_df["匹配结果"] == filter_option].copy()

    if keyword.strip():
        k = normalize(keyword)
        # 同时对“根域名”和“匹配结果”做 contains 过滤
        mask = (
            view_df["根域名"].fillna("").astype(str).map(normalize).str.contains(k, regex=False)
            | view_df["匹配结果"].fillna("").astype(str).map(normalize).str.contains(k, regex=False)
        )
        view_df = view_df[mask].copy()

    st.write(f"当前显示：{len(view_df)} 条（原始结果：{len(result_df)} 条）")
    st.dataframe(view_df, use_container_width=True, hide_index=True)

    # 下载：导出当前筛选后的结果（两列中文表头）
    csv_bytes = view_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="下载结果（CSV）",
        data=csv_bytes,
        file_name="domain_check_results.csv",
        mime="text/csv"
    )
