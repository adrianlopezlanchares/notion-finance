from notion_client import Client
import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import streamlit as st

import os
import sys
import subprocess


COMER = {"uber eats", "comida", "monchis", "desayuno", "restaurante"}


# If we’re not already running under Streamlit, re-invoke ourselves with `streamlit run`
if __name__ == "__main__" and os.getenv("STREAMLIT_RUN") != "1":
    # mark that we are relaunching to avoid infinite loops
    os.environ["STREAMLIT_RUN"] = "1"
    # build the command: streamlit run this_script.py [any args]
    cmd = ["streamlit", "run", sys.argv[0]] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))


notion = Client(auth=st.secrets["NOTION_API_KEY"])
database_id = st.secrets["NOTION_DATABASE_ID"]


def get_transactions() -> pd.DataFrame:
    """Retrieve transaction details from Notion database."""
    response = notion.databases.query(database_id=database_id)
    rows = []

    for page in response["results"]:
        props = page["properties"]
        description = ""
        title_items = props["Description"]["title"]
        if title_items:
            description = "".join([t["plain_text"] for t in title_items])

        category = (
            props["Category"]["select"]["name"]
            if props["Category"]["select"]
            else "None"
        )
        amount = float(props["Amount"]["number"])
        account = (
            props["Account"]["select"]["name"] if props["Account"]["select"] else "None"
        )
        type_ = props["Type"]["select"]["name"] if props["Type"]["select"] else "None"

        default_date = datetime.datetime(2025, 1, 1, 0, 0, 0).isoformat()
        date_str = (
            props["Date"]["created_time"]
            if props["Date"]["created_time"]
            else default_date
        )

        rows.append(
            {
                "description": description,
                "category": category,
                "amount": amount,
                "account": account,
                "type": type_,
                "date": date_str,
            }
        )

    transactions = pd.DataFrame(rows)
    transactions["date"] = pd.to_datetime(transactions["date"]).dt.tz_localize(None)
    transactions["amount"] = transactions["amount"].astype(float)
    transactions = transactions.sort_values("date")
    transactions.loc[transactions["type"] == "Expense", "amount"] *= -1

    return transactions


def get_current_money(transactions: pd.DataFrame) -> tuple[float, float, float, float]:
    """Calculate the current total money based on transactions."""
    transactions["amount_no_ahorros"] = transactions["amount"]
    transactions["tarjeta"] = transactions["amount"]
    transactions["efectivo"] = transactions["amount"]
    transactions["ahorros"] = transactions["amount"]

    transactions.loc[transactions["type"] == "Ahorros", "amount_no_ahorros"] = 0
    transactions.loc[transactions["account"] != "Tarjeta", "tarjeta"] = 0
    transactions.loc[transactions["account"] != "Efectivo", "efectivo"] = 0
    transactions.loc[transactions["account"] != "Ahorros", "ahorros"] = 0

    current_money = transactions["amount_no_ahorros"].sum()
    current_tarjeta = transactions["tarjeta"].sum()
    current_efectivo = transactions["efectivo"].sum()
    current_ahorros = transactions["ahorros"].sum()

    return current_money, current_tarjeta, current_efectivo, current_ahorros


def plot_total_money(transactions: pd.DataFrame) -> Figure:
    """Plot the total money over time."""
    fig, ax = plt.subplots()
    transactions = transactions.copy()
    transactions["amount_no_ahorros"] = transactions["amount"]
    transactions.loc[transactions["type"] == "Ahorros", "amount_no_ahorros"] = 0
    transactions["accumulated"] = transactions["amount_no_ahorros"].cumsum()

    ax.plot(
        transactions["date"], transactions["accumulated"], marker="o", linestyle="-"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Dinero Total")
    fig.autofmt_xdate()

    return fig


def plot_ahorros(transactions: pd.DataFrame) -> Figure:
    """Plot the total money in Ahorros over time."""
    fig, ax = plt.subplots()
    transactions = transactions.copy()
    transactions["amount_ahorros"] = transactions["amount"]
    transactions.loc[transactions["type"] != "Ahorros", "amount_ahorros"] = 0
    transactions = transactions[transactions["amount_ahorros"] != 0]
    transactions["accumulated_ahorros"] = transactions["amount_ahorros"].cumsum()

    ax.plot(
        transactions["date"],
        transactions["accumulated_ahorros"],
        marker="o",
        linestyle="-",
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Ahorros")
    fig.autofmt_xdate()

    return fig


def plot_last_months_category_expense_pie(transactions: pd.DataFrame) -> Figure:
    """Plot a pie chart of the last month's transactions by category."""
    last_month = datetime.datetime.now() - pd.DateOffset(months=1)
    recent = transactions[transactions["date"] >= last_month]

    total_expenses = abs(recent[recent["type"] == "Expense"]["amount"].sum())

    category_expenses = (
        recent[recent["type"] == "Expense"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
    )
    category_expenses = category_expenses[category_expenses["amount"] < 0]
    category_expenses["amount"] = category_expenses["amount"].abs()
    category_expenses["category"] = (
        category_expenses["category"]
        + " ("
        + category_expenses["amount"].astype(str)
        + " €)"
    )

    cmap = plt.get_cmap("Pastel1")
    base_colors = cmap.colors
    colors = [base_colors[i % len(base_colors)] for i in range(len(category_expenses))]

    fig, ax = plt.subplots()
    ax.pie(
        category_expenses["amount"],
        labels=category_expenses["category"],
        startangle=90,
        colors=colors,
    )
    ax.text(
        0,
        0,
        f"{total_expenses:.2f} €",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
    )
    ax.axis("equal")
    fig.tight_layout()

    return fig


def plot_pie_expense_comer(transactions: pd.DataFrame) -> Figure:
    """Plot a pie chart of the last month's transactions by category for 'Comer'."""
    last_month = datetime.datetime.now() - pd.DateOffset(months=1)
    recent = transactions[
        (transactions["date"] >= last_month) & (transactions["category"].isin(COMER))
    ]

    total_expenses = abs(recent[recent["type"] == "Expense"]["amount"].sum())

    category_expenses = (
        recent[recent["type"] == "Expense"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
    )
    category_expenses = category_expenses[category_expenses["amount"] < 0]
    category_expenses["amount"] = category_expenses["amount"].abs()
    category_expenses["category"] = (
        category_expenses["category"]
        + " ("
        + category_expenses["amount"].astype(str)
        + " €)"
    )

    cmap = plt.get_cmap("Pastel2")
    base_colors = cmap.colors
    colors = [base_colors[i % len(base_colors)] for i in range(len(category_expenses))]

    fig, ax = plt.subplots()
    ax.pie(
        category_expenses["amount"],
        labels=category_expenses["category"],
        startangle=90,
        colors=colors,
    )
    ax.text(
        0,
        0,
        f"{total_expenses:.2f} €",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
    )
    ax.axis("equal")
    fig.tight_layout()

    return fig


def deploy_streamlit() -> None:
    """Deploy the Streamlit app to visualize transactions data."""
    if st.button("Refresh"):
        st.rerun()

    st.title("Dashboard")
    df = get_transactions()

    # Mostrar saldos actuales
    current_money, current_tarjeta, current_efectivo, current_ahorros = (
        get_current_money(df)
    )
    st.markdown("### <strong>Dinero Total</strong>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="
            border: 2px solid #47CC32;
            background-color: #47CC32;
            padding: 12px;
            border-radius: 6px;
        ">
        <strong>{current_money:.2f} €</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### <strong>Tarjeta</strong>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="
                border: 2px solid #FD4017;
                background-color: #FD4017;
                padding: 12px;
                border-radius: 6px;
            ">
            <strong>{current_tarjeta:.2f} €</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown("### <strong>Efectivo</strong>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="
                border: 2px solid #47CC32;
                background-color: #47CC32;
                padding: 12px;
                border-radius: 6px;
            ">
           <strong>{current_efectivo:.2f} €</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown("### <strong>Ahorros</strong>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="
                border: 2px solid #17C5FD;
                background-color: #17C5FD;
                padding: 12px;
                border-radius: 6px;
            ">
            <strong>{current_ahorros:.2f} €</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.header("Graficos")

    # Dropdown para seleccionar rango de tiempo
    time_range = st.selectbox(
        "Selecciona el rango de tiempo",
        options=["Todo", "Último mes", "Última semana"],
        index=0,
    )

    # Filtrar datos según el rango seleccionado
    df_filtered = df.copy()
    if time_range == "Último mes":
        start_date = datetime.datetime.now() - pd.DateOffset(months=1)
        df_filtered = df_filtered[df_filtered["date"] >= start_date]
    elif time_range == "Última semana":
        start_date = datetime.datetime.now() - pd.DateOffset(weeks=1)
        df_filtered = df_filtered[df_filtered["date"] >= start_date]

    # Generar figuras con los datos filtrados
    fig_total = plot_total_money(df_filtered)
    fig_ahorros = plot_ahorros(df_filtered)
    fig_pie = plot_last_months_category_expense_pie(df_filtered)
    fig_comer = plot_pie_expense_comer(df_filtered)

    # Mostrar gráficos
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Dinero Total")
        st.pyplot(fig_total)
    with col2:
        st.subheader("Ahorros")
        st.pyplot(fig_ahorros)

    if "selected_graph" not in st.session_state:
        st.session_state.selected_graph = "fig_pie"

    def show_graph(name):
        st.session_state.selected_graph = name

    st.subheader("Seleccionar Gráfico")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("Categorias", on_click=show_graph, args=("fig_pie",))
    with col2:
        st.button("Comer", on_click=show_graph, args=("fig_comer",))
    with col3:
        st.button("Ahorros", on_click=show_graph, args=("C",))

    graph_map = {
        "fig_pie": fig_pie,
        "fig_comer": fig_comer,
        "C": fig_ahorros,
    }

    st.pyplot(graph_map[st.session_state.selected_graph])


###############################################
deploy_streamlit()
