import os
import json
from decimal import Decimal
from datetime import date, datetime

os.environ["JAVA_HOME"] = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
os.environ["SPARK_HOME"] = r"C:\Program Files\Spark\spark-4.2.0-bin-hadoop3\spark-4.2.0-bin-hadoop3"
os.environ["HADOOP_HOME"] = r"C:\Program Files\hadoop"
os.environ["PATH"] = r"C:\Program Files\hadoop\bin;" + os.environ.get("PATH", "")

import findspark
findspark.init(os.environ["SPARK_HOME"])

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum, count, countDistinct, avg, round,
    desc, asc, concat_ws, lpad,
    initcap, trim, regexp_replace
)
NORMALIZE_COLUMNS = ["Payment_Method"]
# Exceptions to Title Case (applied after normalising), e.g. brands / acronyms.
LABEL_OVERRIDES = {"Paypal": "PayPal", "Upi": "UPI"}


def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def export_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=json_serial)
    print(f"Exported: {filepath}")

def main():
    spark = (
        SparkSession.builder
        .appName("DashboardJSONExporter")
        .master("local[2]")
        .getOrCreate()
    )

    parquet_path = "D:/Portfolio/Retail Sales Dataset/retail-sales-analysis/clean_sales.parquet"
    print(f"Reading {parquet_path}...")
    df = spark.read.parquet(parquet_path)

    norm_cols = [c for c in NORMALIZE_COLUMNS if c in df.columns]
    for c in norm_cols:
        df = df.withColumn(c, initcap(trim(regexp_replace(col(c), r"\s+", " "))))
    if norm_cols and LABEL_OVERRIDES:
        df = df.replace(LABEL_OVERRIDES, subset=norm_cols)
    total_records = df.count()
    print(f"Loaded {total_records} rows.")

    output_dir = "dashboard_exports"
    os.makedirs(output_dir, exist_ok=True)

  
    kpi_row = df.select(
        round(sum("Sales_Amount"), 2).alias("total_revenue"),
        round(sum("Profit"), 2).alias("total_profit"),
        round(sum("Cost_Amount"), 2).alias("total_cost"),
        countDistinct("Order_ID").alias("total_orders"),
        countDistinct("Transaction_ID").alias("total_transactions"),
        countDistinct("Customer_ID").alias("total_customers"),
        sum("Quantity").alias("total_units_sold"),
        round(avg("Customer_Rating"), 2).alias("average_rating"),
        round(avg("Delivery_Days"), 2).alias("average_delivery_days"),
        round((sum("Is_Returned") / count("*")) * 100, 2).alias("return_rate_pct"),
        round((sum("Has_Discount") / count("*")) * 100, 2).alias("discount_frequency_pct"),
        round((sum("Is_Profitable") / count("*")) * 100, 2).alias("profitable_orders_pct")
    ).collect()[0].asDict()

    import builtins
    kpi_row["overall_profit_margin_pct"] = builtins.round(
        (kpi_row["total_profit"] / kpi_row["total_revenue"]) * 100, 2
    )
    kpi_row["average_order_value"] = builtins.round(
        kpi_row["total_revenue"] / kpi_row["total_orders"], 2
    )
    kpi_row["average_customer_spend"] = builtins.round(
        kpi_row["total_revenue"] / kpi_row["total_customers"], 2
    )

    export_json(kpi_row, os.path.join(output_dir, "kpis_summary.json"))


    monthly_trend = (
        df.withColumn("Year_Month", concat_ws("-", col("Order_Year"), lpad(col("Order_Month"), 2, "0")))
        .groupBy("Order_Year", "Order_Month", "Year_Month")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            countDistinct("Order_ID").alias("orders_count"),
            countDistinct("Customer_ID").alias("customers_count"),
            sum("Quantity").alias("units_sold"),
            round(avg("Customer_Rating"), 2).alias("avg_rating")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .orderBy("Order_Year", "Order_Month")
        .collect()
    )
    monthly_data = [row.asDict() for row in monthly_trend]
    export_json(monthly_data, os.path.join(output_dir, "monthly_sales_trend.json"))

    category_df = (
        df.groupBy("Product_Category")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            sum("Quantity").alias("units_sold"),
            countDistinct("Order_ID").alias("orders_count"),
            round((sum("Is_Returned") / count("*")) * 100, 2).alias("return_rate_pct")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .orderBy(desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in category_df], os.path.join(output_dir, "category_performance.json"))

    subcategory_df = (
        df.groupBy("Product_Category", "Product_Subcategory")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            sum("Quantity").alias("units_sold"),
            round(avg("Unit_Price"), 2).alias("avg_unit_price")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .orderBy("Product_Category", desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in subcategory_df], os.path.join(output_dir, "subcategory_performance.json"))


    regional_df = (
        df.groupBy("Country", "Region")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            countDistinct("Order_ID").alias("orders_count"),
            countDistinct("Customer_ID").alias("customers_count")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .withColumn("aov", round(col("revenue") / col("orders_count"), 2))
        .orderBy("Country", desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in regional_df], os.path.join(output_dir, "regional_performance.json"))

    channel_df = (
        df.groupBy("Sales_Channel")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            countDistinct("Order_ID").alias("orders_count"),
            round(avg("Delivery_Days"), 2).alias("avg_delivery_days")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .withColumn("pct_of_total_revenue", round((col("revenue") / kpi_row["total_revenue"]) * 100, 2))
        .orderBy(desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in channel_df], os.path.join(output_dir, "sales_channel_distribution.json"))

    segment_df = (
        df.groupBy("Customer_Segment")
        .agg(
            countDistinct("Customer_ID").alias("customer_count"),
            countDistinct("Order_ID").alias("orders_count"),
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .withColumn("aov", round(col("revenue") / col("orders_count"), 2))
        .orderBy(desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in segment_df], os.path.join(output_dir, "customer_segments.json"))

    demographics_df = (
        df.groupBy("Age_Group", "Customer_Gender")
        .agg(
            countDistinct("Customer_ID").alias("customer_count"),
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(avg("Customer_Rating"), 2).alias("avg_rating")
        )
        .orderBy("Age_Group", "Customer_Gender")
        .collect()
    )
    export_json([r.asDict() for r in demographics_df], os.path.join(output_dir, "customer_demographics.json"))


    payment_df = (
        df.groupBy("Payment_Method")
        .agg(
            countDistinct("Transaction_ID").alias("transaction_count"),
            round(sum("Sales_Amount"), 2).alias("revenue")
        )
        .withColumn("share_of_transactions_pct", round((col("transaction_count") / kpi_row["total_transactions"]) * 100, 2))
        .orderBy(desc("revenue"))
        .collect()
    )
    export_json([r.asDict() for r in payment_df], os.path.join(output_dir, "payment_methods.json"))


    top_products = (
        df.groupBy("Product_ID", "Product_Name", "Product_Category")
        .agg(
            round(sum("Sales_Amount"), 2).alias("revenue"),
            round(sum("Profit"), 2).alias("profit"),
            sum("Quantity").alias("units_sold"),
            round(avg("Customer_Rating"), 2).alias("avg_rating")
        )
        .withColumn("profit_margin_pct", round((col("profit") / col("revenue")) * 100, 2))
        .orderBy(desc("revenue"))
        .limit(10)
        .collect()
    )
    export_json([r.asDict() for r in top_products], os.path.join(output_dir, "top_10_products.json"))

    return_reasons_df = (
        df.filter(col("Is_Returned") == 1)
        .groupBy("Return_Reason")
        .agg(
            count("*").alias("return_count"),
            round(sum("Sales_Amount"), 2).alias("returned_value")
        )
        .orderBy(desc("return_count"))
        .collect()
    )
    fulfillment_summary = {
        "return_reasons": [r.asDict() for r in return_reasons_df],
        "delivery_speed": [
            r.asDict() for r in df.groupBy("Delivery_Speed_Category").agg(
                count("*").alias("count"),
                round(avg("Delivery_Days"), 2).alias("avg_days")
            ).collect()
        ],
        "shipping_methods": [
            r.asDict() for r in df.groupBy("Shipping_Method").agg(
                count("*").alias("count"),
                round(avg("Delivery_Days"), 2).alias("avg_days"),
                round(sum("Sales_Amount"), 2).alias("revenue")
            ).collect()
        ]
    }
    export_json(fulfillment_summary, os.path.join(output_dir, "fulfillment_and_returns.json"))

    print("\n--- All dashboard parts successfully exported to 'dashboard_exports/' ---")
    spark.stop()

if __name__ == "__main__":
    main()