from functools import lru_cache
from pathlib import Path
from typing import Optional
import json
import os
import re
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

try:
    import pandas as pd
except ImportError:  # filters are disabled, the dashboard still works unfiltered
    pd = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dashboard_exports"
STATIC_DIR = BASE_DIR / "static"

# Same parquet that dashboard.py reads. Override with the SALES_PARQUET env var.
PARQUET_PATH = Path(os.environ.get("SALES_PARQUET", BASE_DIR / "clean_sales.parquet"))

app = FastAPI(
    title="PySpark Sales Analytics Dashboard",
    description="FastAPI dashboard backend serving PySpark-generated analytical results.",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


FILES = {
    "kpis": "kpis_summary.json",
    "monthly": "monthly_sales_trend.json",
    "categories": "category_performance.json",
    "subcategories": "subcategory_performance.json",
    "regional": "regional_performance.json",
    "channels": "sales_channel_distribution.json",
    "segments": "customer_segments.json",
    "demographics": "customer_demographics.json",
    "payments": "payment_methods.json",
    "products": "top_10_products.json",
    "fulfillment": "fulfillment_and_returns.json",
}


def load_json(filename: str):
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard data file not found: {filename}. "
                   "Run the PySpark exporter first."
        )
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {filename}") from exc


# ─── Filtered analytics (pandas over the same parquet) ──────────────────────
#
# Unfiltered requests are still served from the PySpark JSON exports above.
# When a filter is active, the data is re-aggregated here so that distinct
# counts (orders, customers) stay correct.

NEEDED_COLUMNS = [
    "Order_ID", "Transaction_ID", "Customer_ID", "Order_Year", "Order_Month",
    "Sales_Amount", "Profit", "Cost_Amount", "Quantity", "Unit_Price",
    "Customer_Rating", "Delivery_Days", "Is_Returned", "Has_Discount",
    "Is_Profitable", "Product_ID", "Product_Name", "Product_Category",
    "Product_Subcategory", "Country", "Region", "Sales_Channel",
    "Customer_Segment", "Age_Group", "Customer_Gender", "Payment_Method",
    "Return_Reason", "Delivery_Speed_Category", "Shipping_Method",
]

# Keep these two settings in sync with dashboard.py so filtered and unfiltered
# views group labels identically.
NORMALIZE_COLUMNS = ["Payment_Method"]
LABEL_OVERRIDES = {"Paypal": "PayPal", "Upi": "UPI"}


def _normalize_label(value):
    """Same rule as Spark's initcap(trim(...)): collapse spaces, Capitalize Each Word."""
    if not isinstance(value, str):
        return value
    return " ".join(word.capitalize() for word in value.split())


def _normalize_labels(series):
    mapping = {v: _normalize_label(v) for v in series.dropna().unique()}
    out = series.map(mapping)
    return out.replace(LABEL_OVERRIDES) if LABEL_OVERRIDES else out


_df = None
_df_loaded = False
_df_error = None
_df_lock = threading.Lock()


def get_df():
    """Load the parquet once (lazily). Returns None if filtering is unavailable."""
    global _df, _df_loaded, _df_error
    if _df_loaded:
        return _df
    with _df_lock:
        if _df_loaded:
            return _df
        try:
            if pd is None:
                raise RuntimeError("pandas is not installed (pip install pandas pyarrow)")
            if not PARQUET_PATH.exists():
                raise FileNotFoundError(f"{PARQUET_PATH} not found")
            d = pd.read_parquet(PARQUET_PATH, columns=NEEDED_COLUMNS)
            for c in NORMALIZE_COLUMNS:
                if c in d.columns:
                    d[c] = _normalize_labels(d[c])
            d["Year_Month"] = (
                d["Order_Year"].astype(int).astype(str) + "-"
                + d["Order_Month"].astype(int).astype(str).str.zfill(2)
            )
            _df = d
            print(f"[filters] Loaded {len(d):,} rows from {PARQUET_PATH}")
        except Exception as exc:  # noqa: BLE001 - we want to degrade gracefully
            _df_error = str(exc)
            print(f"[filters] Disabled: {_df_error}")
        _df_loaded = True
    return _df


def _records(frame):
    # to_json converts numpy types and NaN -> null safely
    return json.loads(frame.to_json(orient="records"))


def _mean(series):
    if len(series) == 0:
        return 0.0
    value = series.mean()
    return 0.0 if pd.isna(value) else float(value)


def _pct(part, whole):
    return round(float(part) / float(whole) * 100, 2) if whole else 0.0


def _margin(profit, revenue):
    return (profit / revenue.replace(0, float("nan")) * 100).fillna(0).round(2)


def _round(frame, cols):
    frame[cols] = frame[cols].round(2)
    return frame


def compute_kpis(d):
    n = len(d)
    revenue = float(d["Sales_Amount"].sum())
    profit = float(d["Profit"].sum())
    orders = int(d["Order_ID"].nunique())
    customers = int(d["Customer_ID"].nunique())
    return {
        "total_revenue": round(revenue, 2),
        "total_profit": round(profit, 2),
        "total_cost": round(float(d["Cost_Amount"].sum()), 2),
        "total_orders": orders,
        "total_transactions": int(d["Transaction_ID"].nunique()),
        "total_customers": customers,
        "total_units_sold": int(d["Quantity"].sum()),
        "average_rating": round(_mean(d["Customer_Rating"]), 2),
        "average_delivery_days": round(_mean(d["Delivery_Days"]), 2),
        "return_rate_pct": _pct(d["Is_Returned"].sum(), n),
        "discount_frequency_pct": _pct(d["Has_Discount"].sum(), n),
        "profitable_orders_pct": _pct(d["Is_Profitable"].sum(), n),
        "overall_profit_margin_pct": _pct(profit, revenue),
        "average_order_value": round(revenue / orders, 2) if orders else 0.0,
        "average_customer_spend": round(revenue / customers, 2) if customers else 0.0,
    }


def compute_monthly(d):
    g = d.groupby(["Order_Year", "Order_Month", "Year_Month"], as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        orders_count=("Order_ID", "nunique"),
        units_sold=("Quantity", "sum"),
        avg_rating=("Customer_Rating", "mean"),
        customers_count=("Customer_ID", "nunique"),
    )
    _round(g, ["revenue", "profit", "avg_rating"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    return _records(g.sort_values(["Order_Year", "Order_Month"]))


def compute_categories(d):
    g = d.groupby("Product_Category", as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        units_sold=("Quantity", "sum"),
        orders_count=("Order_ID", "nunique"),
        _returned=("Is_Returned", "sum"),
        _rows=("Is_Returned", "size"),
    )
    g["return_rate_pct"] = (g["_returned"] / g["_rows"] * 100).round(2)
    g = g.drop(columns=["_returned", "_rows"])
    _round(g, ["revenue", "profit"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    return _records(g.sort_values("revenue", ascending=False))


def compute_subcategories(d):
    g = d.groupby(["Product_Category", "Product_Subcategory"], as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        units_sold=("Quantity", "sum"),
        avg_unit_price=("Unit_Price", "mean"),
    )
    _round(g, ["revenue", "profit", "avg_unit_price"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    return _records(g.sort_values(["Product_Category", "revenue"], ascending=[True, False]))


def compute_regional(d):
    g = d.groupby(["Country", "Region"], as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        orders_count=("Order_ID", "nunique"),
        customers_count=("Customer_ID", "nunique"),
    )
    _round(g, ["revenue", "profit"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    g["aov"] = (g["revenue"] / g["orders_count"].replace(0, float("nan"))).fillna(0).round(2)
    return _records(g.sort_values(["Country", "revenue"], ascending=[True, False]))


def compute_channels(d):
    g = d.groupby("Sales_Channel", as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        orders_count=("Order_ID", "nunique"),
        avg_delivery_days=("Delivery_Days", "mean"),
    )
    total = g["revenue"].sum()
    g["pct_of_total_revenue"] = (g["revenue"] / total * 100).round(2) if total else 0.0
    _round(g, ["revenue", "profit", "avg_delivery_days"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    return _records(g.sort_values("revenue", ascending=False))


def compute_segments(d):
    g = d.groupby("Customer_Segment", as_index=False).agg(
        customer_count=("Customer_ID", "nunique"),
        orders_count=("Order_ID", "nunique"),
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
    )
    _round(g, ["revenue", "profit"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    g["aov"] = (g["revenue"] / g["orders_count"].replace(0, float("nan"))).fillna(0).round(2)
    return _records(g.sort_values("revenue", ascending=False))


def compute_demographics(d):
    g = d.groupby(["Age_Group", "Customer_Gender"], as_index=False).agg(
        customer_count=("Customer_ID", "nunique"),
        revenue=("Sales_Amount", "sum"),
        avg_rating=("Customer_Rating", "mean"),
    )
    _round(g, ["revenue", "avg_rating"])
    return _records(g.sort_values(["Age_Group", "Customer_Gender"]))


def compute_payments(d):
    g = d.groupby("Payment_Method", as_index=False).agg(
        transaction_count=("Transaction_ID", "nunique"),
        revenue=("Sales_Amount", "sum"),
    )
    total = int(d["Transaction_ID"].nunique())
    g["share_of_transactions_pct"] = (g["transaction_count"] / total * 100).round(2) if total else 0.0
    _round(g, ["revenue"])
    return _records(g.sort_values("revenue", ascending=False))


def compute_products(d):
    g = d.groupby(["Product_ID", "Product_Name", "Product_Category"], as_index=False).agg(
        revenue=("Sales_Amount", "sum"),
        profit=("Profit", "sum"),
        units_sold=("Quantity", "sum"),
        avg_rating=("Customer_Rating", "mean"),
    )
    _round(g, ["revenue", "profit", "avg_rating"])
    g["profit_margin_pct"] = _margin(g["profit"], g["revenue"])
    return _records(g.sort_values("revenue", ascending=False).head(10))


def compute_fulfillment(d):
    returned = d[d["Is_Returned"] == 1]
    reasons = returned.groupby("Return_Reason", as_index=False).agg(
        return_count=("Return_Reason", "size"),
        returned_value=("Sales_Amount", "sum"),
    )
    _round(reasons, ["returned_value"])

    speed = d.groupby("Delivery_Speed_Category", as_index=False).agg(
        count=("Delivery_Days", "size"),
        avg_days=("Delivery_Days", "mean"),
    )
    _round(speed, ["avg_days"])

    shipping = d.groupby("Shipping_Method", as_index=False).agg(
        count=("Delivery_Days", "size"),
        avg_days=("Delivery_Days", "mean"),
        revenue=("Sales_Amount", "sum"),
    )
    _round(shipping, ["avg_days", "revenue"])

    return {
        "return_reasons": _records(reasons.sort_values("return_count", ascending=False)),
        "delivery_speed": _records(speed),
        "shipping_methods": _records(shipping),
    }


BUILDERS = {
    "kpis": compute_kpis,
    "monthly": compute_monthly,
    "categories": compute_categories,
    "subcategories": compute_subcategories,
    "regional": compute_regional,
    "channels": compute_channels,
    "segments": compute_segments,
    "demographics": compute_demographics,
    "payments": compute_payments,
    "products": compute_products,
    "fulfillment": compute_fulfillment,
}

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _subset(d, start, end, category, channel):
    mask = pd.Series(True, index=d.index)
    if start:
        mask &= d["Year_Month"] >= start
    if end:
        mask &= d["Year_Month"] <= end
    if category:
        mask &= d["Product_Category"] == category
    if channel:
        mask &= d["Sales_Channel"] == channel
    return d[mask]


def _previous_window(start, end, months):
    """The equally long window right before [start, end], or None if it would
    run off the start of the data (an incomplete window gives misleading trends)."""
    if not start and not end:
        return None
    s = pd.Period(start or months[0], "M")
    e = pd.Period(end or months[-1], "M")
    length = (e - s).n + 1
    prev_end = s - 1
    prev_start = prev_end - (length - 1)
    if prev_start < pd.Period(months[0], "M"):
        return None
    return str(prev_start), str(prev_end)


@lru_cache(maxsize=256)
def build(name, start, end, category, channel):
    d = get_df()

    # The category/channel charts keep showing every category/channel (so you
    # can compare and click another one); the selection is highlighted instead.
    own_category = None if name == "categories" else category
    own_channel = None if name == "channels" else channel
    result = BUILDERS[name](_subset(d, start, end, own_category, own_channel))

    if name == "kpis":
        window = _previous_window(start, end, tuple(get_meta()["months"]))
        if window:
            prev = compute_kpis(_subset(d, window[0], window[1], category, channel))
            result["previous"] = {
                "total_revenue": prev["total_revenue"],
                "total_profit": prev["total_profit"],
                "total_orders": prev["total_orders"],
                "total_customers": prev["total_customers"],
                "range": list(window),
            }
    return result


@lru_cache(maxsize=1)
def get_meta():
    d = get_df()
    return {
        "enabled": True,
        "months": sorted(d["Year_Month"].unique().tolist()),
        "categories": sorted(d["Product_Category"].dropna().unique().tolist()),
        "channels": sorted(d["Sales_Channel"].dropna().unique().tolist()),
    }


def _clean_month(value, label):
    if value is None or value == "":
        return None
    if not MONTH_RE.match(value):
        raise HTTPException(status_code=400, detail=f"'{label}' must look like YYYY-MM")
    return value


def _clean_text(value):
    value = (value or "").strip()
    return value or None


# ─── Routes ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def dashboard():
    html_path = STATIC_DIR / "index.html"
    return html_path.read_text(encoding="utf-8")


# NOTE: must be declared before "/api/{dataset_name}" so it isn't swallowed by it.
@app.get("/api/filters")
def get_filters():
    if get_df() is None:
        return {"enabled": False, "reason": _df_error}
    return get_meta()


@app.get("/api/{dataset_name}")
def get_dataset(
    dataset_name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    category: Optional[str] = None,
    channel: Optional[str] = None,
):
    filename = FILES.get(dataset_name)
    if not filename:
        raise HTTPException(status_code=404, detail="Unknown dashboard dataset")

    start = _clean_month(start, "start")
    end = _clean_month(end, "end")
    category = _clean_text(category)
    channel = _clean_text(channel)

    if start and end and start > end:
        raise HTTPException(status_code=400, detail="'start' must not be after 'end'")

    # No filters -> serve the PySpark export exactly as before.
    if not (start or end or category or channel):
        return load_json(filename)

    if get_df() is None:
        raise HTTPException(status_code=503, detail=f"Filtering unavailable: {_df_error}")
    return build(dataset_name, start, end, category, channel)


@app.get("/health")
def health():
    return {"status": "ok", "message": "FastAPI dashboard is running"}

  

