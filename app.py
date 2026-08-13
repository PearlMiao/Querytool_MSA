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

# 隐藏“Press Ctrl + Enter...”这类输入框提示（可选）
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

COL_DB = "纯域名"       # 数据库列名
COL_IN = "根域名"       # 输入列名
COL_RES = "匹配结果"    # 结果列名
COL_MATCH = "匹配域名"  # 匹配到的实际域名

# =========================
# Helpers
# =========================
def resolve_data_file(preferred_name: str) -> str:
    """处理文件名大小写问题，适配 Linux / Streamlit Cloud"""
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
    """
    统一格式：
    1. 去首尾空格
    2. 小写
    3. 去掉 http / https
    4. 去掉开头 www.
    5. 去掉 URL 后面的路径、参数
    6. 去掉末尾 /
    """

    if s is None:
        return ""

    s = str(s).strip().lower()

    # 去掉协议
    s = re.sub(r"^https?://", "", s)

    # 去掉路径、参数、锚点
    s = re.split(r"[/?#]", s)[0]

    # 去掉开头 www.
    s = re.sub(r"^www\.", "", s)

    # 压缩空白
    s = re.sub(r"\s+", " ", s).strip()

    # 去掉末尾点或斜杠
    s = s.strip("./")

    return s


def get_domain_keyword(domain: str) -> str:
    """
    提取主域名关键词，用于模糊匹配

    示例：
    trip.com -> trip
    www.trip.com -> trip
    shop.trip.com -> trip
    notta.ai -> notta
    laptop-fans.eu -> laptop-fans

    注意：
    当前逻辑适合常见单层后缀，如 .com, .ai, .eu, .cn
    如果未来需要精确支持 .co.uk / .com.cn 这类复杂后缀，可以再升级 tldextract
    """

    domain = normalize(domain)

    if not domain:
        return ""

    parts = domain.split(".")

    if len(parts) >= 2:
        return parts[-2]

    return domain


def format_match_list(matches: list[str]) -> str:
    """
    多个匹配域名合并展示
    """
    if not matches:
        return ""

    # 去重保序
    seen = set()
    uniq = []
    for x in matches:
        x_norm = normalize(x)
        if x_norm and x_norm not in seen:
            seen.add(x_norm)
            uniq.append(x_norm)

    return "\n".join(uniq)


@st.cache_data
def load_data(csv_name: str) -> pd.DataFrame:
    """
    读取 CSV（单列域名库），转成中文列名 COL_DB
    不做强清洗，仅做基础 strip + 去重

    cleaned_text.csv 通常为无表头单列文件
    """
    csv_name = resolve_data_file(csv_name)
    p = Path(csv_name)

    if not p.exists():
        return pd.DataFrame(columns=[COL_DB])

    df = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            df = pd.read_csv(csv_name, encoding=enc, header=None)
            break
        except Exception:
            df = None

    if df is None or df.empty:
        return pd.DataFrame(columns=[COL_DB])

    # 无表头单列：取第一列
    s = df.iloc[:, 0]

    df2 = pd.DataFrame({
        COL_DB: s.fillna("").astype(str).map(normalize)
    })

    df2 = (
        df2[df2[COL_DB] != ""]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    return df2


def parse_queries(raw: str) -> list[str]:
    """
    输入支持：
    1. 每行一个
    2. 逗号分隔
    3. 空格分隔

    不做业务清洗，仅做基础拆分 + 去重保序
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
        if k and k not in seen:
            seen.add(k)
            uniq.append(x)

    return uniq


def build_result_table(df_db: pd.DataFrame, raw_input: str) -> pd.DataFrame:
    """
    输出列：
    1. 根域名
    2. 匹配结果
    3. 匹配域名

    匹配逻辑：
    1. 精确匹配
       输入 trip.com，库里有 trip.com

    2. 模糊匹配
       输入 trip，库里有 trip.com
       输入 www.trip.com，库里有 trip.com
       输入 shop.trip.com，库里有 trip.com

    3. 多个模糊匹配
       输入 trip，库里有 trip.com / trip.cn / trip.net
       会全部展示
    """

    queries_all = parse_queries(raw_input)

    if len(queries_all) > MAX_INPUT:
        st.info(f"输入不超过 {MAX_INPUT} 个域名，本次仅取前 {MAX_INPUT} 个。")
        queries_all = queries_all[:MAX_INPUT]

    if not queries_all:
        return pd.DataFrame(columns=[COL_IN, COL_RES, COL_MATCH])

    if df_db.empty:
        return pd.DataFrame({
            COL_IN: queries_all,
            COL_RES: ["域名未使用"] * len(queries_all),
            COL_MATCH: [""] * len(queries_all),
        })

    db_series = (
        df_db[COL_DB]
        .fillna("")
        .astype(str)
        .map(normalize)
    )

    db_series = db_series[db_series != ""].drop_duplicates()

    # =====================
    # 1. 精确匹配库
    # =====================
    db_norm_set = set(db_series.tolist())

    # =====================
    # 2. 模糊匹配库
    # keyword -> 多个域名
    #
    # trip -> [trip.com, trip.cn]
    # notta -> [notta.ai]
    # =====================
    keyword_map: dict[str, list[str]] = {}

    for d in db_series:
        keyword = get_domain_keyword(d)

        if not keyword:
            continue

        if keyword not in keyword_map:
            keyword_map[keyword] = []

        if d not in keyword_map[keyword]:
            keyword_map[keyword].append(d)

    results = []

    for q in queries_all:
        q_norm = normalize(q)

        # =====================
        # 1. 精确匹配
        # =====================
        if q_norm in db_norm_set:
            results.append({
                COL_IN: q,
                COL_RES: "域名已使用（精确匹配）",
                COL_MATCH: q_norm,
            })
            continue

        # =====================
        # 2. 模糊匹配
        # =====================
        keyword = get_domain_keyword(q_norm)

        if keyword in keyword_map:
            matches = keyword_map[keyword]
            match_text = format_match_list(matches)

            if len(matches) == 1:
                result_text = "域名疑似已使用（模糊匹配）"
            else:
                result_text = f"域名疑似已使用（模糊匹配，匹配到 {len(matches)} 个）"

            results.append({
                COL_IN: q,
                COL_RES: result_text,
                COL_MATCH: match_text,
            })
            continue

        # =====================
        # 3. 未匹配
        # =====================
        results.append({
            COL_IN: q,
            COL_RES: "域名未使用",
            COL_MATCH: "",
        })

    return pd.DataFrame(results)


# =========================
# UI
# =========================
st.title("MSA CBA Domain Query Tool")
st.caption("数据源：26年2月-26年7月 CBA已使用根域名")

df_db = load_data(DATA_FILE)

st.subheader("查询")

if "last_result" not in st.session_state:
    st.session_state["last_result"] = pd.DataFrame(
        columns=[COL_IN, COL_RES, COL_MATCH]
    )

col_inp, col_btn = st.columns([6, 1], gap="small")

with col_inp:
    raw_input = st.text_area(
        "输入根域名批量查询（每行一个，或逗号/空格分隔）",
        placeholder="abc.com\nshop.cn",
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
    filter_option = st.selectbox(
        "筛选结果",
        [
            "全部",
            "域名已使用（精确匹配）",
            "域名疑似已使用（模糊匹配）",
            "域名未使用",
        ],
        index=0,
        key="result_filter",
    )

    view_df = result_df.copy()

    if filter_option == "域名已使用（精确匹配）":
        view_df = view_df[
            view_df[COL_RES] == "域名已使用（精确匹配）"
        ].copy()

    elif filter_option == "域名疑似已使用（模糊匹配）":
        view_df = view_df[
            view_df[COL_RES].str.contains("模糊匹配", na=False)
        ].copy()

    elif filter_option == "域名未使用":
        view_df = view_df[
            view_df[COL_RES] == "域名未使用"
        ].copy()

    st.write(f"显示 {len(view_df)} 条（原始结果 {len(result_df)} 条）")

    st.dataframe(
        view_df,
        use_container_width=True,
        hide_index=True,
    )

    # 下载筛选后的结果（中文表头）
    csv_bytes = (
        view_df
        .to_csv(index=False, encoding="utf-8-sig")
        .encode("utf-8-sig")
    )

    st.download_button(
        label="下载结果（CSV）",
        data=csv_bytes,
        file_name="域名查询结果.csv",
        mime="text/csv",
    )
