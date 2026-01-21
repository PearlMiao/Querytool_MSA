
import re
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# ----------------------------
# Page config
# ----------------------------
st.set_page_config(
    page_title="MSA Domain Query Tool",
    page_icon="🔎",
    layout="wide",
)

DATA_FILE = "cleaned_text.csv"
MAX_INPUT = 1000  # 只允许提示这一条：建议一次输入不超过 1000 个 domain


# ----------------------------
# Helpers
# ----------------------------
def resolve_data_file(preferred_name: str) -> str:
    """
    兜底处理文件名大小写问题：
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
        try:
            df = pd.read_csv(p, header=None, names=["domain"], dtype=str, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame(columns=["domain"])

    df["domain"] = df["domain"].fillna("").astype(str).str.strip()
    df = df[df["domain"] != ""]
    df = df.drop_duplicates().reset_index(drop=True)
    return df


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


def is_match(text: str, q: str, mode: str) -> bool:
    if not q:
        return True
    t = normalize(text)
    qn = normalize(q)
    if mode == "包含 (contains)":
        return qn in t
    if mode == "完全匹配 (exact)":
        return t == qn
    return qn in t


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

# 用 form 来避免 text_area 出现 “Ctrl+Enter 查询/应用” 的提示，
# 并且只在点“开始查询”时才执行查询逻辑
if "domain_input" not in st.session_state:
    st.session_state["domain_input"] = ""
if "run_query" not in st.session_state:
    st.session_state["run_query"] = False

col_inp, col_btn = st.columns([6, 1], gap="small")

with col_inp:
    with st.form("query_form", clear_on_submit=False):
        domain_raw = st.text_area(
            "输入 domain（支持换行批量，每行一个）",
            placeholder="例如：\nhttps://www.example.com/path?a=1\nabc.com\nshop.cn",
            height=130,
            value=st.session_state["domain_input"],
        )
        # 表单内放一个隐藏占位，按钮我们放到右侧列里更符合你的UI目标
        submitted = st.form_submit_button("hidden_submit", disabled=True)

with col_btn:
    st.write("")
    # 开始查询
    if st.button("🔍 开始查询", use_container_width=True):
        st.session_state["domain_input"] = domain_raw
        st.session_state["run_query"] = True
        st.rerun()

    # 清空输入
    if st.button("🧹 清空输入", use_container_width=True):
        st.session_state["domain_input"] = ""
        st.session_state["run_query"] = False
        st.rerun()

# 匹配方式仍保留
mode = st.selectbox(
    "匹配方式",
    ["包含 (contains)", "完全匹配 (exact)"],
    index=0,
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
# Filter（不对用户显示“CSV缺失/读取失败”等技术提示）
# ----------------------------
if df.empty:
    filtered = df
else:
    # 如果没点开始查询，就不要默认展示全量
    if not st.session_state["run_query"]:
        filtered = df.iloc[0:0].copy()
    else:
        if not queries:
            filtered = df.copy()
        else:
            mask = df["domain"].apply(lambda x: any(is_match(x, q, mode) for q in queries))
            filtered = df[mask].copy()

# ----------------------------
# Sort（固定自动升序；已删除排序选项）
# ----------------------------
if not filtered.empty:
    filtered["__k"] = filtered["domain"].str.lower()
    filtered = filtered.sort_values("__k", ascending=True).drop(columns=["__k"])

# ----------------------------
# Results
# ----------------------------
st.markdown("---")
st.subheader("查询结果")

# 只允许出现“未找到匹配的 Domain”
if filtered.empty:
    st.write("未找到匹配的 Domain")
else:
    st.write(f"共 **{len(filtered):,}** 条匹配结果")

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
    )

    # Download: one per line, no header
    csv_bytes = filtered["domain"].to_csv(index=False, header=False).encode("utf-8")
    st.download_button(
        label="⬇️ 下载匹配结果（CSV）",
        data=csv_bytes,
        file_name="matched_domains.csv",
        mime="text/csv",
    )

# ----------------------------
# Copy all（不提示失败，只提供功能 + 文本框兜底）
# ----------------------------
st.markdown("### 📋 一键复制全部结果")

all_text = "\n".join(filtered["domain"].tolist()) if not filtered.empty else ""

st.text_area(
    "结果文本（每行一个 domain）",
    value=all_text,
    height=200,
)

components.html(
    f"""
    <div style="display:flex; gap:10px; align-items:center; margin-top:6px;">
      <button id="copyBtn"
              style="padding:8px 12px; border-radius:8px; border:1px solid #ddd; cursor:pointer;">
        📋 一键复制全部
      </button>
      <span id="copyMsg" style="font-size:12px; color:#555;"></span>
    </div>
    <script>
      const text = {json.dumps(all_text)};
      const btn = document.getElementById('copyBtn');
      const msg = document.getElementById('copyMsg');

      btn.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(text);
          msg.textContent = "✅ 已复制";
          setTimeout(() => {{ msg.textContent = ""; }}, 1200);
        }} catch (e) {{
          msg.textContent = "";
        }}
      }});
    </script>
    """,
    height=60,
)
