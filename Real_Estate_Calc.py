import tkinter as tk
from tkinter import ttk
import sys
import os
import re
import math
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams['font.family'] = 'DejaVu Sans'

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==============================
# Globals
# ==============================
saved_calculations = []
max_saves = 10
last_result = None
history_window = None
DEBUG_TAX = True
GOV_URL = "https://www.gov.il/he/service/real_eatate_taxsimulator"  # fallback used if unavailable

# Graph canvases and core GUI references
current_purchase_canvas = None
current_sale_canvas = None
root = None
frame_result = None
frame_graphs = None
counter_label = None

# Entry widgets (will be assigned in create_gui)
entry_sale_price = None
entry_broker_sale = None
entry_lawyer_sale = None
entry_purchase_price = None
entry_expenses = None
entry_exemption_limit = None

entry_buy_price = None
entry_broker_buy = None
entry_lawyer_buy = None

is_single_home_var = None
held_over_18_var = None

# ==============================
# Utility functions
# ==============================

def resource_path(relative_path: str) -> str:
    """
    NOTE: Return correct path for resources when running from EXE.
    Inputs: relative_path (str)
    Outputs: absolute path (str)
    """
    try:
        base_path = sys._MEIPASS  # PyInstaller temporary dir
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def safe_float(entry_widget: tk.Entry, name: str, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    """
    NOTE: Convert entry text to float with validation.
    Inputs: entry_widget (tk.Entry), name (str), optional min_val/max_val
    Outputs: float value
    Raises: ValueError with Hebrew message on invalid input
    """
    try:
        value = float(entry_widget.get().replace(",", ""))
    except ValueError:
        raise ValueError(f"שגיאה בשדה: {name} – אנא הכנס מספר תקין")

    if min_val is not None and value < min_val:
        raise ValueError(f"שגיאה בשדה: {name} – הערך חייב להיות ≥ {min_val}")
    if max_val is not None and value > max_val:
        raise ValueError(f"שגיאה בשדה: {name} – הערך חייב להיות ≤ {max_val}")

    return value


def format_entry_number(entry_widget: tk.Entry) -> None:
    """
    NOTE: Format entry number with commas (1,234,567).
    Inputs: entry_widget (tk.Entry)
    Outputs: None (modifies entry text)
    """
    value = entry_widget.get().replace(",", "")
    if value.isdigit():
        formatted = "{:,}".format(int(value))
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, formatted)

# ==============================
# Tax brackets handling
# ==============================

FALLBACK_PURCHASE_BRACKETS: List[Tuple[int, float, float]] = [
    (0, 1978745, 0.0),
    (1978745, 2347040, 0.035),
    (2347040, 6055070, 0.05),
    (6055070, 20183565, 0.08),
    (20183565, float("inf"), 0.10),
]


def extract_brackets_from_text(text: str) -> List[Tuple[int, float, float]]:
    """
    NOTE: Extract purchase tax brackets from free text.
    Inputs: text (str)
    Outputs: list of tuples (low, high, rate)
    """
    brackets: List[Tuple[int, float, float]] = []

    # First bracket: "עד X ש"ח – לא ישולם מס"
    m0 = re.search(r"עד\s+([\d,\.]+)\s+ש.?ח\s*–?\s*לא\s+ישולם\s+מס", text)
    if m0:
        first_high = int(m0.group(1).replace(",", ""))
        brackets.append((0, first_high, 0.0))

    # Middle brackets: "עד X ש"ח – Y%"
    mid_limits: List[Tuple[int, float]] = []
    for m in re.finditer(r"עד\s+([\d,\.]+)\s+ש.?ח\s*–?\s*(\d+(?:\.\d+)?)\s*%", text):
        high = int(m.group(1).replace(",", ""))
        rate = float(m.group(2)) / 100.0
        mid_limits.append((high, rate))

    low_cursor = brackets[-1][1] if brackets else 0
    for high, rate in mid_limits:
        if high > low_cursor:
            brackets.append((low_cursor, high, rate))
            low_cursor = high

    # Last bracket: "על חלק השווי העולה על X ש"ח – Y%"
    m_last = re.search(r"עולה\s+על\s+([\d,\.]+)\s+ש.?ח\s*–?\s*(\d+(?:\.\d+)?)\s*%", text)
    if m_last:
        last_low = int(m_last.group(1).replace(",", ""))
        last_rate = float(m_last.group(2)) / 100.0
        brackets.append((last_low, float("inf"), last_rate))

    return brackets


def fetch_purchase_tax_brackets() -> Optional[List[Tuple[int, float, float]]]:
    """
    NOTE: Fetch brackets from gov.il site.
    Inputs: None
    Outputs: list of brackets or None on failure
    """
    try:
        resp = requests.get(GOV_URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator="\n")
        return extract_brackets_from_text(text)
    except Exception as e:
        print(f"לא ניתן למשוך מדרגות מהאתר: {e}")
        return None


def get_purchase_tax_brackets() -> Tuple[List[Tuple[int, float, float]], dict]:
    """
    NOTE: Return purchase tax brackets with fallback.
    Inputs: None
    Outputs: (brackets list, meta dict)
    """
    fetched = fetch_purchase_tax_brackets()
    if fetched:
        return fetched, {"source": GOV_URL}
    else:
        if DEBUG_TAX:
            print("DEBUG: שימוש בגיבוי קשיח כי האתר לא זמין.")
        return FALLBACK_PURCHASE_BRACKETS, {"source": "fallback"}

# ==============================
# Tax calculation functions
# ==============================

def calculate_capital_gain_tax(
    sale_price: float,
    purchase_price: float,
    expenses: float,
    is_single_home: bool,
    held_over_18_months: bool,
    exemption_limit: float
    ) -> float:
    """
    NOTE: Calculate capital gain tax (מס שבח).
    Inputs: sale_price, purchase_price, expenses, is_single_home, held_over_18_months, exemption_limit
    Outputs: tax amount (float)
    """
    profit = sale_price - purchase_price - expenses
    if profit <= 0:
        return 0.0
    if is_single_home and held_over_18_months:
        if sale_price <= exemption_limit:
            return 0.0
        taxable_part = sale_price - exemption_limit
        return taxable_part * 0.25
    return profit * 0.25


def calculate_purchase_tax(price: float) -> float:
    """
    NOTE: Calculate purchase tax based on brackets (מס רכישה).
    Inputs: price (float)
    Outputs: tax amount (float)
    """
    brackets, _meta = get_purchase_tax_brackets()
    tax = 0.0
    for low, high, rate in brackets:
        span_low = low
        span_high = min(high, price)
        if span_high <= span_low:
            continue
        taxable_part = span_high - span_low
        tax += taxable_part * rate
    return tax

def get_purchase_tax_breakdown(price: float):
    """
    NOTE: Calculate purchase tax breakdown per bracket.
    Inputs: price (float)
    Outputs: list of dicts: [
        {
            'index': int,
            'low': float,
            'high': float or inf,
            'rate': float,
            'taxable_amount': float,
            'tax_amount': float
        },
        ...
    ]
    """
    brackets, _meta = get_purchase_tax_brackets()
    breakdown = []

    for i, (low, high, rate) in enumerate(brackets, start=1):
        span_high = min(high, price)
        if span_high <= low:
            taxable = 0.0
        else:
            taxable = span_high - low

        tax_amount = taxable * rate

        breakdown.append({
            "index": i,
            "low": low,
            "high": high,
            "rate": rate,
            "taxable_amount": taxable,
            "tax_amount": tax_amount
        })

    return breakdown


# ==============================
# Graph functions
# ==============================
'''
def build_purchase_pie(total_price: float, broker_fee: float, lawyer_fee: float, purchase_tax: float):
    """
    NOTE: Build pie chart for purchase costs.
    Inputs: total_price (float), broker_fee (float), lawyer_fee (float), purchase_tax (float)
    Outputs: matplotlib Figure
    """
    net_price = total_price - (broker_fee + lawyer_fee + purchase_tax)
    labels = ["מחיר קנייה", "עמלת תיווך", "עמלת עורך דין", "מס רכישה"]
    values = [max(net_price, 0), broker_fee, lawyer_fee, purchase_tax]
    fig, ax = plt.subplots(figsize=(4, 4))
    fig.patch.set_alpha(0.0)  # transparent figure background
    ax.set_facecolor("none")  # transparent axes background
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.set_title("חלוקת עלויות בקנייה")
    ax.axis('equal')
    return fig


def build_sale_pie(sale_price: float, broker_fee: float, lawyer_fee: float, sale_tax: float):
    """
    NOTE: Build pie chart for sale distribution.
    Inputs: sale_price (float), broker_fee (float), lawyer_fee (float), sale_tax (float)
    Outputs: matplotlib Figure
    """
    net_income = sale_price - (broker_fee + lawyer_fee + sale_tax)
    labels = ["עמלת תיווך", "עמלת עורך דין", "מס מכירה", "נטו לכיס"]
    values = [broker_fee, lawyer_fee, sale_tax, max(net_income, 0)]
    fig, ax = plt.subplots(figsize=(4, 4))
    fig.patch.set_alpha(0.0)  # transparent figure background
    ax.set_facecolor("none")  # transparent axes background
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.set_title("חלוקת עלויות במכירה")
    ax.axis('equal')
    return fig
'''

def build_purchase_brackets_bar(price: float, breakdown):
    """
    NOTE: Build a vertical stacked bar chart showing purchase price (in M‑NIS)
          split by tax brackets. Each segment is one tax bracket.
    Inputs: price (float), breakdown (list from get_purchase_tax_breakdown)
    Outputs: matplotlib Figure
    """
    # Convert to millions for display
    price_m = price / 1_000_000 if price > 0 else 1.0

    # Heights = taxable amount per bracket (in M‑NIS)
    heights_m = [b["taxable_amount"] / 1_000_000 for b in breakdown]

    # Colors for brackets (will repeat if more brackets)
    colors = [
        "#4A90E2", "#50E3C2", "#F5A623", "#D0021B",
        "#9013FE", "#B8E986", "#F8E71C", "#7ED321"
    ]
    if len(heights_m) > len(colors):
        colors = (colors * ((len(heights_m) // len(colors)) + 1))[:len(heights_m)]
    else:
        colors = colors[:len(heights_m)]

    fig, ax = plt.subplots(figsize=(1, 1))  # smaller vertical figure
    fig.patch.set_alpha(0.0)      # transparent background
    ax.set_facecolor("none")

    bottom = 0.0
    segment_colors = []  # we’ll return this to match colors with text if needed

    for i, (h_m, color, b) in enumerate(zip(heights_m, colors, breakdown)):
        if h_m <= 0:
            continue

        # Draw stacked vertical bar (single x=0)
        ax.bar(
            x=0,
            height=h_m,
            bottom=bottom,
            color=color,
            edgecolor="black"
        )

        # Text inside the segment: "Bracket # | XX.X%"
        rate_pct = b["rate"] * 100.0
        ax.text(
            0,
            bottom + h_m / 2,
            f"{b['index']} | {rate_pct:.1f}%",
            ha="center",
            va="center",
            fontsize=8,
            color="black"
        )

        segment_colors.append(color)
        bottom += h_m

    # X axis: hide ticks (single bar)
    ax.set_xticks([])
    ax.set_xlim(-0.5, 0.5)

    # Y axis: purchase price in M‑NIS
    ax.set_ylabel("Purchase price (Million NIS)", fontsize=10)
    ax.set_ylim(0, price_m)

    # Y ticks in nice steps
    yticks = [price_m * x for x in [0, 0.25, 0.5, 0.75, 1.0]]
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{y:.2f}" for y in yticks])

    ax.set_title("Purchase tax brackets (stacked)", fontsize=12)
    '''
    # Add total tax above the bar
    total_tax = sum(b["tax_amount"] for b in breakdown)
    total_tax_m = total_tax / 1_000_000  # convert to M‑NIS

    ax.text(
        0, price_m * 1.02,  # slightly above the bar
        f"Total Tax: {total_tax_m:.3f} M‑NIS",
        ha="center",
        va="bottom",
        fontsize=10,
        fontweight="bold",
        color="black"
    )
    '''
    # Return both figure and the colors used per bracket (to sync with text)
    return fig, colors

# ==============================
# History and save functions
# ==============================

def save_calculation() -> None:
    """
    NOTE: Save the last calculation to history list.
    Inputs: None (uses globals)
    Outputs: None (updates UI counter)
    """
    global last_result, saved_calculations, counter_label, frame_result

    # Limit saves
    if len(saved_calculations) >= max_saves:
        counter_label.config(text="מלא (10/10)", fg="red")
        return

    # Must have a calculation
    if last_result is None:
        for widget in frame_result.winfo_children():
            widget.destroy()
        tk.Label(frame_result, text="אין חישוב לשמירה. בצע חישוב קודם.", font=("Arial", 16), fg="red").grid(row=0, column=0, columnspan=2)
        return

    saved_calculations.append(last_result.copy())
    counter_label.config(text=f"{len(saved_calculations)}/{max_saves}", fg="green")


def show_history() -> None:
    """
    NOTE: Show saved calculations history in a single toplevel window.
    Inputs: None (uses globals)
    Outputs: None (creates/updates window)
    """
    global history_window, root

    # Close existing history window if open
    if history_window is not None and history_window.winfo_exists():
        history_window.destroy()

    history_window = tk.Toplevel(root)
    history_window.title("היסטוריית חישובים")

    if not saved_calculations:
        tk.Label(history_window, text="אין חישובים להצגה", font=("Arial", 16), fg="red").grid(row=0, column=0, pady=10)
        return

    tk.Label(history_window, text="היסטוריית חישובים", font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=8, pady=10)

    headers = ["#", "מחיר מכירה", "עמלת תיווך מכירה %", "עמלת עו\"ד מכירה %",
               "מחיר קנייה", "עמלת תיווך קנייה %", "עמלת עו\"ד קנייה %", "הפרש נטו"]
    for col, h in enumerate(headers):
        tk.Label(history_window, text=h, font=("Arial", 12, "bold"), borderwidth=1, relief="solid").grid(row=1, column=col, padx=5, pady=5)

    for i, calc in enumerate(saved_calculations, start=1):
        row = i + 1

        if calc['difference'] > 0:
            bg_color = "lightgreen"
        elif calc['difference'] < 0:
            bg_color = "lightcoral"
        else:
            bg_color = "lightyellow"

        tk.Label(history_window, text=f"חישוב {i}", font=("Arial", 12), borderwidth=1, relief="solid").grid(row=row, column=0, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['sale_price']:,.0f}", font=("Arial", 12), borderwidth=1, relief="solid", bg="lavender").grid(row=row, column=1, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['broker_fee_sale_percent']}%", font=("Arial", 12), borderwidth=1, relief="solid", bg="lavender").grid(row=row, column=2, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['lawyer_fee_sale_percent']}%", font=("Arial", 12), borderwidth=1, relief="solid", bg="lavender").grid(row=row, column=3, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['buy_price']:,.0f}", font=("Arial", 12), borderwidth=1, relief="solid", bg="honeydew").grid(row=row, column=4, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['broker_fee_buy_percent']}%", font=("Arial", 12), borderwidth=1, relief="solid", bg="honeydew").grid(row=row, column=5, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['lawyer_fee_buy_percent']}%", font=("Arial", 12), borderwidth=1, relief="solid", bg="honeydew").grid(row=row, column=6, padx=5, pady=5)
        tk.Label(history_window, text=f"{calc['difference']:,.0f} ({calc['status']})", font=("Arial", 12), borderwidth=1, relief="solid", bg=bg_color).grid(row=row, column=7, padx=5, pady=5)


def clear_history() -> None:
    """
    NOTE: Clear saved calculations, update GUI, and also clear pie charts.
    Inputs: None (uses globals)
    Outputs: None (updates UI)
    """
    global saved_calculations, history_window, counter_label, frame_result, frame_graphs

    # Clear saved list
    saved_calculations.clear()
    counter_label.config(text="0/10", fg="green")

    # Clear history window if open
    if history_window is not None and history_window.winfo_exists():
        for widget in history_window.winfo_children():
            widget.destroy()
        tk.Label(history_window, text="אין חישובים להצגה", font=("Arial", 16), fg="red").grid(row=0, column=0, pady=10)

    # Clear result frame
    for widget in frame_result.winfo_children():
        widget.destroy()
    tk.Label(frame_result, text="היסטוריה נמחקה", font=("Arial", 16), fg="blue").grid(row=0, column=0, columnspan=2)

    # 🔑 Clear graphs frame too
    for widget in frame_graphs.winfo_children():
        widget.destroy()


# ==============================
# Calculation and rendering
# ==============================

def calculate() -> None:
    """
    NOTE: Perform calculation, show results on the left, and render graphs on the right.
    Inputs: None (reads from Entry widgets)
    Outputs: None (updates the GUI)
    """
    global last_result, current_purchase_canvas, current_sale_canvas

    try:
        # Inputs - sale
        sale_price = safe_float(entry_sale_price, "מחיר מכירה", min_val=0)
        broker_fee_sale_percent = safe_float(entry_broker_sale, "עמלת תיווך מכירה", min_val=0, max_val=100)
        lawyer_fee_sale_percent = safe_float(entry_lawyer_sale, "עמלת עו\"ד מכירה", min_val=0, max_val=100)
        purchase_price = safe_float(entry_purchase_price, "מחיר רכישה מקורי", min_val=0)
        expenses = safe_float(entry_expenses, "הוצאות מוכרות", min_val=0)
        exemption_limit = safe_float(entry_exemption_limit, "תקרת פטור", min_val=0)

        # Inputs - buy
        buy_price = safe_float(entry_buy_price, "מחיר קנייה", min_val=0)
        broker_fee_buy_percent = safe_float(entry_broker_buy, "עמלת תיווך קנייה", min_val=0, max_val=100)
        lawyer_fee_buy_percent = safe_float(entry_lawyer_buy, "עמלת עו\"ד קנייה", min_val=0, max_val=100)

        is_single_home = is_single_home_var.get()
        held_over_18_months = held_over_18_var.get()

        # Taxes
        tax_sale = calculate_capital_gain_tax(
            sale_price, purchase_price, expenses, is_single_home, held_over_18_months, exemption_limit
        )
        tax_buy = calculate_purchase_tax(buy_price)

        # Fees
        broker_fee_sale = sale_price * (broker_fee_sale_percent / 100.0)
        broker_fee_buy = buy_price * (broker_fee_buy_percent / 100.0)
        lawyer_fee_sale = sale_price * (lawyer_fee_sale_percent / 100.0)
        lawyer_fee_buy = buy_price * (lawyer_fee_buy_percent / 100.0)

        # Totals
        total_buy = buy_price + broker_fee_buy + lawyer_fee_buy + tax_buy
        total_sale = sale_price - broker_fee_sale - lawyer_fee_sale - tax_sale
        difference = total_sale - total_buy

        # Clear previous result
        for widget in frame_result.winfo_children():
            widget.destroy()

        # Result headers
        tk.Label(frame_result, text="מכירה", font=("Arial", 16, "bold")).grid(row=0, column=0, padx=20)
        tk.Label(frame_result, text="קנייה", font=("Arial", 16, "bold")).grid(row=0, column=1, padx=20)

        # Sale details
        tk.Label(frame_result, text=f"מחיר מכירה: {sale_price:,.0f} ₪", font=("Arial", 16)).grid(row=1, column=0, sticky="w")
        tk.Label(frame_result, text=f"עמלת תיווך: {broker_fee_sale:,.0f} ₪", font=("Arial", 16)).grid(row=2, column=0, sticky="w")
        tk.Label(frame_result, text=f"עמלת עו\"ד: {lawyer_fee_sale:,.0f} ₪", font=("Arial", 16)).grid(row=3, column=0, sticky="w")
        tk.Label(frame_result, text=f"מס מכירה: {tax_sale:,.0f} ₪", font=("Arial", 16)).grid(row=4, column=0, sticky="w")
        tk.Label(frame_result, text=f"סה\"כ נטו: {total_sale:,.0f} ₪", font=("Arial", 16, "bold")).grid(row=5, column=0, sticky="w")

        # Buy details
        tk.Label(frame_result, text=f"מחיר קנייה: {buy_price:,.0f} ₪", font=("Arial", 16)).grid(row=1, column=1, sticky="w")
        tk.Label(frame_result, text=f"עמלת תיווך: {broker_fee_buy:,.0f} ₪", font=("Arial", 16)).grid(row=2, column=1, sticky="w")
        tk.Label(frame_result, text=f"עמלת עו\"ד: {lawyer_fee_buy:,.0f} ₪", font=("Arial", 16)).grid(row=3, column=1, sticky="w")
        tk.Label(frame_result, text=f"מס רכישה: {tax_buy:,.0f} ₪", font=("Arial", 16)).grid(row=4, column=1, sticky="w")
        tk.Label(frame_result, text=f"סה\"כ כולל: {total_buy:,.0f} ₪", font=("Arial", 16, "bold")).grid(row=5, column=1, sticky="w")

        # Difference line
        if difference > 0:
            bg_color = "lightgreen"
            status = "מרוויחים"
            display_amount = f"{difference:,.0f} ₪"
        elif difference < 0:
            bg_color = "lightcoral"
            status = "צריך להוסיף"
            display_amount = f"{abs(difference):,.0f} ₪"
        else:
            bg_color = "lightyellow"
            status = "מאוזן"
            display_amount = "0 ₪"

        tk.Label(frame_result, text=f"הפרש נטו: {display_amount} ({status})",
                 font=("Arial", 16, "bold"), bg=bg_color).grid(row=6, column=0, columnspan=2, pady=10)

        # Store last result
        last_result = {
            "sale_price": sale_price,
            "broker_fee_sale_percent": broker_fee_sale_percent,
            "lawyer_fee_sale_percent": lawyer_fee_sale_percent,
            "purchase_price": purchase_price,
            "expenses": expenses,
            "buy_price": buy_price,
            "broker_fee_buy_percent": broker_fee_buy_percent,
            "lawyer_fee_buy_percent": lawyer_fee_buy_percent,
            "tax_sale": tax_sale,
            "tax_buy": tax_buy,
            "total_sale": total_sale,
            "total_buy": total_buy,
            "difference": difference,
            "status": status
        }
        '''
        # Render graphs on the right: clear previous and draw new
        for w in frame_graphs.winfo_children():
            w.destroy()

        # Purchase pie: whole pie = total_buy, slices = נטו, תיווך, עו"ד, מס רכישה
        fig_purchase = build_purchase_pie(total_buy, broker_fee_buy, lawyer_fee_buy, tax_buy)
        canvas_purchase = FigureCanvasTkAgg(fig_purchase, master=frame_graphs)
        canvas_purchase.draw()
        canvas_purchase.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Sale pie: whole pie = sale_price, slices = תיווך, עו"ד, מס מכירה, נטו לכיס
        fig_sale = build_sale_pie(sale_price, broker_fee_sale, lawyer_fee_sale, tax_sale)
        canvas_sale = FigureCanvasTkAgg(fig_sale, master=frame_graphs)
        canvas_sale.draw()
        canvas_sale.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        frame_graphs.rowconfigure(0, weight=1)
        frame_graphs.rowconfigure(1, weight=1)
        frame_graphs.columnconfigure(0, weight=1)
        '''


        # ----- Render purchase tax brackets bar chart on the right -----
        for w in frame_graphs.winfo_children():
            w.destroy()

        # 1. Build breakdown for purchase tax per bracket
        breakdown = get_purchase_tax_breakdown(buy_price)

        # 2. Build stacked bar: purchase price split by brackets (numbers only)
        fig, colors = build_purchase_brackets_bar(buy_price, breakdown)
        canvas = FigureCanvasTkAgg(fig, master=frame_graphs)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # 3. Textual breakdown in English with matching colors
        info_frame = tk.Frame(frame_graphs)
        info_frame.grid(row=1, column=0, sticky="nw", padx=5, pady=5)

        tk.Label(
            info_frame,
            text="Purchase tax breakdown by bracket:",
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")

        row_idx = 1
        color_idx = 0

        for b in breakdown:
            if b["taxable_amount"] <= 0:
                continue  # skip brackets with no contribution

            low = b["low"]
            high = b["high"]
            rate = b["rate"]
            taxable = b["taxable_amount"]
            tax_amount = b["tax_amount"]

            # Range text in numbers only
            if math.isinf(high):
                range_str = f"{low:,.0f} - ∞"
            else:
                range_str = f"{low:,.0f} - {high:,.0f}"

            range_str = range_str.replace("‑", "-").replace("–", "-").replace("—", "-")

            text = (
                f"Bracket {b['index']}: {range_str} | "
                f"Rate: {rate * 100:.2f}% | "
                f"Taxable: {taxable:,.0f} | "
                f"Tax: {tax_amount:,.0f}"
            )

            # Match color with bar segment
            line_color = colors[color_idx % len(colors)]
            color_idx += 1

            tk.Label(
                info_frame,
                text=text,
                font=("Arial", 10),
                justify="left",
                anchor="w",
                fg=line_color
            ).grid(row=row_idx, column=0, sticky="w")

            row_idx += 1

        # Add total tax line
        total_tax = sum(b["tax_amount"] for b in breakdown)
        tk.Label(
            info_frame,
            text=f"Total Tax: {total_tax:,.0f} NIS",
            font=("Arial", 11, "bold"),
            fg="black"
        ).grid(row=row_idx, column=0, sticky="w")


        frame_graphs.rowconfigure(0, weight=1)
        frame_graphs.rowconfigure(1, weight=0)
        frame_graphs.columnconfigure(0, weight=1)

    except ValueError as e:
        # Clear previous result area
        for widget in frame_result.winfo_children():
            widget.destroy()
        # Show friendly error message
        tk.Label(frame_result, text=str(e), font=("Arial", 16), fg="red").grid(row=0, column=0, columnspan=2)
        last_result = None

# ==============================
# GUI construction
# ==============================

def create_gui() -> None:
    """
    NOTE: Build the entire GUI and assign globals.
    Inputs: None
    Outputs: None (creates the application window)
    """
    global root, frame_result, frame_graphs
    global entry_sale_price, entry_broker_sale, entry_lawyer_sale, entry_purchase_price, entry_expenses, entry_exemption_limit
    global entry_buy_price, entry_broker_buy, entry_lawyer_buy
    global is_single_home_var, held_over_18_var, counter_label

    # Root and basic options
    root = tk.Tk()
    root.title("מחשבון נדל\"ן")
    root.option_add("*Font", "Arial 16")

    # Layout: 3 columns (sale, buy, graphs)
    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)
    root.columnconfigure(2, weight=1)

    # Try to load images (optional)
    try:
        sell_img = tk.PhotoImage(file=resource_path("SellHouse.png"))
        buy_img = tk.PhotoImage(file=resource_path("BuyHouse.png"))
        tk.Label(root, image=sell_img).grid(row=0, column=0, pady=5)
        tk.Label(root, image=buy_img).grid(row=0, column=1, pady=5)
        # Keep references to avoid garbage collection
        root.sell_img = sell_img
        root.buy_img = buy_img
    except Exception:
        # If images missing, show textual headers only
        pass

    # Top headers
    tk.Label(root, text="מכירה", font=("Arial", 16, "bold")).grid(row=1, column=0, pady=5)
    tk.Label(root, text="קנייה", font=("Arial", 16, "bold")).grid(row=1, column=1, pady=5)

    # Frames for columns
    sale_frame = tk.Frame(root)
    buy_frame = tk.Frame(root)
    sale_frame.grid(row=2, column=0, padx=10, pady=5, sticky="n")
    buy_frame.grid(row=2, column=1, padx=10, pady=5, sticky="n")

    # ===== Sale column =====
    tk.Label(sale_frame, text="מחיר מכירה (₪)").grid(row=0, column=0, sticky="w")
    entry_sale_price = tk.Entry(sale_frame)
    entry_sale_price.grid(row=0, column=1, sticky="e")

    tk.Label(sale_frame, text="עמלת תיווך מכירה (%)").grid(row=1, column=0, sticky="w")
    entry_broker_sale = tk.Entry(sale_frame)
    entry_broker_sale.grid(row=1, column=1, sticky="e")

    tk.Label(sale_frame, text="עמלת עו\"ד מכירה (%)").grid(row=2, column=0, sticky="w")
    entry_lawyer_sale = tk.Entry(sale_frame)
    entry_lawyer_sale.grid(row=2, column=1, sticky="e")

    tk.Label(sale_frame, text="מחיר רכישה מקורי (₪)").grid(row=3, column=0, sticky="w")
    entry_purchase_price = tk.Entry(sale_frame)
    entry_purchase_price.grid(row=3, column=1, sticky="e")

    tk.Label(sale_frame, text="הוצאות מוכרות (₪)").grid(row=4, column=0, sticky="w")
    entry_expenses = tk.Entry(sale_frame)
    entry_expenses.grid(row=4, column=1, sticky="e")

    is_single_home_var = tk.BooleanVar(value=True)
    tk.Checkbutton(sale_frame, text="דירה יחידה", variable=is_single_home_var).grid(row=5, column=0, columnspan=2, sticky="w")

    held_over_18_var = tk.BooleanVar(value=True)
    tk.Checkbutton(sale_frame, text="החזקה מעל 18 חודשים", variable=held_over_18_var).grid(row=6, column=0, columnspan=2, sticky="w")

    tk.Label(sale_frame, text="תקרת פטור (₪)").grid(row=7, column=0, sticky="w")
    entry_exemption_limit = tk.Entry(sale_frame)
    entry_exemption_limit.insert(0, "5,008,000")  # default with commas for readability
    entry_exemption_limit.grid(row=7, column=1, sticky="e")

    # ===== Buy column =====
    tk.Label(buy_frame, text="מחיר קנייה (₪)").grid(row=0, column=0, sticky="w")
    entry_buy_price = tk.Entry(buy_frame)
    entry_buy_price.grid(row=0, column=1, sticky="e")

    tk.Label(buy_frame, text="עמלת תיווך קנייה (%)").grid(row=1, column=0, sticky="w")
    entry_broker_buy = tk.Entry(buy_frame)
    entry_broker_buy.grid(row=1, column=1, sticky="e")

    tk.Label(buy_frame, text="עמלת עו\"ד קנייה (%)").grid(row=2, column=0, sticky="w")
    entry_lawyer_buy = tk.Entry(buy_frame)
    entry_lawyer_buy.grid(row=2, column=1, sticky="e")

    # Calculate button
    tk.Button(root, text="חשב", command=calculate, font=("Arial", 18, "bold")).grid(row=3, column=0, columnspan=2, pady=10)

    # Exit button (right)
    tk.Button(root, text="❌ סיום", command=root.destroy, bg="lightgray").grid(row=4, column=1, sticky="e", pady=10)

    # Save calculation button (left)
    tk.Button(root, text="שמור חישוב", command=save_calculation, bg="lightblue").grid(row=3, column=0, sticky="w", pady=10)

    # Note under save
    tk.Label(root, text="כדי לשמור חישוב נוכחי יש ללחוץ קודם על 'חשב'", font=("Arial", 14), fg="green").grid(row=4, column=0, sticky="w")

    # History controls
    counter_label = tk.Label(root, text="0/10", font=("Arial", 12), fg="green")
    counter_label.grid(row=6, column=0, sticky="w")

    tk.Button(root, text="הצג היסטוריית חישובים", command=show_history, bg="lightyellow").grid(row=5, column=0, sticky="w", pady=5)
    tk.Button(root, text="מחק היסטוריה", command=clear_history, bg="lightpink").grid(row=7, column=0, sticky="w", pady=5)

    # Result frame
    frame_result = tk.Frame(root)
    frame_result.grid(row=6, column=0, columnspan=2, pady=20, sticky="n")

    # Right graphs frame (column 2)
    frame_graphs = tk.Frame(root)
    frame_graphs.grid(row=2, column=2, rowspan=6, padx=10, pady=5, sticky="nsew")
    root.rowconfigure(2, weight=1)
    root.rowconfigure(3, weight=0)
    root.rowconfigure(4, weight=0)
    root.rowconfigure(5, weight=0)
    root.rowconfigure(6, weight=1)
    root.columnconfigure(2, weight=1)

# ==============================
# Main
# ==============================

if __name__ == "__main__":
    create_gui()
    root.mainloop()