import json
print([r["Payment_Method"] for r in json.load(open("D:/Portfolio/Retail Sales Dataset/retail-sales-analysis/dashboard_exports/payment_methods.json"))])
