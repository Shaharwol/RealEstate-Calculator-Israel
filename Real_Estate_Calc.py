import tkinter as tk
from tkinter import ttk
import sys
import os
import re
import math
import json
import webbrowser
import csv
from tkinter import filedialog, messagebox
#import requests
#from bs4 import BeautifulSoup
from typing import List, Tuple, Optional
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams['font.family'] = 'DejaVu Sans'
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def open_gov_site():
    """Opens the official tax simulator."""
    webbrowser.open("https://www.gov.il/he/service/real_eatate_taxsimulator")


def show_current_tax_brackets_window():
    """
    NOTE: Opens a popup window displaying the currently loaded tax brackets.
    This provides transparency to the user.
    """
    brackets_data = load_tax_brackets_from_json()

    # Create popup window
    win = tk.Toplevel(root)
    win.title("מדרגות מס רכישה בשימוש")
    win.geometry("700x500")

    # Title
    tk.Label(win, text="מדרגות המס הטעונות במערכת (2026)", font=("Arial", 14, "bold"), fg="blue").pack(pady=10)

    # Link button
    tk.Button(win, text="בדיקת עדכניות באתר Gov.il 🌐", command=open_gov_site, bg="#e1f5fe").pack(pady=5)

    # Frame for tables (Side by Side)
    container = tk.Frame(win)
    container.pack(fill="both", expand=True, padx=10, pady=10)

    # --- Helper to render a table ---
    def render_table(parent, title, bracket_list):
        frame = tk.LabelFrame(parent, text=title, font=("Arial", 12, "bold"))
        frame.pack(side="left", fill="both", expand=True, padx=5)

        # Headers
        tk.Label(frame, text="מ- (₪)", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=5)
        tk.Label(frame, text="עד- (₪)", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5)
        tk.Label(frame, text="מס (%)", font=("Arial", 10, "bold")).grid(row=0, column=2, padx=5)

        for i, (low, high, rate) in enumerate(bracket_list):
            high_str = "∞" if high == float("inf") else f"{high:,.0f}"
            tk.Label(frame, text=f"{low:,.0f}").grid(row=i + 1, column=0)
            tk.Label(frame, text=high_str).grid(row=i + 1, column=1)
            tk.Label(frame, text=f"{rate * 100:.1f}%").grid(row=i + 1, column=2)

    # Render Single Home Brackets
    render_table(container, "דירה יחידה", brackets_data.get("single_home", []))

    # Render Additional Home Brackets
    render_table(container, "דירה נוספת (להשקעה)", brackets_data.get("additional_home", []))

    # Close button
    tk.Button(win, text="סגור", command=win.destroy).pack(pady=10)


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

is_single_home_var = None           # For Sale (Capital Gains Exemption)
is_single_home_purchase_var = None  # For Purchase (Tax Brackets Logic)
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
# Tax brackets handling (JSON Config)
# ==============================

TAX_FILE_NAME = "tax_brackets.json"

# Fallback defaults (Hardcoded 2026 values) in case JSON is missing/corrupt
DEFAULT_BRACKETS = {
    "single_home": [
        (0, 1978745, 0.0),
        (1978745, 2347040, 0.035),
        (2347040, 6055070, 0.05),
        (6055070, 20183565, 0.08),
        (20183565, float("inf"), 0.10),
    ],
    "additional_home": [
        (0, 6055070, 0.08),
        (6055070, float("inf"), 0.10),
    ]
}


def load_tax_brackets_from_json() -> dict:
    """
    Loads tax brackets from an external JSON file.
    Returns a dictionary containing 'single_home' and 'additional_home' lists.
    Falls back to hardcoded defaults if file reading fails.
    """
    path = resource_path(TAX_FILE_NAME)

    try:
        if not os.path.exists(path):
            print(f"DEBUG: JSON file not found at {path}. Using defaults.")
            return DEFAULT_BRACKETS

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Parse and convert "inf" strings to float("inf")
        parsed_brackets = {}
        for key in ["single_home", "additional_home"]:
            raw_list = data.get(key, [])
            clean_list = []
            for low, high, rate in raw_list:
                # Handle "inf" from JSON
                if isinstance(high, str) and high.lower() == "inf":
                    high = float("inf")
                clean_list.append((low, high, rate))
            parsed_brackets[key] = clean_list

        return parsed_brackets

    except (json.JSONDecodeError, ValueError, Exception) as e:
        print(f"ERROR: Failed to load/parse JSON ({e}). Using defaults.")
        return DEFAULT_BRACKETS


def get_current_brackets(is_single_home: bool) -> List[Tuple[int, float, float]]:
    """
    Router function to get the correct list based on user selection.
    """
    all_brackets = load_tax_brackets_from_json()

    if is_single_home:
        return all_brackets.get("single_home", DEFAULT_BRACKETS["single_home"])
    else:
        return all_brackets.get("additional_home", DEFAULT_BRACKETS["additional_home"])

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


def calculate_purchase_tax(price: float, brackets) -> float:
    tax = 0.0
    for low, high, rate in brackets:
        span_high = min(high, price)
        if span_high <= low:
            continue
        taxable_part = span_high - low
        tax += taxable_part * rate
    return tax

def get_purchase_tax_breakdown(price: float, brackets):
    breakdown = []

    for i, (low, high, rate) in enumerate(brackets, start=1):
        span_high = min(high, price)
        taxable = max(0, span_high - low)
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


def export_to_csv() -> None:
    """
    NOTE: Export the saved history to a CSV file selected by the user.
    Handles Hebrew encoding for Excel compatibility.
    """
    if not saved_calculations:
        messagebox.showwarning("אין נתונים", "אין היסטוריית חישובים לייצוא.")
        return

    # Ask user where to save
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        title="שמור דוח כקובץ CSV"
    )

    if not file_path:
        return  # User cancelled

    # Define Hebrew headers mapping
    # Maps internal keys to Hebrew column names
    field_mapping = {
        "sale_price": "מחיר מכירה",
        "broker_fee_sale_percent": "תיווך מכירה (%)",
        "lawyer_fee_sale_percent": "עו\"ד מכירה (%)",
        "tax_sale": "מס שבח (לתשלום)",
        "total_sale": "סה\"כ נטו ממכירה",
        "buy_price": "מחיר קנייה",
        "broker_fee_buy_percent": "תיווך קנייה (%)",
        "lawyer_fee_buy_percent": "עו\"ד קנייה (%)",
        "tax_buy": "מס רכישה (לתשלום)",
        "total_buy": "סה\"כ עלות קנייה",
        "difference": "הפרש נטו",
        "status": "סטטוס"
    }

    try:
        with open(file_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=field_mapping.values())
            writer.writeheader()

            for calc in saved_calculations:
                # Create a row with Hebrew keys based on the mapping
                row = {heb_key: calc.get(eng_key, "") for eng_key, heb_key in field_mapping.items()}
                writer.writerow(row)

        messagebox.showinfo("הצלחה", "הקובץ נשמר בהצלחה!")

    except Exception as e:
        messagebox.showerror("שגיאה", f"שגיאה בשמירת הקובץ:\n{e}")
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

    # No network calls needed. Loading JSON happens instantly.

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

        # Logic Flags
        is_single_home_sale = is_single_home_var.get()  # Checkbox for Sale
        is_single_home_buy = is_single_home_purchase_var.get()  # Checkbox for Purchase (NEW)
        held_over_18_months = held_over_18_var.get()

        # Taxes
        # UPDATE: Fetch brackets based on the PURCHASE checkbox status
        # If checked (True) -> Single home brackets (0% start)
        # If unchecked (False) -> Additional home brackets (8% start)
        brackets = get_current_brackets(is_single_home_buy)

        tax_sale = calculate_capital_gain_tax(
            sale_price, purchase_price, expenses, is_single_home_sale, held_over_18_months, exemption_limit
        )
        tax_buy = calculate_purchase_tax(buy_price, brackets)




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
        breakdown = get_purchase_tax_breakdown(buy_price, brackets)

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
    global is_single_home_purchase_var

    # Root and basic options
    root = tk.Tk()
    root.title("מחשבון נדל\"ן (מערכות)")
    # === תיקון 1: קביעת גודל חלון התחלתי גדול יותר ===
    root.geometry("1400x900")
    root.option_add("*Font", "Arial 16")

    # Layout: 3 columns (sale, buy, graphs)
    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)
    root.columnconfigure(2, weight=1)

    # --- IMAGES (Row 0) ---
    try:
        sell_img = tk.PhotoImage(file=resource_path("SellHouse.png"))
        buy_img = tk.PhotoImage(file=resource_path("BuyHouse.png"))
        tk.Label(root, image=sell_img).grid(row=0, column=0, pady=5)
        tk.Label(root, image=buy_img).grid(row=0, column=1, pady=5)
        root.sell_img = sell_img
        root.buy_img = buy_img
    except Exception:
        pass

    # --- HEADERS (Row 1) ---
    tk.Label(root, text="מכירה", font=("Arial", 16, "bold")).grid(row=1, column=0, pady=5)
    tk.Label(root, text="קנייה", font=("Arial", 16, "bold")).grid(row=1, column=1, pady=5)

    # --- INPUT FRAMES (Row 2) ---
    sale_frame = tk.Frame(root)
    buy_frame = tk.Frame(root)
    sale_frame.grid(row=2, column=0, padx=10, pady=5, sticky="n")
    buy_frame.grid(row=2, column=1, padx=10, pady=5, sticky="n")

    # [Sale Inputs]
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
    tk.Checkbutton(sale_frame, text="דירה יחידה (פטור שבח)", variable=is_single_home_var).grid(row=5, column=0,
                                                                                               columnspan=2, sticky="w")

    held_over_18_var = tk.BooleanVar(value=True)
    tk.Checkbutton(sale_frame, text="החזקה מעל 18 חודשים", variable=held_over_18_var).grid(row=6, column=0,
                                                                                           columnspan=2, sticky="w")

    tk.Label(sale_frame, text="תקרת פטור (₪)").grid(row=7, column=0, sticky="w")
    entry_exemption_limit = tk.Entry(sale_frame)
    entry_exemption_limit.insert(0, "5,008,000")
    entry_exemption_limit.grid(row=7, column=1, sticky="e")

    # [Buy Inputs]
    tk.Label(buy_frame, text="מחיר קנייה (₪)").grid(row=0, column=0, sticky="w")
    entry_buy_price = tk.Entry(buy_frame)
    entry_buy_price.grid(row=0, column=1, sticky="e")

    tk.Label(buy_frame, text="עמלת תיווך קנייה (%)").grid(row=1, column=0, sticky="w")
    entry_broker_buy = tk.Entry(buy_frame)
    entry_broker_buy.grid(row=1, column=1, sticky="e")

    tk.Label(buy_frame, text="עמלת עו\"ד קנייה (%)").grid(row=2, column=0, sticky="w")
    entry_lawyer_buy = tk.Entry(buy_frame)
    entry_lawyer_buy.grid(row=2, column=1, sticky="e")

    is_single_home_purchase_var = tk.BooleanVar(value=True)
    tk.Checkbutton(buy_frame, text="דירה יחידה (לחישוב מס רכישה)", variable=is_single_home_purchase_var).grid(row=3,
                                                                                                              column=0,
                                                                                                              columnspan=2,
                                                                                                              sticky="w")

    # --- BUTTONS (Rows 3, 4) ---
    tk.Button(root, text="חשב", command=calculate, font=("Arial", 18, "bold"), bg="#e0f7fa").grid(row=3, column=0,
                                                                                                  columnspan=2, pady=10)

    tk.Button(root, text="שמור חישוב", command=save_calculation, bg="lightblue").grid(row=4, column=0, sticky="w",
                                                                                      padx=10)
    tk.Label(root, text="(יש ללחוץ 'חשב' לפני השמירה)", font=("Arial", 10), fg="gray").grid(row=4, column=0, sticky="e",
                                                                                            padx=50)
    tk.Button(root, text="❌ סיום", command=root.destroy, bg="lightgray").grid(row=4, column=1, sticky="e", padx=10)

    # --- Layout Separation (Rows 5-10) ---

    # עמודה 0 (שמאל): כפתורי היסטוריה
    history_frame = tk.Frame(root)
    history_frame.grid(row=5, column=0, rowspan=5, sticky="nw", padx=10, pady=20)

    counter_label = tk.Label(history_frame, text="0/10", font=("Arial", 12), fg="green")
    counter_label.pack(anchor="w", pady=2)
    tk.Button(history_frame, text="הצג היסטוריה 📜", command=show_history, bg="lightyellow", width=20).pack(anchor="w",
                                                                                                           pady=5)
    tk.Button(history_frame, text="מחק היסטוריה 🗑️", command=clear_history, bg="lightpink", width=20).pack(anchor="w",
                                                                                                           pady=5)
    tk.Button(history_frame, text="ייצוא ל-CSV 💾", command=export_to_csv, bg="#dcedc8", width=20).pack(anchor="w",
                                                                                                       pady=5)

    # עמודה 1 (מרכז/ימין): תוצאות החישוב
    # === תיקון 2: העלאת התוצאות לשורה 5 בעמודה נפרדת ===
    frame_result = tk.Frame(root, bd=2, relief="groove")
    frame_result.grid(row=5, column=1, rowspan=10, sticky="n", padx=10, pady=10)

    # --- GRAPHS (Row 2, spanning down) ---
    frame_graphs = tk.Frame(root)
    frame_graphs.grid(row=2, column=2, rowspan=15, padx=10, pady=5, sticky="nsew")

    # Weights
    root.rowconfigure(2, weight=1)
    root.rowconfigure(5, weight=1)
    root.columnconfigure(2, weight=1)

    # --- FOOTER (Row 20 - BOTTOM) ---
    footer_frame = tk.Frame(root, bd=1, relief="sunken", bg="#e0e0e0")
    footer_frame.grid(row=20, column=0, columnspan=3, sticky="ew", padx=0, pady=(20, 0))

    tk.Label(footer_frame, text=" המערכת טענה מדרגות מס מקובץ מקומי.",
             bg="#e0e0e0", fg="#333333", font=("Arial", 10)).pack(side="right", padx=10)

    tk.Button(footer_frame, text="⚙️ הגדרות מדרגות מס",
              command=show_current_tax_brackets_window,
              font=("Arial", 9, "bold"), bg="white", bd=1).pack(side="left", padx=5, pady=2)

    root.rowconfigure(20, weight=0)


# ==============================
# Main
# ==============================

if __name__ == "__main__":
    create_gui()
    root.mainloop()