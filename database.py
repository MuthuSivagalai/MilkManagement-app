import sqlite3
import csv
import io
import re
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "milk_delivery.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

AVAILABLE_ITEMS = [
    "Aavin Milk (250ml)",
    "Aavin Milk (500ml)",
    "Aavin Curd (100ml)",
    "Nanjil Milk (130ml)",
    "Nanjil Milk (500ml)",
    "Nanjil Milk (1 Litre)",
    "Nanjil Green Milk (500ml)",
    "Nanjil Green Milk (1 Litre)",
    "Nanjil Curd (100ml)"
]

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
            rate REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, delivery_date, item_name),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    
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
    
    try:
        cur.execute("DELETE FROM customer_items WHERE item_name = 'Aavin Milk (100ml)'")
        cur.execute("DELETE FROM deliveries WHERE item_name = 'Aavin Milk (100ml)'")
    except Exception:
        pass

    default_rates = {
        "Aavin Milk (250ml)": 25.0,
        "Aavin Milk (500ml)": 28.0,
        "Aavin Curd (100ml)": 15.0,
        "Nanjil Milk (130ml)": 15.0,
        "Nanjil Milk (500ml)": 35.0,
        "Nanjil Milk (1 Litre)": 70.0,
        "Nanjil Green Milk (500ml)": 38.0,
        "Nanjil Green Milk (1 Litre)": 75.0,
        "Nanjil Curd (100ml)": 15.0
    }
    for item, price in default_rates.items():
        key = f"rate_{item.lower().replace(' ', '_').replace('(', '').replace(')', '')}"
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, str(price)))

    conn.commit()
    conn.close()

def get_item_rates():
    conn = get_conn()
    rates = {}
    for item in AVAILABLE_ITEMS:
        key = f"rate_{item.lower().replace(' ', '_').replace('(', '').replace(')', '')}"
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        rates[item] = float(row[0]) if row else 30.0
    conn.close()
    return rates

def set_item_rate(item, rate):
    conn = get_conn()
    key = f"rate_{item.lower().replace(' ', '_').replace('(', '').replace(')', '')}"
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, str(rate)))
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
        if item_name != 'Aavin Milk (100ml)' and item_name not in seen:
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
        if item_name != 'Aavin Milk (100ml)' and item_name not in seen:
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
        if r[1] != 'Aavin Milk (100ml)' and r[1] not in seen:
            seen.add(r[1])
            unique_items.append({"id": r[0], "item_name": r[1], "normal_qty": r[2]})
    return unique_items

def save_delivery(customer_id, delivery_date, item_name, quantity, rate, status, note=""):
    if item_name == 'Aavin Milk (100ml)':
        return
    conn = get_conn()
    conn.execute("""
        INSERT INTO deliveries(customer_id, delivery_date, item_name, quantity, rate, status, note)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(customer_id, delivery_date, item_name) DO UPDATE SET
          quantity=excluded.quantity,
          rate=excluded.rate,
          status=excluded.status,
          note=excluded.note
    """, (customer_id, delivery_date, item_name, quantity, rate, status, note))
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
        "SELECT id, item_name, quantity, rate, status, note FROM deliveries WHERE customer_id=? AND delivery_date=?",
        (customer_id, delivery_date)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "item_name": r[1], "quantity": r[2], "rate": r[3], "status": r[4], "note": r[5]} for r in rows if r[1] != 'Aavin Milk (100ml)']

def get_deliveries(customer_id=None, date_or_month=None):
    conn = get_conn()
    if customer_id is not None and date_or_month:
        if len(date_or_month) == 7:
            sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note
                     FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=? AND substr(d.delivery_date,1,7)=? AND d.item_name != 'Aavin Milk (100ml)'"""
        else:
            sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note
                     FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=? AND d.delivery_date=? AND d.item_name != 'Aavin Milk (100ml)'"""
        rows = conn.execute(sql, (customer_id, date_or_month)).fetchall()
    elif date_or_month:
        sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note
                 FROM deliveries d JOIN customers c ON c.id=d.customer_id
                 WHERE d.delivery_date=? AND d.item_name != 'Aavin Milk (100ml)'"""
        rows = conn.execute(sql, (date_or_month,)).fetchall()
    else:
        sql = """SELECT d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note
                 FROM deliveries d JOIN customers c ON c.id=d.customer_id
                 WHERE d.item_name != 'Aavin Milk (100ml)'"""
        rows = conn.execute(sql).fetchall()
    conn.close()
    
    # Sort naturally by customer name, date, and item name
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
        WHERE d.customer_id=? AND substr(d.delivery_date,1,7)=? AND d.item_name != 'Aavin Milk (100ml)'
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

def get_dashboard_stats(delivery_date):
    conn = get_conn()
    customers = conn.execute("SELECT COUNT(*) FROM customers WHERE active=1").fetchone()[0]
    row = conn.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN status='Delivered' AND quantity>0 THEN 1 ELSE 0 END),0),
          COALESCE(SUM(CASE WHEN status='No Milk' OR quantity=0 THEN 1 ELSE 0 END),0),
          COALESCE(SUM(quantity),0)
        FROM deliveries WHERE delivery_date=? AND item_name != 'Aavin Milk (100ml)'
    """, (delivery_date,)).fetchone()
    conn.close()
    return {"customers": customers, "delivered": row[0], "no_milk": row[1], "litres": float(row[2] or 0)}

def export_customers_csv():
    customers = get_customers(include_inactive=True)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Name", "Phone", "Address", "Default Items & Qty", "Active", "Created At"])
    for c in customers:
        cid, name, phone, address, active, created = c
        items = get_customer_items(cid)
        items_str = " | ".join([f"{i['item_name']} ({i['normal_qty']:g})" for i in items if i['item_name'] != 'Aavin Milk (100ml)'])
        writer.writerow([cid, name, phone or "", address or "", items_str, active, created])
    return out.getvalue().encode("utf-8-sig")

def export_deliveries_csv():
    rows = get_deliveries()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Customer", "Date", "Item Name", "Quantity / Packets", "Rate", "Status", "Note"])
    writer.writerows(rows)
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