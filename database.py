import sqlite3
import csv
import io
import re
import calendar
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "milk_delivery.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# Organized with Normal/Retail customer variants first, followed by Shop variants
AVAILABLE_ITEMS = [
    # --- Normal / Retail Customer Variants ---
    "Aavin Milk (250ml)",
    "Aavin Milk (500ml)",
    "Aavin Curd (100ml)",
    "Nanjil Milk Red (130ml)",
    "Nanjil Milk Red (500ml)",
    "Nanjil Milk Red (1 Litre)",
    "Nanjil Green Milk (500ml)",
    "Nanjil Green Milk (1 Litre)",
    "Nanjil Curd (100ml)",
    
    # --- Shop Variants ---
    "Aavin Milk (Shop) (250ml)",
    "Aavin Milk (Shop) (500ml)",
    "Aavin Curd (Shop) (100ml)",
    "Nanjil Milk Red (Shop) (130ml)",
    "Nanjil Milk Red (Shop) (500ml)",
    "Nanjil Milk Red (Shop) (1 Litre)",
    "Nanjil Green Milk (Shop) (500ml)",
    "Nanjil Green Milk (Shop) (1 Litre)",
    "Nanjil Curd (Shop) (100ml)"
]

def _slug(item_name):
    return item_name.lower().replace(' ', '_').replace('(', '').replace(')', '')

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT UNIQUE NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customer_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            normal_qty REAL NOT NULL DEFAULT 1.0,
            UNIQUE(customer_id, item_name),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_items'")
    if cur.fetchone():
        try:
            cur.execute("""
                INSERT OR IGNORE INTO customer_items_new(customer_id, item_name, normal_qty)
                SELECT customer_id, item_name, normal_qty FROM customer_items
            """)
            cur.execute("DROP TABLE customer_items")
        except Exception:
            pass
    cur.execute("ALTER TABLE customer_items_new RENAME TO customer_items")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            delivery_date TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            cost_rate REAL NOT NULL DEFAULT 0,
            rate REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, delivery_date, item_name),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    
    cur.execute("PRAGMA table_info(deliveries)")
    columns = [col[1] for col in cur.fetchall()]
    if "cost_rate" not in columns:
        cur.execute("ALTER TABLE deliveries ADD COLUMN cost_rate REAL NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            method TEXT,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)

    default_rates = {
        "Aavin Milk (250ml)": (10.80, 14.0),
        "Aavin Milk (500ml)": (22.0, 28.0),
        "Aavin Curd (100ml)": (8.50, 10.0),
        "Nanjil Milk Red (130ml)": (10.50, 13.0),
        "Nanjil Milk Red (500ml)": (37.0, 42.0),
        "Nanjil Milk Red (1 Litre)": (72.0, 84.0),
        "Nanjil Green Milk (500ml)": (33.0, 39.0),
        "Nanjil Green Milk (1 Litre)": (66.0, 76.50),
        "Nanjil Curd (100ml)": (7.50, 10.0),
        
        "Aavin Milk (Shop) (250ml)": (10.80, 12.50),
        "Aavin Milk (Shop) (500ml)": (22.0, 25.0),
        "Aavin Curd (Shop) (100ml)": (8.50, 9.50),
        "Nanjil Milk Red (Shop) (130ml)": (10.50, 11.50),
        "Nanjil Milk Red (Shop) (500ml)": (37.0, 39.0),
        "Nanjil Milk Red (Shop) (1 Litre)": (72.0, 78.0),
        "Nanjil Green Milk (Shop) (500ml)": (33.0, 36.0),
        "Nanjil Green Milk (Shop) (1 Litre)": (66.0, 71.0),
        "Nanjil Curd (Shop) (100ml)": (7.50, 9.0)
    }
    
    for item, (cp, sp) in default_rates.items():
        key_cp = f"cost_rate_{_slug(item)}"
        key_sp = f"rate_{_slug(item)}"
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key_cp, str(cp)))
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key_sp, str(sp)))

    conn.commit()
    conn.close()

def get_all_available_items():
    conn = get_conn()
    rows = conn.execute("SELECT item_name FROM custom_items").fetchall()
    conn.close()
    custom_list = [r[0] for r in rows]
    combined = list(AVAILABLE_ITEMS)
    for ci in custom_list:
        if ci not in combined:
            combined.append(ci)
    return combined

def add_custom_item(item_name, default_cp=20.0, default_sp=25.0):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO custom_items(item_name) VALUES(?)", (item_name,))
    conn.commit()
    conn.close()
    set_item_rate(item_name, default_cp, default_sp)

def get_item_rates():
    conn = get_conn()
    rates = {}
    all_items = get_all_available_items()
    for item in all_items:
        key_cp = f"cost_rate_{_slug(item)}"
        key_sp = f"rate_{_slug(item)}"
        row_cp = conn.execute("SELECT value FROM settings WHERE key=?", (key_cp,)).fetchone()
        row_sp = conn.execute("SELECT value FROM settings WHERE key=?", (key_sp,)).fetchone()
        
        cost_p = float(row_cp[0]) if row_cp else 20.0
        sell_p = float(row_sp[0]) if row_sp else 25.0
        rates[item] = {"cost_price": cost_p, "sell_price": sell_p}
    conn.close()
    return rates

def set_item_rate(item, cost_price, sell_price):
    conn = get_conn()
    key_cp = f"cost_rate_{_slug(item)}"
    key_sp = f"rate_{_slug(item)}"
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key_cp, str(cost_price)))
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key_sp, str(sell_price)))
    
    conn.execute("UPDATE deliveries SET cost_rate=?, rate=? WHERE item_name=?", (cost_price, sell_price, item))
    conn.commit()
    conn.close()

def add_customer(name, phone, address, items_list, active=True):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO customers(name, phone, address, active) VALUES(?,?,?,?)",
        (name, phone, address, int(active))
    )
    cid = cur.lastrowid
    seen = set()
    for item_name, qty in items_list:
        if item_name not in seen:
            seen.add(item_name)
            cur.execute("INSERT OR REPLACE INTO customer_items(customer_id, item_name, normal_qty) VALUES(?,?,?)", (cid, item_name, qty))
    conn.commit()
    conn.close()

def update_customer(cid, name, phone, address, items_list, active):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE customers SET name=?, phone=?, address=?, active=? WHERE id=?",
        (name, phone, address, int(active), cid)
    )
    cur.execute("DELETE FROM customer_items WHERE customer_id=?", (cid,))
    seen = set()
    for item_name, qty in items_list:
        if item_name not in seen:
            seen.add(item_name)
            cur.execute("INSERT OR REPLACE INTO customer_items(customer_id, item_name, normal_qty) VALUES(?,?,?)", (cid, item_name, qty))
    conn.commit()
    conn.close()

def delete_customer(cid):
    conn = get_conn()
    conn.execute("DELETE FROM customers WHERE id=?", (cid,))
    conn.commit()
    conn.close()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

def get_customers(include_inactive=False):
    conn = get_conn()
    sql = "SELECT id, name, phone, address, active, created_at FROM customers"
    if not include_inactive:
        sql += " WHERE active=1"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return sorted(rows, key=lambda x: natural_sort_key(x[1]))

def get_customer(cid):
    conn = get_conn()
    row = conn.execute("SELECT id, name, phone, address, active, created_at FROM customers WHERE id=?", (cid,)).fetchone()
    conn.close()
    return row

def get_customer_items(cid):
    conn = get_conn()
    rows = conn.execute("SELECT id, item_name, normal_qty FROM customer_items WHERE customer_id=?", (cid,)).fetchall()
    conn.close()
    seen = set()
    unique_items = []
    for r in rows:
        if r[1] not in seen:
            seen.add(r[1])
            unique_items.append({"id": r[0], "item_name": r[1], "normal_qty": r[2]})
    return unique_items

def save_delivery(customer_id, delivery_date, item_name, quantity, cost_rate, sell_rate, status, note=""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO deliveries(customer_id, delivery_date, item_name, quantity, cost_rate, rate, status, note)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(customer_id, delivery_date, item_name) DO UPDATE SET
          quantity=excluded.quantity,
          cost_rate=excluded.cost_rate,
          rate=excluded.rate,
          status=excluded.status,
          note=excluded.note
    """, (customer_id, delivery_date, item_name, quantity, cost_rate, sell_rate, status, note))
    conn.commit()
    conn.close()

def clear_deliveries_for_date(customer_id, delivery_date):
    conn = get_conn()
    conn.execute("DELETE FROM deliveries WHERE customer_id=? AND delivery_date=?", (customer_id, delivery_date))
    conn.commit()
    conn.close()

def get_customer_deliveries_for_date(customer_id, delivery_date):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, item_name, quantity, cost_rate, rate, status, note FROM deliveries WHERE customer_id=? AND delivery_date=?",
        (customer_id, delivery_date)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "item_name": r[1], "quantity": r[2], "cost_rate": r[3], "rate": r[4], "status": r[5], "note": r[6]} for r in rows]

def get_deliveries(customer_id=None, date_or_month=None):
    conn = get_conn()
    if customer_id is not None and date_or_month:
        if len(date_or_month) == 7:
            sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note, d.cost_rate
                     FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=? AND substr(d.delivery_date,1,7)=?"""
        else:
            sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note, d.cost_rate
                     FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=? AND d.delivery_date=?"""
        rows = conn.execute(sql, (customer_id, date_or_month)).fetchall()
    elif date_or_month:
        sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note, d.cost_rate
                 FROM deliveries d JOIN customers c ON c.id=d.customer_id
                 WHERE d.delivery_date=?"""
        rows = conn.execute(sql, (date_or_month,)).fetchall()
    else:
        sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note, d.cost_rate
                 FROM deliveries d JOIN customers c ON c.id=d.customer_id"""
        rows = conn.execute(sql).fetchall()
    conn.close()
    
    if date_or_month and customer_id is None:
        return sorted(rows, key=lambda x: (natural_sort_key(x[1]), str(x[3])))
    elif customer_id is not None:
        return sorted(rows, key=lambda x: (str(x[2]), natural_sort_key(x[1]), str(x[3])))
    else:
        return sorted(rows, key=lambda x: (str(x[2]), natural_sort_key(x[1]), str(x[3])), reverse=True)

def get_monthly_summary(customer_id, month):
    conn = get_conn()
    row = conn.execute("""
        SELECT COALESCE(SUM(d.quantity),0),
               COALESCE(SUM(d.quantity * d.rate),0)
        FROM deliveries d
        WHERE d.customer_id=? AND substr(d.delivery_date,1,7)=?
    """, (customer_id, month)).fetchone()
    conn.close()
    return {"litres": float(row[0] or 0), "total": float(row[1] or 0)}

def add_payment(customer_id, month, payment_date, amount, method, note):
    conn = get_conn()
    conn.execute(
        "INSERT INTO payments(customer_id, month, payment_date, amount, method, note) VALUES(?,?,?,?,?,?)",
        (customer_id, month, payment_date, amount, method, note)
    )
    conn.commit()
    conn.close()

def get_payments(customer_id, month):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, customer_id, payment_date, amount, method, note FROM payments WHERE customer_id=? AND month=? ORDER BY payment_date",
        (customer_id, month)
    ).fetchall()
    conn.close()
    return rows

def get_dashboard_stats(start_date, end_date=None):
    if not end_date:
        end_date = start_date
    conn = get_conn()
    customers = conn.execute("SELECT COUNT(*) FROM customers WHERE active=1").fetchone()[0]
    row = conn.execute("""
        SELECT
          COALESCE(COUNT(DISTINCT CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity>0 THEN customer_id END), 0),
          COALESCE(COUNT(DISTINCT CASE WHEN status='No Milk' OR status='பால் இல்லை' OR quantity=0 THEN customer_id END), 0),
          COALESCE(SUM(quantity), 0),
          COALESCE(SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * cost_rate ELSE 0 END), 0),
          COALESCE(SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * rate ELSE 0 END), 0)
        FROM deliveries WHERE delivery_date BETWEEN ? AND ?
    """, (start_date, end_date)).fetchone()
    conn.close()
    
    total_cost = float(row[3] or 0)
    total_sell = float(row[4] or 0)
    profit = total_sell - total_cost

    return {
        "customers": customers,
        "delivered": row[0],
        "no_milk": row[1],
        "litres": float(row[2] or 0),
        "total_cost": total_cost,
        "total_sell": total_sell,
        "profit": profit
    }

def get_item_breakdown_by_date_range(start_date, end_date=None):
    if not end_date:
        end_date = start_date
    conn = get_conn()
    sql = """
        SELECT 
            item_name,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity ELSE 0 END) as delivered_qty,
            SUM(CASE WHEN status='No Milk' OR status='பால் இல்லை' OR quantity = 0 THEN 1 ELSE 0 END) as undelivered_count,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * cost_rate ELSE 0 END) as total_cost,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * rate ELSE 0 END) as total_sell
        FROM deliveries
        WHERE delivery_date BETWEEN ? AND ?
        GROUP BY item_name
        ORDER BY item_name
    """
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()
    return [
        {
            "item_name": r[0],
            "delivered_qty": float(r[1] or 0),
            "undelivered_count": int(r[2] or 0),
            "total_cost": float(r[3] or 0),
            "total_sell": float(r[4] or 0),
            "profit": float(r[4] or 0) - float(r[3] or 0)
        }
        for r in rows
    ]

def get_daily_breakdown_by_date_range(start_date, end_date):
    conn = get_conn()
    sql = """
        SELECT 
            delivery_date,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity ELSE 0 END) as delivered_qty,
            COUNT(DISTINCT CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN customer_id END) as delivered_cust,
            COUNT(DISTINCT CASE WHEN status='No Milk' OR status='பால் இல்லை' OR quantity = 0 THEN customer_id END) as undelivered_cust,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * cost_rate ELSE 0 END) as total_cost,
            SUM(CASE WHEN (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0 THEN quantity * rate ELSE 0 END) as total_sell
        FROM deliveries
        WHERE delivery_date BETWEEN ? AND ?
        GROUP BY delivery_date
        ORDER BY delivery_date ASC
    """
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()
    return [
        {
            "delivery_date": r[0],
            "delivered_qty": float(r[1] or 0),
            "delivered_cust": int(r[2] or 0),
            "undelivered_cust": int(r[3] or 0),
            "total_cost": float(r[4] or 0),
            "total_sell": float(r[5] or 0),
            "profit": float(r[5] or 0) - float(r[4] or 0)
        }
        for r in rows
    ]

def get_daily_brand_matrix(start_date, end_date):
    conn = get_conn()
    sql = """
        SELECT delivery_date, item_name, SUM(quantity)
        FROM deliveries
        WHERE delivery_date BETWEEN ? AND ? AND (status='Delivered' OR status='விநியோகிக்கப்பட்டது') AND quantity > 0
        GROUP BY delivery_date, item_name
        ORDER BY delivery_date ASC, item_name ASC
    """
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()
    
    matrix = {}
    for r in rows:
        d_date, item, qty = r[0], r[1], float(r[2] or 0)
        if d_date not in matrix:
            matrix[d_date] = {}
        matrix[d_date][item] = qty
    return matrix

def export_customers_csv():
    customers = get_customers(include_inactive=True)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Name", "Phone", "Address", "Default Items & Qty", "Active", "Created At"])
    for c in customers:
        cid, name, phone, address, active, created = c
        items = get_customer_items(cid)
        items_str = " | ".join([f"{i['item_name']} ({i['normal_qty']:g})" for i in items])
        writer.writerow([cid, name, phone or "", address or "", items_str, active, created])
    return out.getvalue().encode("utf-8-sig")

def export_deliveries_csv():
    rows = get_deliveries()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Customer", "Date", "Item Name", "Quantity / Packets", "Selling Rate", "Status", "Note", "Cost Rate"])
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")

def export_range_deliveries_csv(start_date, end_date):
    conn = get_conn()
    sql = """
        SELECT d.id, c.name, c.phone, d.delivery_date, d.item_name, d.quantity, d.cost_rate, d.rate, (d.quantity * d.cost_rate) as total_cost, (d.quantity * d.rate) as total_sell, ((d.quantity * d.rate) - (d.quantity * d.cost_rate)) as profit, d.status, d.note
        FROM deliveries d JOIN customers c ON c.id=d.customer_id
        WHERE d.delivery_date BETWEEN ? AND ?
        ORDER BY d.delivery_date ASC, c.name ASC
    """
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()
    
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Delivery ID", "Customer Name", "Phone", "Date", "Item / Brand", "Quantity", "Cost Rate (₹)", "Sell Rate (₹)", "Total Cost (₹)", "Total Revenue (₹)", "Profit (₹)", "Status", "Note"])
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")

def export_daily_summary_csv(start_date, end_date):
    daily_rows = get_daily_breakdown_by_date_range(start_date, end_date)
    matrix = get_daily_brand_matrix(start_date, end_date)
    all_items = get_all_available_items()
    
    out = io.StringIO()
    writer = csv.writer(out)
    
    headers = ["Date", "Delivered Customers", "No Milk Customers", "Total Delivered Qty", "Total Cost (₹)", "Total Revenue (₹)", "Profit (₹)"] + all_items
    writer.writerow(headers)
    
    for row in daily_rows:
        d = row["delivery_date"]
        b_map = matrix.get(d, {})
        brand_qtys = [b_map.get(item, 0.0) for item in all_items]
        writer.writerow([d, row["delivered_cust"], row["undelivered_cust"], row["delivered_qty"], row["total_cost"], row["total_sell"], row["profit"]] + brand_qtys)
        
    return out.getvalue().encode("utf-8-sig")

def export_all_customers_monthly_report_csv(month):
    customers = get_customers(include_inactive=True)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Customer ID", "Customer Name", "Phone", "Address", "Month", "Total Items / Qty", "Total Bill Amount (₹)", "Total Paid (₹)", "Balance Due (₹)"])
    for c in customers:
        cid, name, phone, address, _, _ = c
        summary = get_monthly_summary(cid, month)
        payments = get_payments(cid, month)
        paid = sum(float(p[3]) for p in payments)
        total = summary["total"]
        balance = total - paid
        writer.writerow([cid, name, phone or "", address or "", month, f"{summary['litres']:.2f}", f"{total:.2f}", f"{paid:.2f}", f"{balance:.2f}"])
    return out.getvalue().encode("utf-8-sig")
