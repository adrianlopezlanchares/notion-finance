from finance_graphs import get_transactions


if __name__ == "__main__":
    transactions = get_transactions()

    print(transactions.head(10))
