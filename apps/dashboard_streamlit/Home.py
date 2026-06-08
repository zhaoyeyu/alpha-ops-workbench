from __future__ import annotations

import streamlit as st

from apps.dashboard_streamlit.ui.home_view import render_home


st.set_page_config(page_title="AlphaOps Workbench", layout="wide")

pages = [
    st.Page(render_home, title="首页", url_path="home"),
    st.Page("pages/01_Data_Hub.py", title="数据中心", url_path="data-hub"),
    st.Page("pages/02_Data_Quality.py", title="数据质量", url_path="data-quality"),
    st.Page("pages/03_Synthetic_Index_Lab.py", title="合成指数实验室", url_path="synthetic-index-lab"),
    st.Page("pages/04_Alpha_Factory.py", title="Alpha 工厂", url_path="alpha-factory"),
    st.Page("pages/05_Backtest_Lab.py", title="回测实验室", url_path="backtest-lab"),
    st.Page("pages/06_Alpha_Registry.py", title="Alpha 注册表", url_path="alpha-registry"),
    st.Page("pages/07_Risk_Monitor.py", title="风险监控", url_path="risk-monitor"),
    st.Page("pages/08_Agent_Console.py", title="Agent 控制台", url_path="agent-console"),
    st.Page("pages/09_Report_Center.py", title="报告中心", url_path="report-center"),
    st.Page("pages/10_Connector_Admin.py", title="连接器管理", url_path="connector-admin"),
    st.Page("pages/11_Evaluation_Dashboard.py", title="评估仪表盘", url_path="evaluation-dashboard"),
]

navigation = st.navigation(pages, position="sidebar")
navigation.run()
