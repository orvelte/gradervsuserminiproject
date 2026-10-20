"""Clean the customer export: data/customers_raw.csv -> data/customers_clean.csv."""
import csv

COLUMNS = ["customer_id", "name", "email", "phone", "country", "signup_date", "plan"]


def main() -> None:
    with open("data/customers_raw.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    with open("data/customers_clean.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
