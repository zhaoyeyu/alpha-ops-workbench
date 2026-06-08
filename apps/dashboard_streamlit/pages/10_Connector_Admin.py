from __future__ import annotations

import streamlit as st

from alphaops.data.adapters.admin import connector_admin_snapshot


TEXT = {
    "zh": {
        "language": "语言",
        "title": "连接器管理",
        "subtitle": "管理真实连接器健康检查、权限范围、凭证槽位状态和本地私有文件连接器；只显示环境变量是否配置，不显示密钥值。",
        "private": "Private CSV/Parquet path",
        "connectors": "Connector Health",
        "credentials": "Credential Slots",
        "policy": "Secret Policy",
        "error": "连接器管理无法加载",
    },
    "en": {
        "language": "Language",
        "title": "Connector Admin",
        "subtitle": "Manage real connector health checks, permission scopes, credential slot status, and local private file registration; only env presence is shown, never secret values.",
        "private": "Private CSV/Parquet path",
        "connectors": "Connector Health",
        "credentials": "Credential Slots",
        "policy": "Secret Policy",
        "error": "Connector Admin cannot load",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="connector_admin_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

private_path = st.text_input(text["private"], value="")
try:
    snapshot = connector_admin_snapshot(private_path or None)
    st.subheader(text["connectors"])
    st.dataframe(snapshot["connectors"], use_container_width=True, hide_index=True)
    st.subheader(text["credentials"])
    st.dataframe(snapshot["credential_slots"], use_container_width=True, hide_index=True)
    st.subheader(text["policy"])
    st.info(snapshot["secret_policy"])
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
