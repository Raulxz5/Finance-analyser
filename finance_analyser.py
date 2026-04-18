"""
Personal Finance Analyser
=========================
Imports bank statement CSV → SQLite, categorises transactions,
runs SQL analytics, and generates Matplotlib visualisations.

Usage:
    python finance_analyser.py transactions.csv
"""

import sys
import sqlite3
import re
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

# ── Output paths ──────────────────────────────────────────────────────────────
OUT_DIR  = Path("output")
DB_PATH  = OUT_DIR / "finance.db"
CHART_SPENDING   = OUT_DIR / "spending_breakdown.png"
CHART_BALANCE    = OUT_DIR / "balance_over_time.png"
CHART_CATEGORIES = OUT_DIR / "category_trends.png"
CHART_DASHBOARD  = OUT_DIR / "dashboard.png"

# ── Category rules  (order matters — first match wins) ────────────────────────
CATEGORY_RULES = [
    # Income
    ("Income",        r"datori|R Law Beer|paid in"),
    # Housing
    ("Rent",          r"Ryan Law Rent|UNIHOMES"),
    # Transport
    ("Transport",     r"FIRST WEST OF ENGL|DVLA|BUS|TRAIN|UBER|TAXI"),
    ("Fuel",          r"SAINSBURYS PETROL|PETROL|FUEL|BP "),
    # Groceries
    ("Groceries",     r"LIDL|SAINSBURYS S/MKTS|TESCO|ALDI|ASDA|MORRISONS|WAITROSE"),
    # Eating out
    ("Eating Out",    r"DOMINO|PIZZA|ISTANBUL|THIRSTY MEEPLE|KFC|McDONALD|BURGER|SUBWAY|NANDO"),
    # Entertainment / gaming
    ("Gaming",        r"STEAM|STEAMGAMES|SCL\.GG|WWW\.SCL"),
    ("Gambling",      r"POKERSTARS|BETFAIR|BET365|PADDY"),
    # Subscriptions
    ("Subscriptions", r"APPLE\.COM/BILL|NETFLIX|SPOTIFY|AMAZON PRIME|DISNEY"),
    # Shopping
    ("Shopping",      r"AMAZON"),
    # Fallback
    ("Other",         r".*"),
]


def categorise(description: str, paid_in: float) -> str:
    if paid_in > 0:
        return "Income"
    desc = description.upper()
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, desc, re.IGNORECASE):
            return category
    return "Other"


# ── 1. Load & clean CSV ───────────────────────────────────────────────────────
def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df.columns = [c.strip() for c in df.columns]
    df.rename(columns={"Paid Out": "paid_out", "Paid In": "paid_in",
                        "Balance": "balance", "Date": "date",
                        "Description": "description"}, inplace=True)
    df["paid_out"] = pd.to_numeric(df["paid_out"], errors="coerce").fillna(0)
    df["paid_in"]  = pd.to_numeric(df["paid_in"],  errors="coerce").fillna(0)
    df["balance"]  = pd.to_numeric(df["balance"],  errors="coerce")
    df["category"] = df.apply(
        lambda r: categorise(r["description"], r["paid_in"]), axis=1
    )
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df


# ── 2. Store in SQLite ────────────────────────────────────────────────────────
def store_sqlite(df: pd.DataFrame, db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    df.to_sql("transactions", conn, if_exists="replace", index=False)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_category ON transactions(category)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_date ON transactions(date)
    """)
    conn.commit()
    return conn


# ── 3. SQL analytics ──────────────────────────────────────────────────────────
def run_analytics(conn: sqlite3.Connection) -> dict:
    results = {}

    results["total_out"] = pd.read_sql(
        "SELECT SUM(paid_out) AS total FROM transactions WHERE paid_out > 0", conn
    )["total"].iloc[0]

    results["total_in"] = pd.read_sql(
        "SELECT SUM(paid_in) AS total FROM transactions WHERE paid_in > 0", conn
    )["total"].iloc[0]

    results["by_category"] = pd.read_sql("""
        SELECT category,
               ROUND(SUM(paid_out), 2) AS total_spent,
               COUNT(*)               AS num_transactions
        FROM   transactions
        WHERE  paid_out > 0
        GROUP  BY category
        ORDER  BY total_spent DESC
    """, conn)

    results["top_transactions"] = pd.read_sql("""
        SELECT date, description, paid_out, category
        FROM   transactions
        WHERE  paid_out > 0
        ORDER  BY paid_out DESC
        LIMIT  10
    """, conn)

    results["monthly_summary"] = pd.read_sql("""
        SELECT month,
               ROUND(SUM(paid_out), 2) AS spent,
               ROUND(SUM(paid_in),  2) AS income
        FROM   transactions
        GROUP  BY month
        ORDER  BY month
    """, conn)

    results["daily_balance"] = pd.read_sql("""
        SELECT date, balance
        FROM   transactions
        WHERE  balance IS NOT NULL
        ORDER  BY date
    """, conn)

    return results


# ── 4. Visualisations ─────────────────────────────────────────────────────────
PALETTE = [
    "#4361EE", "#F72585", "#4CC9F0", "#7209B7", "#3A0CA3",
    "#560BAD", "#480CA8", "#3F37C9", "#F77F00", "#FCBF49",
]

def style_axis(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor("#0f0f1a")
    ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, color="#aaaaaa", fontsize=9)
    ax.set_ylabel(ylabel, color="#aaaaaa", fontsize=9)
    ax.tick_params(colors="#aaaaaa", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")


def plot_dashboard(results: dict, df: pd.DataFrame):
    fig = plt.figure(figsize=(16, 10), facecolor="#0a0a14")
    gs  = GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35,
                   left=0.06, right=0.97, top=0.91, bottom=0.08)

    # ── Title bar ──────────────────────────────────────────────────────────
    fig.text(0.5, 0.96, "Personal Finance Dashboard",
             ha="center", va="top", fontsize=18, fontweight="bold",
             color="white")
    period = f"{df['date'].min().strftime('%d %b %Y')}  →  {df['date'].max().strftime('%d %b %Y')}"
    fig.text(0.5, 0.925, period, ha="center", va="top",
             fontsize=10, color="#888888")

    # ── KPI strip ──────────────────────────────────────────────────────────
    kpis = [
        ("Total Spent",   f"£{results['total_out']:.2f}",  "#F72585"),
        ("Total Income",  f"£{results['total_in']:.2f}",   "#4CC9F0"),
        ("Net",           f"£{results['total_in'] - results['total_out']:.2f}",
                           "#4CC9F0" if results['total_in'] >= results['total_out'] else "#F72585"),
        ("Transactions",  str(len(df[df["paid_out"] > 0])),           "#4361EE"),
    ]
    for i, (label, value, colour) in enumerate(kpis):
        x = 0.13 + i * 0.205
        fig.text(x, 0.885, value, ha="center", fontsize=14,
                 fontweight="bold", color=colour)
        fig.text(x, 0.865, label, ha="center", fontsize=8, color="#888888")

    # ── [0,0] Pie: spending by category ────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    style_axis(ax1, "Spending by Category")
    cat = results["by_category"]
    wedges, texts, autotexts = ax1.pie(
        cat["total_spent"],
        labels=None,
        autopct=lambda p: f"{p:.0f}%" if p > 4 else "",
        colors=PALETTE[:len(cat)],
        startangle=140,
        wedgeprops=dict(linewidth=1.2, edgecolor="#0a0a14"),
        pctdistance=0.78,
    )
    for at in autotexts:
        at.set_fontsize(7)
        at.set_color("white")
    ax1.legend(
        wedges, [f"{r['category']}  £{r['total_spent']:.0f}"
                 for _, r in cat.iterrows()],
        loc="lower center", bbox_to_anchor=(0.5, -0.38),
        fontsize=7, framealpha=0, labelcolor="white",
        ncol=2, handlelength=1,
    )

    # ── [0,1] Bar: category totals ─────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    style_axis(ax2, "Spend per Category", ylabel="£")
    bars = ax2.barh(
        cat["category"][::-1],
        cat["total_spent"][::-1],
        color=PALETTE[:len(cat)][::-1],
        edgecolor="#0a0a14", linewidth=0.8,
    )
    for bar, val in zip(bars, cat["total_spent"][::-1]):
        ax2.text(bar.get_width() + 2, bar.get_y() + bar.get_height() / 2,
                 f"£{val:.0f}", va="center", color="white", fontsize=7)
    ax2.set_xlim(0, cat["total_spent"].max() * 1.25)
    ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:.0f}"))

    # ── [0,2] Top 5 expenses ────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    style_axis(ax3, "Top 5 Expenses")
    top5 = results["top_transactions"].head(5)
    short_labels = [
        re.sub(r"^[())\s*]+", "", d)[:28] for d in top5["description"]
    ]
    colours5 = [PALETTE[i % len(PALETTE)] for i in range(len(top5))]
    b = ax3.bar(range(len(top5)), top5["paid_out"], color=colours5,
                edgecolor="#0a0a14", linewidth=0.8)
    for bar, val in zip(b, top5["paid_out"]):
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 f"£{val:.0f}", ha="center", color="white", fontsize=7)
    ax3.set_xticks(range(len(top5)))
    ax3.set_xticklabels(short_labels, rotation=25, ha="right", fontsize=7)
    ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:.0f}"))

    # ── [1, 0:2] Balance over time ─────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 0:2])
    style_axis(ax4, "Account Balance Over Time", ylabel="Balance (£)")
    bal = results["daily_balance"].copy()
    bal["date"] = pd.to_datetime(bal["date"])
    bal = bal.sort_values("date")

    ax4.fill_between(bal["date"], bal["balance"], 0,
                     where=(bal["balance"] >= 0),
                     alpha=0.25, color="#4CC9F0", interpolate=True)
    ax4.fill_between(bal["date"], bal["balance"], 0,
                     where=(bal["balance"] < 0),
                     alpha=0.25, color="#F72585", interpolate=True)
    ax4.plot(bal["date"], bal["balance"], color="#4CC9F0", linewidth=2, zorder=3)
    ax4.axhline(0, color="#F72585", linewidth=0.8, linestyle="--", alpha=0.6)
    ax4.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:.0f}"))
    ax4.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=30, ha="right")

    # ── [1,2] Monthly in vs out ────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 2])
    style_axis(ax5, "Monthly Income vs Spending", ylabel="£")
    ms   = results["monthly_summary"]
    x    = range(len(ms))
    w    = 0.35
    ax5.bar([i - w/2 for i in x], ms["income"], width=w,
            color="#4CC9F0", label="Income",  edgecolor="#0a0a14")
    ax5.bar([i + w/2 for i in x], ms["spent"],  width=w,
            color="#F72585", label="Spending", edgecolor="#0a0a14")
    ax5.set_xticks(list(x))
    ax5.set_xticklabels(ms["month"], rotation=20, ha="right", fontsize=8)
    ax5.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:.0f}"))
    ax5.legend(fontsize=8, framealpha=0, labelcolor="white")

    plt.savefig(CHART_DASHBOARD, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  ✓ Dashboard saved → {CHART_DASHBOARD}")


# ── 5. Print text report ──────────────────────────────────────────────────────
def print_report(results: dict, df: pd.DataFrame):
    sep = "─" * 52
    print(f"\n{'═'*52}")
    print(f"  PERSONAL FINANCE REPORT")
    print(f"  {df['date'].min().strftime('%d %b %Y')} → {df['date'].max().strftime('%d %b %Y')}")
    print(f"{'═'*52}")

    net = results["total_in"] - results["total_out"]
    print(f"\n  Total Income  : £{results['total_in']:>8.2f}")
    print(f"  Total Spent   : £{results['total_out']:>8.2f}")
    print(f"  Net           : £{net:>8.2f}  {'⚠ OVERDRAWN' if net < 0 else '✓'}")

    print(f"\n{sep}")
    print(f"  {'CATEGORY':<20} {'SPENT':>8}  {'TXNS':>5}  {'% OF TOTAL':>10}")
    print(sep)
    total = results["total_out"]
    for _, row in results["by_category"].iterrows():
        pct = row["total_spent"] / total * 100 if total else 0
        print(f"  {row['category']:<20} £{row['total_spent']:>7.2f}  "
              f"{int(row['num_transactions']):>5}  {pct:>9.1f}%")

    print(f"\n{sep}")
    print("  TOP 5 TRANSACTIONS")
    print(sep)
    for _, row in results["top_transactions"].head(5).iterrows():
        desc = re.sub(r"^[())\s*]+", "", row["description"])[:32]
        print(f"  £{row['paid_out']:>7.2f}  {desc:<32}  [{row['category']}]")

    print(f"\n{'═'*52}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "transactions.csv"

    OUT_DIR.mkdir(exist_ok=True)

    print("\n📥  Loading CSV...")
    df = load_csv(csv_path)
    print(f"    {len(df)} transactions loaded, {df['category'].nunique()} categories detected")

    print("🗄   Storing in SQLite...")
    conn = store_sqlite(df, DB_PATH)
    print(f"    Database saved → {DB_PATH}")

    print("🔍  Running SQL analytics...")
    results = run_analytics(conn)

    print("📊  Generating visualisations...")
    plot_dashboard(results, df)

    print_report(results, df)
    conn.close()


if __name__ == "__main__":
    main()