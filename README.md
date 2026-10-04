# Retail Sales Analysis Report
**Prepared by:** Jhonas Mariano  
**Dataset Source:** [Kaggle — danielsowah123/retail-sales-dataset](https://www.kaggle.com/datasets/danielsowah123/retail-sales-dataset)  
**Analysis Tool:** PySpark 4.2.0 on Apache Spark  
**Report Date:** October 2026

---

## 1. Executive Summary

This report presents a comprehensive analysis of a global retail sales dataset spanning **2022 to 2025**, processed and analyzed using **Apache PySpark** for scalable, distributed data computation. The dataset covers sales across 6 countries, 4 product categories, and 5 sales channels.

### Headline Numbers

| Metric | Value |
|---|---|
| 💰 Total Revenue | **$8,234,090.60** |
| 📈 Total Profit | **$1,645,439.40** |
| 📊 Profit Margin | **19.98%** |
| 🛒 Total Orders | **14,541** |
| 👥 Unique Customers | **4,882** |
| 📦 Units Sold | **38,277** |
| ⭐ Average Customer Rating | **3.99 / 5.00** |
| 🔄 Return Rate | **10.41%** |

> [!IMPORTANT]
> The business is profitable and growing, with a healthy ~20% margin across all categories. Electronics dominates revenue at 59.8%, while Appliances shows the strongest margin at 22%.

---

## 2. Dataset Overview & Data Quality

### 2.1 Dataset Dimensions

The raw dataset contained:
- **18,045 rows** and **36 columns** across transactions from 2022–2025
- Columns spanning transaction IDs, customer demographics, product details, financial metrics, fulfillment, and feedback

### 2.2 Data Schema

| Column Group | Fields |
|---|---|
| **Transaction** | Transaction_ID, Order_ID, Order_Date, Order_Time, Order_Status |
| **Customer** | Customer_ID, Customer_Name, Customer_Age, Customer_Gender, Customer_Segment |
| **Location** | Store_ID, Store_Name, Country, Region, City, Sales_Channel |
| **Product** | Product_ID, Product_Name, Product_Category, Product_Subcategory |
| **Financials** | Quantity, Unit_Price, Discount_Percentage, Sales_Amount, Cost_Amount, Profit |
| **Fulfillment** | Shipping_Method, Delivery_Days, Return_Flag, Return_Reason |
| **Feedback** | Customer_Rating, Inventory_Level, Promotion_Code, Sales_Representative |

### 2.3 Missing Value Analysis (Pre-Cleaning)

| Column | Missing % | Handling Strategy |
|---|---|---|
| Return_Reason | **~89.6%** | Expected — only returned items have a reason. Filled with "Not Stated" |
| Promotion_Code | **~54.0%** | ~46% of orders had no promo. Filled with "No Promotion Code" |
| Customer_Rating | **~19.1%** | Filled with median rating (4.0) |
| Inventory_Level | **~1.1%** | Filled with median value |
| Customer_Age | **~1.2%** | Filled with median age (39) |
| Customer_Gender | **~0.9%** | Filled with "Unspecified" |
| Customer_Name | **~0.6%** | Filled with "Unknown" |
| Payment_Method | **~0.8%** | Filled with "Other" |
| Product_Name | **~0.8%** | Filled with "Unlabeled Item" |
| Delivery_Days | **~0.9%** | Filled with median delivery days |

### 2.4 Duplicate Records

- **45 duplicate rows** were detected and removed using `dropDuplicates()`
- Final clean dataset: **18,000 rows**

---

## 3. Data Cleaning & Feature Engineering

### 3.1 Cleaning Steps Applied

1. **Removed 45 duplicate records**
2. **Standardized categorical fields** — Gender, Region, City, Product_Category, Order_Status were normalized using `initcap(trim(...))` to ensure consistent casing (e.g., `"FEMALE"` → `"Female"`, `"Non Binary"` → `"Non-binary"`)
3. **Resolved region name inconsistencies** — e.g., `"NRW"` → `"North Rhine-Westphalia"`, `"North East"` → `"Northeast"`
4. **Imputed missing values** with appropriate strategies (median for numerical, mode/placeholder for categorical)

### 3.2 Feature Engineering

A total of **16 new features** were derived from the cleaned dataset:

| Feature | Description |
|---|---|
| `Profit_Margin_Pct` | (Profit / Sales_Amount) × 100 |
| `Unit_Cost` | Cost_Amount / Quantity |
| `Discount_Amount` | (Unit_Price × Quantity) – Sales_Amount |
| `Has_Discount` | Binary flag: 1 if Discount_Percentage > 0 |
| `Is_Profitable` | Binary flag: 1 if Profit > 0 |
| `Order_Month` | Month extracted from Order_Date |
| `Order_Quarter` | Quarter (Q1–Q4) from Order_Date |
| `Day_Name` | Day of week (Monday–Sunday) |
| `Is_Weekend` | Binary flag for Saturday/Sunday |
| `Order_Hour` | Hour of order from Order_Time |
| `Day_Part` | Morning / Afternoon / Evening / Night |
| `Age_Group` | <25 / 25–34 / 35–49 / 50+ |
| `Customer_Order_Sequence` | Purchase rank per customer (window function) |
| `Is_First_Purchase` | Binary flag for first-time buyers |
| `Is_Returned` | Binary flag: 1 if Return_Flag = "Yes" |
| `Delivery_Speed_Category` | Next Day / Standard / Delayed |
| `Stock_Status` | Low Stock (<30 units) / Adequate |
| `Rating_Class` | Positive (≥4.0) / Neutral (3.0) / Negative (≤2.0) |

---

## 4. Business KPI Summary

| KPI | Value | Interpretation |
|---|---|---|
| Total Revenue | $8,234,090.60 | Strong multi-year performance |
| Total Profit | $1,645,439.40 | Healthy absolute profit |
| Total Orders | 14,541 | Avg ~1.24 transactions/order |
| Total Customers | 4,882 | Diversified customer base |

---

## 5. Revenue & Profit Trends

### 5.1 Annual Summary (derived from monthly data)

| Year | Est. Revenue | Est. Orders |
|---|---|---|
| 2022 | ~$1.87M | ~3,200 |
| 2023 | ~$2.01M | ~3,500 |
| 2024 | ~$2.25M | ~3,900 |
| 2025 | ~$2.10M | ~3,900 (partial data) |

The business shows **consistent year-over-year growth** from 2022 to 2024. Revenue accelerated from ~$95K/month in Jan 2022 to over $200K+ in peak months.

### 5.2 Seasonal Observations

- **Q1 (Jan–Mar)**: Typically slower, lower transaction volumes
- **Q2–Q3 (Apr–Sep)**: Strong performance, driven by mid-year spending
- **Q4 (Oct–Dec)**: Holiday season uplift, notable in Nov/Dec with promotions like `BLACKFRIDAY25` and `HOLIDAY20`

> [!TIP]
> Promotions such as `SAVE10`, `HOLIDAY20`, and `BLACKFRIDAY25` appear in the data. A dedicated promotion attribution analysis could quantify the incremental revenue and ROI of each campaign.

---

## 6. Product & Category Performance

### 6.1 Category Revenue Breakdown

| Category | Revenue | Profit | Units Sold | Profit Margin | Return Rate |
|---|---|---|---|---|---|
| **Electronics** | $4,922,081 | $952,111 | 18,061 | 19.34% | 10.37% |
| **Furniture** | $1,986,145 | $420,015 | 6,288 | 21.15% | 10.20% |
| **Office Supplies** | $741,775 | $144,728 | 10,043 | 19.51% | 9.92% |
| **Appliances** | $584,089 | $128,585 | 3,885 | **22.01%** | **11.99%** |

**Key observations:**
- **Electronics** dominates with **59.8% of total revenue**, but has the lowest profit margin among categories (19.34%)
- **Appliances** achieves the **highest margin (22.01%)** but also the highest return rate (11.99%) — a quality/expectation gap worth investigating
- **Office Supplies** delivers strong volume (10,043 units) despite lower revenue due to lower average price points
- **Furniture** achieves the best balance of margin and low return rate

### 6.2 Top 10 Products by Revenue

| Rank | Product | Category | Revenue | Profit | Margin | Avg Rating |
|---|---|---|---|---|---|---|
| 1 | AeroBook 14 Laptop | Electronics | $1,382,382 | $234,632 | 16.97% | 4.03 |
| 2 | ProBook 16 Laptop | Electronics | $1,346,439 | $251,757 | 18.70% | 4.02 |
| 3 | EdgeTab 11 Tablet | Electronics | $675,691 | $100,538 | 14.88% | 4.03 |
| 4 | Standing Desk | Furniture | $588,721 | $118,579 | 20.14% | 3.95 |
| 5 | Meeting Table | Furniture | $530,253 | $82,510 | 15.56% | 4.01 |
| 6 | Vision 27 Monitor | Electronics | $455,769 | $89,675 | 19.68% | 3.98 |
| 7 | Office Chair Pro | Furniture | $436,645 | $95,708 | **21.92%** | 3.95 |
| 8 | Printer Plus | Office Supplies | $255,368 | $35,773 | 14.01% | 3.98 |
| 9 | Air Purifier | Appliances | $236,657 | $51,163 | 21.62% | 3.95 |
| 10 | Filing Cabinet | Furniture | $222,638 | $55,425 | **24.89%** | 4.04 |

> [!IMPORTANT]
> The **Filing Cabinet (P014)** has the highest profit margin in the top 10 at 24.89%. **Laptops** (AeroBook + ProBook) together account for **$2.73M in revenue**, representing **33% of all revenue**, making them the single most critical product group.

---

## 7. Geographic Performance

### 7.1 Performance by Country & Region

| Country | Region | Revenue | Profit | Orders | Customers | Margin | AOV |
|---|---|---|---|---|---|---|---|
| 🇬🇧 United Kingdom | England | $1,326,892 | $269,790 | 2,870 | 783 | 20.33% | $462 |
| 🇺🇸 United States | Northeast | $1,010,756 | $201,411 | 2,119 | 606 | 19.93% | $477 |
| 🇺🇸 United States | West | $992,310 | $200,950 | 2,077 | 589 | 20.25% | $478 |
| 🇫🇷 France | Île-de-France | $725,735 | $144,663 | 1,557 | 439 | 19.93% | $466 |
| 🇺🇸 United States | South | $760,347 | $154,540 | 1,624 | 456 | 20.32% | $468 |
| 🇺🇸 United States | Midwest | $740,473 | $142,699 | 1,525 | 436 | 19.27% | $486 |
| 🇩🇪 Germany | Bavaria | $583,796 | $113,943 | 1,211 | 335 | 19.52% | $482 |
| 🇨🇦 Canada | Ontario | $682,772 | $135,187 | 1,536 | 383 | 19.80% | $445 |
| 🇨🇦 Canada | British Columbia | $516,738 | $105,606 | 1,103 | 305 | 20.44% | $468 |
| 🇦🇺 Australia | New South Wales | $512,876 | $101,049 | 1,097 | 308 | 19.70% | $468 |
| 🇩🇪 Germany | North Rhine-W. | $381,396 | $75,601 | 893 | 242 | 19.82% | $427 |

**Key observations:**
- **UK (England)** is the single largest market by revenue ($1.33M), contributing ~16.1% of global revenue
- **US collectively** (Northeast + West + South + Midwest) = **$3.5M**, representing ~42.5% of total revenue
- **BC, Canada** and **UK England** have the highest profit margins (20.44% and 20.33%)
- **US Midwest** has the lowest margin (19.27%) but the highest AOV ($485.56) — suggesting high-value, lower-frequency buyers

---

## 8. Customer Demographics & Segments

### 8.1 Customer Segments

| Segment | Customers | Orders | Revenue | Margin | AOV |
|---|---|---|---|---|---|
| **Consumer** | 2,575 | 7,283 | $3,666,739 | 20.12% | $503 |
| Small Business | 1,047 | 3,055 | $1,421,953 | 20.23% | $465 |
| Returning Customer | 1,823 | 2,383 | $1,115,274 | 20.09% | $468 |
| Corporate | 677 | 2,039 | $942,132 | **18.65%** | $462 |
| New Customer | 1,214 | 1,417 | $708,174 | 19.95% | $500 |
| **Premium** | 260 | 792 | $379,818 | **20.83%** | $480 |

**Key observations:**
- **Consumers** are the largest segment — 52.7% of customers generating 44.5% of revenue
- **Premium customers** are highly efficient: 260 customers generating ~$380K with the highest margin (20.83%)
- **Corporate** has the lowest margin (18.65%), suggesting heavier discounting for B2B relationships — worth examining contract terms
- **New Customers** (1,214) have a solid AOV of $500, showing strong first-purchase quality

### 8.2 Demographics by Age & Gender

| Age Group | Gender | Customers | Revenue | Avg Rating |
|---|---|---|---|---|
| 35–49 | Female | 1,263 | $1,994,492 | 3.98 |
| 35–49 | Male | 1,160 | $1,914,768 | 3.97 |
| 25–34 | Male | 585 | $1,051,719 | 4.00 |
| 25–34 | Female | 591 | $977,732 | 4.00 |
| 50+ | Female | 397 | $667,201 | 4.01 |
| 50+ | Male | 396 | $624,909 | 4.02 |
| <25 | Male | 207 | $365,928 | 3.99 |
| <25 | Female | 217 | $352,669 | 3.97 |

**Key observations:**
- The **35–49 cohort** is the dominant revenue driver (~$3.9M combined), accounting for **~47.4% of total revenue**
- Gender parity is notable: Male and Female customers are nearly equal in count and revenue contribution
- **50+ customers** have the highest average ratings (4.01–4.02), suggesting greater satisfaction post-purchase
- The **<25 cohort** represents an untapped growth opportunity — smaller now but with high lifetime value potential

---

## 9. Sales Channel Analysis

| Channel | Revenue | % of Total | Orders | Margin | Avg Delivery |
|---|---|---|---|---|---|
| **Online** | $3,112,092 | 37.8% | 7,444 | 20.24% | 2.95 days |
| **Retail Store** | $2,449,189 | 29.7% | 5,779 | 19.90% | 0.89 days |
| **B2B Portal** | $2,121,499 | 25.8% | 2,070 | 19.79% | 3.02 days |
| **Phone Order** | $551,310 | 6.7% | 1,432 | 19.67% | 2.98 days |

**Key observations:**
- **Online** is the dominant channel by revenue (37.8%), with the best profit margin (20.24%)
- **Retail Store** has the fastest delivery (0.89 days — essentially same-day pickup) and is the second-largest channel
- **B2B Portal** punches above its weight — 2,070 orders generating $2.12M suggests high-value B2B transactions with average order value significantly higher than consumer channels
- **Phone Order** is declining relevance at 6.7% — potential candidate for resource optimization

> [!TIP]
> B2B Portal generates 25.8% of revenue with only 14.2% of order count, implying an **AOV of ~$1,025** — far above the company average of $566. Growing the B2B segment should be a strategic priority.

---

## 10. Fulfillment, Delivery & Returns

### 10.1 Delivery Performance

| Speed Category | Orders | Avg Delivery Days |
|---|---|---|
| Next Day / Express | 9,111 (50.6%) | 0.25 days |
| Standard | 4,992 (27.7%) | 3.19 days |
| Delayed | 3,897 (21.7%) | 5.74 days |

- **50.6% of orders** are fulfilled next-day/express — a strong operational capability
- **21.7% of orders are delayed** (>5 days) — this is a significant operational pain point

### 10.2 Shipping Method Analysis

| Method | Orders | Avg Days | Revenue |
|---|---|---|---|
| Pickup | 6,939 | 0.01 days | $2,997,593 |
| Standard | 7,735 | 4.50 days | $3,639,938 |
| Express | 2,377 | 1.84 days | $1,139,897 |
| Next Day | 949 | 1.37 days | $456,664 |

### 10.3 Returns Analysis

**Overall Return Rate: 10.41%**

| Return Reason | Count | Returned Value |
|---|---|---|
| Late Delivery | 331 | $145,310 |
| Changed Mind | 300 | **$153,914** |
| Wrong Item | 317 | $121,065 |
| Damaged | 312 | $132,388 |
| Other | 311 | $140,189 |
| Defective | 302 | $135,429 |

**Key observations:**
- Return reasons are remarkably **evenly distributed** (300–331 per reason), suggesting no single systemic failure
- **Late Delivery** is the most frequent return reason — directly tied to the 21.7% delayed delivery rate
- **Changed Mind** returns generate the highest revenue loss ($153,914) — these are behavioural and may respond to better pre-purchase product content/imagery
- **Damaged + Defective** together = 614 returns ($267,818) — a packaging/quality control concern

> [!WARNING]
> The 21.7% delayed delivery rate is the primary driver of Late Delivery returns. Improving logistics for Standard shipping (avg 4.5 days) could reduce returns and improve customer satisfaction scores.

---

## 11. Payment Methods

| Method | Transactions | Revenue | Share |
|---|---|---|---|
| **Credit Card** | 6,804 | $3,251,316 | ~37.8% |
| **Debit Card** | 3,954 | $1,738,075 | ~21.9% |
| **PayPal** | 2,816 | $1,329,416 | ~15.7% |
| Bank Transfer | 2,157 | $932,103 | ~11.9% |
| Apple Pay | 1,087 | $466,580 | ~6.0% |
| Cash | 1,038 | $471,008 | ~5.8% |

> [!NOTE]
> Minor data inconsistencies exist in payment method naming (e.g., `"credit card"`, `"DebitCard"`, `"paypal"` — lowercase/variant forms representing ~1% of transactions). These are residual from pre-cleaning and should be standardized in the next pipeline run.

**Credit Card** is overwhelmingly dominant at ~37.8% of transactions. **Digital wallets (PayPal + Apple Pay) combined** account for ~21.7%, showing strong digital payment adoption.

---

## 12. Key Findings & Strategic Recommendations

### 🔍 Summary of Key Findings

1. **Electronics is the revenue engine** but not the margin leader — it contributes 59.8% of revenue at only 19.34% margin
2. **The 35–49 age demographic** is the core customer base — any churn here directly impacts business health
3. **B2B Portal is underexplored** — generating $1,025 AOV vs $566 company average with near-identical margins
4. **21.7% delayed delivery rate** is the #1 operational risk, driving the top return reason
5. **57.6% discount frequency** is high — testing selective discount reduction could improve margin
6. **UK is the largest single market** despite a smaller GDP vs the US — suggesting strong brand-market fit

### 💡 Strategic Recommendations

| Priority | Recommendation | Expected Impact |
|---|---|---|
| 🔴 **High** | Investigate and reduce the 21.7% delayed delivery rate for Standard shipping | Reduce return rate, improve ratings |
| 🔴 **High** | Scale B2B Portal acquisition — highest AOV channel at ~$1,025/order | Revenue growth without margin dilution |
| 🟡 **Medium** | Audit Appliances return rate (11.99%) — highest among categories | Protect margins, reduce returns |
| 🟡 **Medium** | A/B test discount frequency reduction on Electronics by 10–15% | Potential $50K+ margin improvement |
| 🟡 **Medium** | Develop targeted campaigns for the <25 segment (emerging customer group) | Long-term LTV growth |
| 🟢 **Low** | Standardize remaining payment method naming inconsistencies in pipeline | Data quality improvement |
| 🟢 **Low** | Promotion code attribution analysis (SAVE10, HOLIDAY20, BLACKFRIDAY25) | Optimize marketing spend |
| 🟢 **Low** | Expand Premium segment (260 customers, 20.83% margin) via referral programs | High-margin revenue expansion |

### 📌 Watch Metrics Going Forward

- **Monthly profit margin** — ensure it stays above 19%
- **Return rate trend** — target reduction to <8%
- **B2B Portal revenue share** — target >30% of total
- **Average customer rating** — target 4.1+ through delivery improvements
- **Discount frequency** — target reduction to <50% while maintaining revenue

---

*This report was generated from `analysis.ipynb` and the associated dashboard export data. All figures are based on 18,000 cleaned transaction records processed via PySpark 4.2.0.*
