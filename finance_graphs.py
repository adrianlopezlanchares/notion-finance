from notion_client import Client
import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import streamlit as st

import os
import sys
import subprocess

# If we’re not already running under Streamlit, re-invoke ourselves with `streamlit run`
if __name__ == "__main__" and os.getenv("STREAMLIT_RUN") != "1":
    # mark that we are relaunching to avoid infinite loops
    os.environ["STREAMLIT_RUN"] = "1"
    # build the command: streamlit run this_script.py [any args]
    cmd = ["streamlit", "run", sys.argv[0]] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))


notion = Client(auth="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")
database_id = "20e8d199e75580f6bb77d022c88e6a41"


@st.cache_data(ttl=600)
def get_transactions() -> pd.DataFrame:
    """Retrieve transaction details from Notion database.

    Returns:
        pd.DataFrame: A DataFrame containing the transaction details.
    """

    response = notion.databases.query(database_id=database_id)

    rows = []

    for page in response["results"]:  # type: ignore

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

        row = {
            "description": description,
            "category": category,
            "amount": amount,
            "account": account,
            "type": type_,
            "date": date_str,
        }

        rows.append(row)

    transactions = pd.DataFrame(rows)

    # Process transactions
    transactions["date"] = pd.to_datetime(transactions["date"])
    transactions["date"] = transactions["date"].dt.tz_localize(None)
    transactions["amount"] = transactions["amount"].astype(float)

    # Sort by date
    transactions = transactions.sort_values("date")

    # Turn amount negative if type is "Expense"
    transactions.loc[transactions["type"] == "Expense", "amount"] *= -1

    return transactions


def get_current_money(transactions: pd.DataFrame) -> tuple[float, float, float, float]:
    """Calculate the current total money based on transactions.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction details.

    Returns:
        tuple: A tuple containing current money, current tarjeta, current efectivo, and current ahorros.
    """

    transactions["amount_no_ahorros"] = transactions["amount"].copy()
    transactions["tarjeta"] = transactions["amount"].copy()
    transactions["efectivo"] = transactions["amount"].copy()
    transactions["ahorros"] = transactions["amount"].copy()

    # Remove "Ahorros" category from amount
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
    """Plot the total money over time.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction details.

    Returns:
        plt.Figure: A matplotlib figure object containing the plot.
    """

    # Create figure & axes
    fig, ax = plt.subplots()

    transactions["amount_no_ahorros"] = transactions["amount"].copy()
    # Remove "Ahorros" category from amount
    transactions.loc[transactions["type"] == "Ahorros", "amount_no_ahorros"] = 0

    transactions["accumulated"] = transactions["amount_no_ahorros"].cumsum()

    # Plot each expense
    ax.plot(
        transactions["date"], transactions["accumulated"], marker="o", linestyle="-"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Dinero Total")
    fig.autofmt_xdate()  # rotate & align date labels

    return fig


def plot_ahorros(transactions: pd.DataFrame) -> Figure:
    """Plot the total money in Ahorros over time.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction details.

    Returns:
        plt.Figure: A matplotlib figure object containing the plot.
    """

    # Create figure & axes
    fig, ax = plt.subplots()

    transactions["amount_ahorros"] = transactions["amount"].copy()
    # Remove "Ahorros" category from amount
    transactions.loc[transactions["type"] != "Ahorros", "amount_ahorros"] = 0

    # Remove all entries where amout_ahorros is 0
    transactions = transactions[transactions["amount_ahorros"] != 0]

    transactions["accumulated_ahorros"] = transactions["amount_ahorros"].cumsum()

    # Plot Ahorros
    ax.plot(
        transactions["date"],
        transactions["accumulated_ahorros"],
        marker="o",
        linestyle="-",
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Euros (€)")
    ax.set_title("Ahorros")
    fig.autofmt_xdate()  # rotate & align date labels

    return fig


def plot_last_months_category_expense_pie(transactions: pd.DataFrame) -> Figure:
    """Plot a pie chart of the last month's transactions by category.

    Args:
        transactions (pd.DataFrame): DataFrame containing transaction details.

    Returns:
        plt.Figure: A matplotlib figure object containing the pie chart.
    """

    # Filter transactions for the last month
    last_month = datetime.datetime.now() - pd.DateOffset(months=1)
    recent_transactions = transactions[transactions["date"] >= last_month]

    total_expenses = recent_transactions[recent_transactions["type"] == "Expense"][
        "amount"
    ].sum()
    total_expenses = abs(total_expenses)  # Ensure total expenses is positive

    # Group expenses by category and sum amounts
    category_expenses = (
        recent_transactions[recent_transactions["type"] == "Expense"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
    )
    category_expenses = category_expenses[category_expenses["amount"] < 0]
    category_expenses["amount"] = category_expenses["amount"].abs()

    # Change category_expenses["category"] to contain category, and the sum of that category
    category_expenses["category"] = (
        category_expenses["category"]
        + " ("
        + category_expenses["amount"].astype(str)
        + " €)"
    )

    # Create pie chart
    cmap = plt.get_cmap("Pastel1")
    base_colors = cmap.colors  # type: ignore

    # if you have more categories than colors in Set3, it will wrap around:
    colors = [base_colors[i % len(base_colors)] for i in range(len(category_expenses))]

    fig, ax = plt.subplots()
    ax.pie(
        category_expenses["amount"],
        labels=category_expenses["category"],  # type: ignore
        startangle=90,
        colors=colors,
    )

    # Add total expenses number in the center of the pie chart
    total_expenses_str = f"{total_expenses:.2f} €"
    ax.text(
        0,
        0,
        total_expenses_str,
        horizontalalignment="center",
        verticalalignment="center",
        fontsize=12,
        fontweight="bold",
    )
    ax.axis("equal")  # Equal aspect ratio ensures that pie is drawn as a circle.
    fig.tight_layout()  # Adjust layout to prevent clipping of pie chart

    return fig


def deploy_streamlit() -> None:
    """Deploy the Streamlit app to visualize transactions data."""

    st.title("Dashboard")
    df = get_transactions()

    current_money, current_tarjeta, current_efectivo, current_ahorros = (
        get_current_money(df)
    )
    fig_total = plot_total_money(df)
    fig_ahorros = plot_ahorros(df)
    fig_pie = plot_last_months_category_expense_pie(df)

    #### Display Dashboard

    # Display current money
    st.metric("Dinero Total", f"{current_money:.2f} €")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tarjeta", f"{current_tarjeta:.2f} €")
    with col2:
        st.metric("Efectivo", f"{current_efectivo:.2f} €")
    with col3:
        st.metric("Ahorros", f"{current_ahorros:.2f} €")

    st.header("Graficos")

    # Display both plots side to side
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Dinero Total")
        st.pyplot(fig_total)
    with col2:
        st.subheader("Ahorros")
        st.pyplot(fig_ahorros)

    # Display pie chart of last month's transactions by category
    st.subheader("Gastos del Último Mes por Categoría")
    st.pyplot(fig_pie)


###############################################
deploy_streamlit()
