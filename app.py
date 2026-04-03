from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "expense_tracker_secret_key"
DB_NAME = "database.db"


# -----------------------------
# Database Connection
# -----------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------
# Initialize Database
# -----------------------------
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            note TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT UNIQUE NOT NULL,
            amount REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# -----------------------------
# Helper Functions
# -----------------------------
def get_current_month():
    return datetime.now().strftime("%Y-%m")


def get_month_name(month_str):
    try:
        return datetime.strptime(month_str, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return month_str


def get_previous_month(current_month):
    dt = datetime.strptime(current_month + "-01", "%Y-%m-%d")
    year = dt.year
    month = dt.month

    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def get_budget_for_month(month):
    conn = get_db_connection()
    budget = conn.execute(
        "SELECT amount FROM budgets WHERE month = ?",
        (month,)
    ).fetchone()
    conn.close()
    return budget["amount"] if budget else 0


def get_total_expense_for_month(month):
    conn = get_db_connection()
    result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
    """, (month,)).fetchone()
    conn.close()
    return result["total"]


def get_top_category(month):
    conn = get_db_connection()
    result = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """, (month,)).fetchone()
    conn.close()
    return result


def get_available_months():
    conn = get_db_connection()
    months = conn.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) AS month
        FROM expenses
        WHERE date IS NOT NULL
        ORDER BY month DESC
    """).fetchall()
    conn.close()

    months_list = [row["month"] for row in months if row["month"]]

    if not months_list:
        months_list = [get_current_month()]

    return months_list


def generate_insights(current_month):
    insights = []

    current_total = get_total_expense_for_month(current_month)
    budget = get_budget_for_month(current_month)
    top_category = get_top_category(current_month)
    previous_month = get_previous_month(current_month)
    previous_total = get_total_expense_for_month(previous_month)

    if top_category:
        insights.append(
            f"Your highest spending category this month is {top_category['category']} (₹{top_category['total']:.2f})."
        )

    if budget > 0:
        percent_used = (current_total / budget) * 100
        if percent_used >= 100:
            insights.append("You have exceeded your monthly budget.")
        elif percent_used >= 80:
            insights.append("You have used more than 80% of your monthly budget.")
        else:
            insights.append(f"You have used {percent_used:.1f}% of your monthly budget.")

    if previous_total > 0:
        if current_total > previous_total:
            diff = current_total - previous_total
            insights.append(f"You spent ₹{diff:.2f} more than last month.")
        elif current_total < previous_total:
            diff = previous_total - current_total
            insights.append(f"You spent ₹{diff:.2f} less than last month.")
        else:
            insights.append("Your spending is the same as last month.")

    if current_total == 0:
        insights.append("No expenses found for this month. Add some expenses to view analytics.")

    if not insights:
        insights.append("Start adding expenses to view smart insights.")

    return insights


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    months_list = get_available_months()
    selected_month = request.args.get("month")

    if not selected_month or selected_month not in months_list:
        selected_month = months_list[0]

    conn = get_db_connection()

    expenses = conn.execute("""
        SELECT * FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        ORDER BY date DESC, id DESC
        LIMIT 5
    """, (selected_month,)).fetchall()

    total_expense = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
    """, (selected_month,)).fetchone()["total"]

    category_data = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC
    """, (selected_month,)).fetchall()

    conn.close()

    budget = get_budget_for_month(selected_month)
    remaining = budget - total_expense if budget else 0
    insights = generate_insights(selected_month)

    categories = [row["category"] for row in category_data]
    totals = [row["total"] for row in category_data]

    return render_template(
        "index.html",
        expenses=expenses,
        total_expense=total_expense,
        budget=budget,
        remaining=remaining,
        categories=categories,
        totals=totals,
        insights=insights,
        selected_month=selected_month,
        month_name=get_month_name(selected_month),
        months_list=months_list
    )


@app.route("/add", methods=["GET", "POST"])
def add_expense():
    if request.method == "POST":
        amount = request.form.get("amount")
        category = request.form.get("category")
        date = request.form.get("date")
        note = request.form.get("note", "")

        if not amount or not category or not date:
            flash("Please fill all required fields.", "error")
            return redirect(url_for("add_expense"))

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO expenses (amount, category, date, note)
            VALUES (?, ?, ?, ?)
        """, (amount, category, date, note))
        conn.commit()
        conn.close()

        flash("Expense added successfully!", "success")
        return redirect(url_for("transactions"))

    return render_template("add_expense.html", expense=None, edit_mode=False)


@app.route("/transactions")
def transactions():
    conn = get_db_connection()
    expenses = conn.execute("""
        SELECT * FROM expenses
        ORDER BY date DESC, id DESC
    """).fetchall()
    conn.close()

    return render_template("transactions.html", expenses=expenses)


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    conn = get_db_connection()
    expense = conn.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (expense_id,)
    ).fetchone()

    if not expense:
        conn.close()
        flash("Expense not found.", "error")
        return redirect(url_for("transactions"))

    if request.method == "POST":
        amount = request.form.get("amount")
        category = request.form.get("category")
        date = request.form.get("date")
        note = request.form.get("note", "")

        if not amount or not category or not date:
            conn.close()
            flash("Please fill all required fields.", "error")
            return redirect(url_for("edit_expense", expense_id=expense_id))

        conn.execute("""
            UPDATE expenses
            SET amount = ?, category = ?, date = ?, note = ?
            WHERE id = ?
        """, (amount, category, date, note, expense_id))
        conn.commit()
        conn.close()

        flash("Expense updated successfully!", "success")
        return redirect(url_for("transactions"))

    conn.close()
    return render_template("add_expense.html", expense=expense, edit_mode=True)


@app.route("/delete/<int:expense_id>")
def delete_expense(expense_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

    flash("Expense deleted successfully!", "success")
    return redirect(url_for("transactions"))


@app.route("/budget", methods=["GET", "POST"])
def budget():
    months_list = get_available_months()
    selected_month = request.args.get("month", get_current_month())

    if request.method == "POST":
        month = request.form.get("month")
        amount = request.form.get("amount")

        if not month or not amount:
            flash("Please enter month and budget amount.", "error")
            return redirect(url_for("budget"))

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT * FROM budgets WHERE month = ?",
            (month,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE budgets SET amount = ? WHERE month = ?",
                (amount, month)
            )
        else:
            conn.execute(
                "INSERT INTO budgets (month, amount) VALUES (?, ?)",
                (month, amount)
            )

        conn.commit()
        conn.close()

        flash("Budget saved successfully!", "success")
        return redirect(url_for("budget", month=month))

    saved_budget = get_budget_for_month(selected_month)

    return render_template(
        "budget.html",
        selected_month=selected_month,
        saved_budget=saved_budget,
        month_name=get_month_name(selected_month),
        months_list=months_list
    )


@app.route("/reports")
def reports():
    months_list = get_available_months()
    selected_month = request.args.get("month")

    if not selected_month or selected_month not in months_list:
        selected_month = months_list[0]

    conn = get_db_connection()

    category_data = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC
    """, (selected_month,)).fetchall()

    monthly_trend = conn.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM expenses
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month ASC
    """).fetchall()

    yearly_data = conn.execute("""
        SELECT strftime('%Y', date) AS year, SUM(amount) AS total
        FROM expenses
        GROUP BY strftime('%Y', date)
        ORDER BY year ASC
    """).fetchall()

    conn.close()

    categories = [row["category"] for row in category_data]
    category_totals = [row["total"] for row in category_data]

    trend_months = [row["month"] for row in monthly_trend]
    trend_totals = [row["total"] for row in monthly_trend]

    years = [row["year"] for row in yearly_data]
    year_totals = [row["total"] for row in yearly_data]

    insights = generate_insights(selected_month)

    return render_template(
        "reports.html",
        categories=categories,
        category_totals=category_totals,
        trend_months=trend_months,
        trend_totals=trend_totals,
        years=years,
        year_totals=year_totals,
        insights=insights,
        selected_month=selected_month,
        month_name=get_month_name(selected_month),
        months_list=months_list
    )


# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)