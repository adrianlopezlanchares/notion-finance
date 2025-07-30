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

notion = Client(auth=st.secrets["NOTION_API_KEY"])
database_id = st.secrets["NOTION_DATABASE_ID"]


def get_transactions() -> pd.DataFrame:
    """Retrieve transaction details from Notion database."""

    response = notion.databases.query(database_id=database_id, page_size=100)
    cursor = response["next_cursor"]
    response_results = response["results"]

    while response["has_more"]:
        response = notion.databases.query(
            database_id=database_id, page_size=100, start_cursor=cursor
        )
        cursor = response["next_cursor"]
        response_results += response["results"]

    rows = []

    for page in response_results:  # type: ignore
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


def get_current_money(
    transactions: pd.DataFrame,
) -> tuple[float, float, float, float]:
    """Calculate the current total money based on transactions.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction data.

    Returns:
        tuple[float, float, float, float]: Current total money, tarjeta, efectivo, and ahorros.
    """

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
    current_tarjeta -= current_ahorros

    return (
        current_money,
        current_tarjeta,
        current_efectivo,
        current_ahorros,
    )


def plot_total_money(transactions: pd.DataFrame, time_range: str) -> Figure:
    """Plot the total money over time.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction data.
        time_range (str): Time range for the plot (e.g., "Último mes", "Última semana").

    Returns:
        Figure: Matplotlib figure object.
    """

    fig, ax = plt.subplots()
    transactions = transactions.copy()
    transactions["amount_no_ahorros"] = transactions["amount"]
    transactions.loc[transactions["type"] == "Ahorros", "amount_no_ahorros"] = 0
    transactions["accumulated"] = transactions["amount_no_ahorros"].cumsum()
    transactions = transactions[transactions["amount_no_ahorros"] != 0]

    # Filtrar datos según el rango seleccionado
    transactions_filtered = transactions.copy()
    if time_range == "Último mes":
        start_date = datetime.datetime.now() - pd.DateOffset(months=1)
        transactions_filtered = transactions_filtered[
            transactions_filtered["date"] >= start_date
        ]
    elif time_range == "Última semana":
        start_date = datetime.datetime.now() - pd.DateOffset(weeks=1)
        transactions_filtered = transactions_filtered[
            transactions_filtered["date"] >= start_date
        ]

    ax.plot(
        transactions_filtered["date"],
        transactions_filtered["accumulated"],
        marker="o",
        markersize=1,
        linestyle="-",
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Dinero Total")
    fig.autofmt_xdate()

    return fig


def plot_ahorros(transactions: pd.DataFrame, time_range: str) -> Figure:
    """Plot the total money in Ahorros over time.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction data.
        time_range (str): Time range for the plot (e.g., "Último mes", "Última semana").

    Returns:
        Figure: Matplotlib figure object.
    """

    fig, ax = plt.subplots()
    transactions = transactions.copy()
    transactions["amount_ahorros"] = transactions["amount"]
    transactions.loc[transactions["type"] != "Ahorros", "amount_ahorros"] = 0
    transactions = transactions[transactions["amount_ahorros"] != 0]
    transactions["accumulated_ahorros"] = transactions["amount_ahorros"].cumsum()

    # Filtrar datos según el rango seleccionado
    transactions_filtered = transactions.copy()
    if time_range == "Último mes":
        start_date = datetime.datetime.now() - pd.DateOffset(months=1)
        transactions_filtered = transactions_filtered[
            transactions_filtered["date"] >= start_date
        ]
    elif time_range == "Última semana":
        start_date = datetime.datetime.now() - pd.DateOffset(weeks=1)
        transactions_filtered = transactions_filtered[
            transactions_filtered["date"] >= start_date
        ]

    ax.plot(
        transactions_filtered["date"],
        transactions_filtered["accumulated_ahorros"],
        marker="o",
        markersize=1,
        linestyle="-",
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Ahorros")
    fig.autofmt_xdate()

    return fig


def plot_category_pie(transactions: pd.DataFrame, transaction_type: str) -> Figure:
    """Plot a pie chart of transactions by category.

    Args:
        transactions (pd.DataFrame): The transactions data.
        transaction_type (str): The type of transactions to filter ('Expense' or 'Income').

    Returns:
        Figure: The matplotlib figure object.
    """

    total_expenses = abs(
        transactions[transactions["type"] == transaction_type]["amount"].sum()
    )

    # Add all transactions to have category in 'COMER' as one single transaction
    transactions["general_category"] = transactions["category"]
    transactions.loc[transactions["category"].isin(COMER), "general_category"] = "Comer"

    category_expenses = (
        transactions[transactions["type"] == transaction_type]
        .groupby("general_category")["amount"]
        .sum()
        .reset_index()
    )
    if transaction_type == "Income":
        category_expenses = category_expenses[category_expenses["amount"] > 0]
    else:
        category_expenses = category_expenses[category_expenses["amount"] < 0]
        category_expenses["amount"] = category_expenses["amount"].abs()
    category_expenses["general_category"] = (
        category_expenses["general_category"]
        + " ("
        + category_expenses["amount"].apply(lambda x: f"{x:.2f}").astype(str)
        + " €)"
    )

    cmap = plt.get_cmap("Pastel1")
    base_colors = cmap.colors  # type: ignore
    colors = [base_colors[i % len(base_colors)] for i in range(len(category_expenses))]

    fig, ax = plt.subplots()
    ax.pie(
        category_expenses["amount"],
        labels=category_expenses["general_category"],  # type: ignore
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


def plot_pie_expense_comer(transactions: pd.DataFrame, transaction_type: str) -> Figure:
    """Plot a pie chart of the last month's transactions by category for 'Comer'.

    Args:
        transactions (pd.DataFrame): The transactions data.
        transaction_type (str): The type of transactions to filter ('Expense' or 'Income').

    Returns:
        Figure: The matplotlib figure object.
    """
    recent = transactions[(transactions["category"].isin(COMER))]

    total_expenses = abs(recent[recent["type"] == transaction_type]["amount"].sum())

    category_expenses = (
        recent[recent["type"] == transaction_type]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
    )
    if transaction_type == "Income":
        category_expenses = category_expenses[category_expenses["amount"] > 0]
    else:
        category_expenses = category_expenses[category_expenses["amount"] < 0]
    category_expenses["amount"] = category_expenses["amount"].abs()
    category_expenses["category"] = (
        category_expenses["category"]
        + " ("
        + category_expenses["amount"].apply(lambda x: f"{x:.2f}").astype(str)
        + " €)"
    )

    cmap = plt.get_cmap("Pastel2")
    base_colors = cmap.colors  # type: ignore
    colors = [base_colors[i % len(base_colors)] for i in range(len(category_expenses))]

    fig, ax = plt.subplots()
    ax.pie(
        category_expenses["amount"],
        labels=category_expenses["category"],  # type: ignore
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


def dashboard(transactions: pd.DataFrame) -> None:
    """Display the dashboard with current money and graphs.

    Args:
        transactions (pd.DataFrame): The transactions data.
    """
    st.title("Dashboard")

    # Mostrar saldos actuales
    current_money, current_tarjeta, current_efectivo, current_ahorros = (
        get_current_money(transactions)
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
        index=1,
    )

    # Generar figuras con los datos filtrados
    fig_total = plot_total_money(transactions, time_range)
    fig_ahorros = plot_ahorros(transactions, time_range)

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

    expenses_or_income = st.selectbox(
        "Selecciona el tipo",
        options=["Expense", "Income"],
        index=0,
    )

    # Filtrar datos según el rango seleccionado
    df_filtered = transactions.copy()
    if time_range == "Último mes":
        start_date = datetime.datetime.now() - pd.DateOffset(months=1)
        df_filtered = df_filtered[df_filtered["date"] >= start_date]
    elif time_range == "Última semana":
        start_date = datetime.datetime.now() - pd.DateOffset(weeks=1)
        df_filtered = df_filtered[df_filtered["date"] >= start_date]

    if expenses_or_income == "Income":
        fig_pie = plot_category_pie(df_filtered, "Income")
        fig_comer = plot_pie_expense_comer(df_filtered, "Income")
    else:
        fig_pie = plot_category_pie(df_filtered, "Expense")
        fig_comer = plot_pie_expense_comer(df_filtered, "Expense")

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


def list_transactions(transactions: pd.DataFrame) -> None:
    """List all transactions in a paginated table format."""
    st.subheader("Lista")
    transactions_list = transactions.copy()

    transactions_list["date"] = transactions_list["date"].dt.strftime("%d-%m-%Y")
    transactions_list = transactions_list.iloc[::-1]  # Most recent first

    # Pagination config
    items_per_page = 20
    total_items = len(transactions_list)
    total_pages = (total_items - 1) // items_per_page + 1

    page = st.number_input(
        "Página", min_value=1, max_value=total_pages, value=1, step=1
    )

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page

    # Slice the DataFrame for the current page
    current_page_data = transactions_list.iloc[start_idx:end_idx]

    # Display each transaction
    for _, row in current_page_data.iterrows():
        color = "#76C869" if row["type"] == "Income" else "#FA8970"
        color = "#6CA9F9" if row["type"] == "Ahorros" else color
        image = "💳" if row["account"] == "Tarjeta" else "🤑"
        image = "📈" if row["type"] == "Ahorros" else image

        amount = row["amount"] if row["type"] == "Ahorros" else abs(row["amount"])

        st.markdown(
            f"""
            <div style="
                border: 2px solid {color};
                background-color: {color};
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 5px;
                font-family: monospace;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="width: 200px;">{row['date']}</div>
                    <div style="width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{row['description']}</div>
                    <div style="width: 150px;">{row['category']}</div>
                    <div style="width: 100px; text-align: right;">{amount} €</div>
                    <div style="width: 50px; text-align: right;">{image}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def deploy_streamlit() -> None:
    """Deploy the Streamlit app to visualize transactions data."""
    if st.button("Refresh"):
        st.rerun()

    df = get_transactions()

    tab1, tab2 = st.tabs(["Dashboard", "Transactions"])

    with tab1:
        dashboard(df)

    with tab2:
        list_transactions(df)


###################################################
deploy_streamlit()
