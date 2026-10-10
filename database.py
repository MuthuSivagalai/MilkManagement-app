import csv
import io
import re
import calendar
from datetime import date, datetime
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text, bindparam

# Fetch connection string from .streamlit/secrets.toml
DB_URL = st.secrets["connections"]["postgresql"]["url"]

# Create Engine with connection pooling to maximize UI speed
engine = create_engine(
    DB_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True
)

_BASE_ITEMS = [
    "Aavin Milk (250ml)",
    "Aavin Milk (500ml)",
    "Aavin Curd (100ml)",
    "Nanjil Milk Red (130ml)",
    "Nanjil Milk Red (500ml)",
    "Nanjil Milk Red (1 Litre)",
    "Nanjil Green Milk (500ml)",
    "Nanjil Green Milk (1 Litre)",
    "Nanjil Curd (100ml)",
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

# Built-in items + items the admin adds later (Item Rates -> Add New Item).
# This list is updated IN PLACE by refresh_items(), so every module that imported it sees the change.
AVAILABLE_ITEMS = list(_BASE_ITEMS)

# ---------------------------------------------------------------------------
# Reusable SQL fragments (keeps the long CASE expressions in one place)
#
# DATA MODEL FOR EXTRA MILK
#   deliveries.quantity   = TOTAL packets delivered (normal + extra)  -> billing unchanged
#   deliveries.extra_qty  = the part of `quantity` that was an EXTRA request
#   normal packets        = quantity - extra_qty
# ---------------------------------------------------------------------------
_DELIVERED = "(status IN ('Delivered', 'விநியோகிக்கப்பட்டது') AND quantity > 0)"
_NOT_DELIVERED = "(status IN ('No Milk', 'பால் இல்லை') OR quantity = 0)"
_EXTRA = "COALESCE(extra_qty, 0)"


# Short codes used in the Customer Monthly Report, e.g. "2N130" = 2 packets of Nanjil Red 130ml.
# Edit freely - any item missing here gets an auto-generated code.
ITEM_CODES = {
    "Aavin Milk (250ml)": "Aavin250",
    "Aavin Milk (500ml)": "Aavin500",
    "Aavin Curd (100ml)": "AavinCurd100",
    "Nanjil Milk Red (130ml)": "Nanjil130",
    "Nanjil Milk Red (500ml)": "Nanjil500",
    "Nanjil Milk Red (1 Litre)": "Nanjil1L",
    "Nanjil Green Milk (500ml)": "NanjilGreen500",
    "Nanjil Green Milk (1 Litre)": "NanjilGreen1L",
    "Nanjil Curd (100ml)": "NanjilCurd100",
}


def item_code(item_name):
    """Readable short name, e.g. 'Nanjil130'. Shop items get a '-Shop' suffix (Aavin250-Shop)."""
    if item_name in ITEM_CODES:
        return ITEM_CODES[item_name]
    base = item_name.replace("(Shop) ", "")
    suffix = "-Shop" if "(Shop)" in item_name else ""
    if base in ITEM_CODES:
        return ITEM_CODES[base] + suffix
    return re.sub(r"[^A-Za-z0-9]", "", item_name) + suffix


def _slug(item_name):
    return item_name.lower().replace(' ', '_').replace('(', '').replace(')', '')


def _month_range(month):
    """'2026-10' -> ('2026-10-01', '2026-10-31'). Lets Postgres use the date index
    instead of TO_CHAR(delivery_date) which forces a full table scan."""
    y, m = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


# ---------------------------------------------------------------------------
# Schema setup  (cache_resource => runs ONCE per server process, not on every click)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _custom_item_names():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM custom_items ORDER BY created_at, name")).fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=30)
def _item_renames():
    """{original built-in name: new name} for built-in items the admin has renamed."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT old_name, new_name FROM item_renames")).fetchall()
    return {r[0]: r[1] for r in rows}


def refresh_items():
    """AVAILABLE_ITEMS = built-in items (with any renames applied) + admin-added items (cheap: cached for 30 s)."""
    ren = _item_renames()
    base = [ren.get(i, i) for i in _BASE_ITEMS]
    AVAILABLE_ITEMS[:] = base + [n for n in _custom_item_names() if n not in base]


@st.cache_resource(show_spinner=False)
def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(20),
                address TEXT,
                active INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customer_items (
                id SERIAL PRIMARY KEY,
                customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
                item_name VARCHAR(100) NOT NULL,
                normal_qty NUMERIC(5,2) DEFAULT 1.0,
                CONSTRAINT unique_cust_item UNIQUE(customer_id, item_name)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS deliveries (
                id SERIAL PRIMARY KEY,
                customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
                delivery_date DATE NOT NULL,
                item_name VARCHAR(100) NOT NULL,
                quantity NUMERIC(5,2) DEFAULT 0,
                cost_rate NUMERIC(10,2) DEFAULT 0,
                rate NUMERIC(10,2) DEFAULT 0,
                status VARCHAR(20) NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_delivery UNIQUE(customer_id, delivery_date, item_name)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
                month VARCHAR(10) NOT NULL,
                payment_date DATE NOT NULL,
                amount NUMERIC(10,2) NOT NULL,
                method VARCHAR(50),
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # ---- Migration: extra milk column (safe to run repeatedly; old rows get 0) ----
        conn.execute(text("ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS extra_qty NUMERIC(5,2) DEFAULT 0;"))

        # ---- Migration: bank / UPI reference of a payment (used to stop double-recording a statement) ----
        conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS txn_ref VARCHAR(100);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_payments_txn_ref ON payments(txn_ref);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);"))
        # payer name seen in a statement -> customer (learned the first time you confirm it)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payer_aliases (
                alias VARCHAR(200) PRIMARY KEY,
                customer_id INT REFERENCES customers(id) ON DELETE CASCADE
            );
        """))
        # built-in items that were renamed from the Item Rates page
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS item_renames (
                old_name VARCHAR(100) PRIMARY KEY,
                new_name VARCHAR(100) NOT NULL
            );
        """))

        # ---- Indexes: every dashboard / report query filters by date or by (customer, month) ----
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deliveries_date ON deliveries(delivery_date);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_payments_cust_month ON payments(customer_id, month);"))

        # ---- Items added by the admin from the Item Rates page ----
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_items (
                name VARCHAR(100) PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
    return True


# ---------------------------------------------------------------------------
# Item rates
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_item_rates():
    """Fetches all item rates in ONE database round-trip."""
    rates = {}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM settings WHERE key LIKE 'cost_rate_%' OR key LIKE 'rate_%'")).fetchall()
        settings_map = {row[0]: row[1] for row in rows}

        for item in AVAILABLE_ITEMS:
            key_cp = f"cost_rate_{_slug(item)}"
            key_sp = f"rate_{_slug(item)}"

            cp = float(settings_map.get(key_cp, 20.0))
            sp = float(settings_map.get(key_sp, 25.0))
            rates[item] = {"cost_price": cp, "sell_price": sp}
    return rates


def set_item_rates(changes):
    """Save many rates in ONE transaction. `changes` = {item: (cost_price, sell_price)}.
    NOTE: like the original code, this also re-prices existing deliveries of that item."""
    if not changes:
        return
    with engine.begin() as conn:
        for item, (cost_price, sell_price) in changes.items():
            conn.execute(text("""
                INSERT INTO settings(key, value) VALUES(:k, :v)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
            """), [
                {"k": f"cost_rate_{_slug(item)}", "v": str(cost_price)},
                {"k": f"rate_{_slug(item)}", "v": str(sell_price)},
            ])
            conn.execute(text("UPDATE deliveries SET cost_rate=:cp, rate=:sp WHERE item_name=:item;"),
                         {"cp": cost_price, "sp": sell_price, "item": item})
    st.cache_data.clear()


def set_item_rate(item, cost_price, sell_price):
    set_item_rates({item: (cost_price, sell_price)})


def add_item(name, cost_price, sell_price):
    """Add a NEW product / brand. Raises ValueError with a readable message if the name is not acceptable."""
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Item name is required.")
    if len(name) > 60:
        raise ValueError("Item name is too long (maximum 60 characters).")
    if name.lower() in [i.lower() for i in AVAILABLE_ITEMS]:
        raise ValueError(f"'{name}' already exists.")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO custom_items(name) VALUES(:n)"), {"n": name})
        conn.execute(text("""
            INSERT INTO settings(key, value) VALUES(:k, :v)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
        """), [
            {"k": f"cost_rate_{_slug(name)}", "v": str(cost_price)},
            {"k": f"rate_{_slug(name)}", "v": str(sell_price)},
        ])
    st.cache_data.clear()
    refresh_items()


def rename_item(old, new):
    """Rename a product everywhere: item list, customer defaults, ALL past deliveries, rates and Tamil name.
    Raises ValueError with a readable message if the new name is not acceptable."""
    new = " ".join(str(new or "").split())
    if not new:
        raise ValueError("New item name is required.")
    if len(new) > 60:
        raise ValueError("Item name is too long (maximum 60 characters).")
    if new == old:
        raise ValueError("The new name is the same as the old name.")
    if new.lower() in [i.lower() for i in AVAILABLE_ITEMS if i != old]:
        raise ValueError(f"'{new}' already exists.")
    with engine.begin() as conn:
        in_custom = conn.execute(text("SELECT 1 FROM custom_items WHERE name=:o"), {"o": old}).fetchone()
        if in_custom:
            conn.execute(text("UPDATE custom_items SET name=:n WHERE name=:o"), {"n": new, "o": old})
        else:  # built-in item: remember the new name (the built-in list in this file stays as it is)
            upd = conn.execute(text("UPDATE item_renames SET new_name=:n WHERE new_name=:o"), {"n": new, "o": old})
            if not upd.rowcount:
                conn.execute(text("INSERT INTO item_renames(old_name, new_name) VALUES(:o, :n)"), {"o": old, "n": new})
        conn.execute(text("UPDATE customer_items SET item_name=:n WHERE item_name=:o"), {"n": new, "o": old})
        conn.execute(text("UPDATE deliveries SET item_name=:n WHERE item_name=:o"), {"n": new, "o": old})
        for prefix in ("cost_rate_", "rate_", "item_ta_"):  # rates + Tamil name follow the item
            ko, kn = prefix + _slug(old), prefix + _slug(new)
            if ko != kn:
                conn.execute(text("""
                    INSERT INTO settings(key, value) SELECT CAST(:kn AS TEXT), value FROM settings WHERE key=:ko
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
                """), {"kn": kn, "ko": ko})
                conn.execute(text("DELETE FROM settings WHERE key=:ko"), {"ko": ko})
    st.cache_data.clear()
    refresh_items()


# ---------------------------------------------------------------------------
# Generic settings (receipt greeting / announcements, Tamil item names, ...)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_settings_by_prefix(prefix):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM settings WHERE key LIKE :p"), {"p": prefix + "%"}).fetchall()
    return {r[0]: r[1] for r in rows}


def set_settings(mapping):
    with engine.begin() as conn:
        for k, v in mapping.items():
            conn.execute(text("""
                INSERT INTO settings(key, value) VALUES(:k, :v)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
            """), {"k": k, "v": v})
    st.cache_data.clear()


def get_item_tamil_names():
    """{item name: Tamil name typed by the owner} - only items that have one."""
    d = get_settings_by_prefix("item_ta_")
    return {i: d[f"item_ta_{_slug(i)}"] for i in AVAILABLE_ITEMS if d.get(f"item_ta_{_slug(i)}")}


def set_item_tamil_name(item, tamil):
    set_settings({f"item_ta_{_slug(item)}": " ".join(str(tamil or "").split())})


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def add_customer(name, phone, address, items_list, active=True):
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO customers(name, phone, address, active)
            VALUES(:name, :phone, :address, :active) RETURNING id;
        """), {"name": name, "phone": phone, "address": address, "active": int(active)})
        cid = res.fetchone()[0]

        seen = set()
        for item_name, qty in items_list:
            if item_name not in seen:
                seen.add(item_name)
                conn.execute(text("""
                    INSERT INTO customer_items(customer_id, item_name, normal_qty)
                    VALUES(:cid, :item, :qty);
                """), {"cid": cid, "item": item_name, "qty": qty})
    st.cache_data.clear()


def update_customer(cid, name, phone, address, items_list, active):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE customers SET name=:name, phone=:phone, address=:address, active=:active WHERE id=:cid;
        """), {"name": name, "phone": phone, "address": address, "active": int(active), "cid": cid})

        conn.execute(text("DELETE FROM customer_items WHERE customer_id=:cid;"), {"cid": cid})

        seen = set()
        for item_name, qty in items_list:
            if item_name not in seen:
                seen.add(item_name)
                conn.execute(text("""
                    INSERT INTO customer_items(customer_id, item_name, normal_qty)
                    VALUES(:cid, :item, :qty);
                """), {"cid": cid, "item": item_name, "qty": qty})
    st.cache_data.clear()


def delete_customer(cid):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customers WHERE id=:cid;"), {"cid": cid})
    st.cache_data.clear()


def natural_sort_key(s):
    return [int(text_val) if text_val.isdigit() else text_val.lower() for text_val in re.split('([0-9]+)', str(s))]


@st.cache_data(ttl=60)
def get_customers(include_inactive=False):
    sql = "SELECT id, name, phone, address, active, created_at FROM customers"
    if not include_inactive:
        sql += " WHERE active=1"
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return sorted(rows, key=lambda x: natural_sort_key(x[1]))


@st.cache_data(ttl=60)
def get_customer(cid):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, name, phone, address, active, created_at FROM customers WHERE id=:cid"), {"cid": cid}).fetchone()
    return row


@st.cache_data(ttl=60)
def get_customer_items(cid):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, item_name, normal_qty FROM customer_items WHERE customer_id=:cid"), {"cid": cid}).fetchall()
    return [{"id": r[0], "item_name": r[1], "normal_qty": float(r[2])} for r in rows]


@st.cache_data(ttl=60)
def get_all_customer_items():
    """ONE query for every customer's default items -> {customer_id: [(item_name, normal_qty), ...]}"""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT customer_id, item_name, normal_qty FROM customer_items ORDER BY id")).fetchall()
    out = {}
    for cid, item, qty in rows:
        out.setdefault(cid, []).append((item, float(qty)))
    return out


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------
def save_delivery(customer_id, delivery_date, item_name, quantity, cost_rate, sell_rate, status, note="", extra_qty=0.0):
    """Single-row save (kept for compatibility). For the daily sheet use save_daily_deliveries()."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO deliveries(customer_id, delivery_date, item_name, quantity, extra_qty, cost_rate, rate, status, note)
            VALUES(:cid, :d_date, :item, :qty, :extra, :cp, :sp, :status, :note)
            ON CONFLICT (customer_id, delivery_date, item_name) DO UPDATE SET
              quantity = EXCLUDED.quantity,
              extra_qty = EXCLUDED.extra_qty,
              cost_rate = EXCLUDED.cost_rate,
              rate = EXCLUDED.rate,
              status = EXCLUDED.status,
              note = EXCLUDED.note;
        """), {
            "cid": customer_id, "d_date": delivery_date, "item": item_name,
            "qty": quantity, "extra": extra_qty, "cp": cost_rate, "sp": sell_rate,
            "status": status, "note": note
        })
    st.cache_data.clear()


def save_daily_deliveries(delivery_date, customer_ids, rows):
    """Save a whole day's sheet in ONE transaction and ~3 round-trips.

    Old code did ~140 DELETEs + ~250 INSERTs, each as its own transaction (and cleared the
    cache every time) -> that was the main reason 'Save' took so long.

    rows: list of dicts {cid, item, qty, extra, cp, sp, status, note}
    """
    with engine.begin() as conn:
        if customer_ids:
            conn.execute(
                text("DELETE FROM deliveries WHERE delivery_date=:d AND customer_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"d": delivery_date, "ids": list(customer_ids)}
            )

        CHUNK = 300
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start:start + CHUNK]
            params = {"d": delivery_date}
            values = []
            for i, r in enumerate(chunk):
                values.append(f"(:cid{i}, :d, :item{i}, :qty{i}, :ex{i}, :cp{i}, :sp{i}, :st{i}, :note{i})")
                params.update({
                    f"cid{i}": r["cid"], f"item{i}": r["item"], f"qty{i}": r["qty"], f"ex{i}": r["extra"],
                    f"cp{i}": r["cp"], f"sp{i}": r["sp"], f"st{i}": r["status"], f"note{i}": r["note"],
                })
            conn.execute(text(f"""
                INSERT INTO deliveries(customer_id, delivery_date, item_name, quantity, extra_qty, cost_rate, rate, status, note)
                VALUES {", ".join(values)}
                ON CONFLICT (customer_id, delivery_date, item_name) DO UPDATE SET
                  quantity = EXCLUDED.quantity,
                  extra_qty = EXCLUDED.extra_qty,
                  cost_rate = EXCLUDED.cost_rate,
                  rate = EXCLUDED.rate,
                  status = EXCLUDED.status,
                  note = EXCLUDED.note;
            """), params)
    st.cache_data.clear()


def clear_deliveries_for_date(customer_id, delivery_date):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM deliveries WHERE customer_id=:cid AND delivery_date=:d_date"), {
            "cid": customer_id, "d_date": delivery_date
        })
    st.cache_data.clear()


@st.cache_data(ttl=60)
def get_deliveries_map_for_date(delivery_date):
    """All deliveries of one date in ONE query -> {customer_id: [row dicts]}"""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT customer_id, item_name, quantity, {_EXTRA}, status, note
            FROM deliveries WHERE delivery_date=:d ORDER BY id
        """), {"d": delivery_date}).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r[0], []).append({
            "item": r[1], "qty": float(r[2] or 0), "extra": float(r[3] or 0),
            "status": r[4], "note": r[5] or ""
        })
    return out


@st.cache_data(ttl=60)
def get_customer_deliveries_for_date(customer_id, delivery_date):
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, item_name, quantity, cost_rate, rate, status, note, {_EXTRA}
            FROM deliveries WHERE customer_id=:cid AND delivery_date=:d_date
        """), {"cid": customer_id, "d_date": delivery_date}).fetchall()
    return [{"id": r[0], "item_name": r[1], "quantity": float(r[2]), "cost_rate": float(r[3]), "rate": float(r[4]),
             "status": r[5], "note": r[6], "extra_qty": float(r[7] or 0)} for r in rows]


@st.cache_data(ttl=60)
def get_deliveries(customer_id=None, date_or_month=None):
    cols = "d.id, c.name, d.delivery_date, d.item_name, d.quantity, d.rate, d.status, d.note, d.cost_rate, COALESCE(d.extra_qty, 0)"
    params = {}
    if customer_id is not None and date_or_month:
        if len(date_or_month) == 7:
            sd, ed = _month_range(date_or_month)
            sql = f"""SELECT {cols} FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=:cid AND d.delivery_date BETWEEN :sd AND :ed"""
            params = {"cid": customer_id, "sd": sd, "ed": ed}
        else:
            sql = f"""SELECT {cols} FROM deliveries d JOIN customers c ON c.id=d.customer_id
                     WHERE d.customer_id=:cid AND d.delivery_date=:dm"""
            params = {"cid": customer_id, "dm": date_or_month}
    elif date_or_month:
        sql = f"""SELECT {cols} FROM deliveries d JOIN customers c ON c.id=d.customer_id
                 WHERE d.delivery_date=:dm"""
        params = {"dm": date_or_month}
    else:
        sql = f"""SELECT {cols} FROM deliveries d JOIN customers c ON c.id=d.customer_id"""

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    if date_or_month and customer_id is None:
        return sorted(rows, key=lambda x: (natural_sort_key(x[1]), str(x[3])))
    elif customer_id is not None:
        return sorted(rows, key=lambda x: (str(x[2]), natural_sort_key(x[1]), str(x[3])))
    else:
        return sorted(rows, key=lambda x: (str(x[2]), natural_sort_key(x[1]), str(x[3])), reverse=True)


# ---------------------------------------------------------------------------
# Billing / payments
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_monthly_summary(customer_id, month):
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT COALESCE(SUM(quantity),0),
                   COALESCE(SUM(quantity * rate),0),
                   COALESCE(SUM({_EXTRA}),0),
                   COALESCE(SUM({_EXTRA} * rate),0)
            FROM deliveries
            WHERE customer_id=:cid AND delivery_date BETWEEN :sd AND :ed
        """), {"cid": customer_id, "sd": sd, "ed": ed}).fetchone()
    return {
        "litres": float(row[0] or 0),
        "total": float(row[1] or 0),
        "extra_qty": float(row[2] or 0),
        "extra_total": float(row[3] or 0),
    }


@st.cache_data(ttl=60)
def get_customer_month_items(customer_id, month):
    """Item-wise bill for one customer: normal vs extra packets."""
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT item_name,
                   SUM(quantity - {_EXTRA}),
                   SUM({_EXTRA}),
                   SUM(quantity),
                   SUM(quantity * rate)
            FROM deliveries
            WHERE customer_id=:cid AND delivery_date BETWEEN :sd AND :ed
            GROUP BY item_name ORDER BY item_name
        """), {"cid": customer_id, "sd": sd, "ed": ed}).fetchall()
    return [{
        "Product": r[0],
        "Normal Qty": float(r[1] or 0),
        "Extra Qty": float(r[2] or 0),
        "Total Qty": float(r[3] or 0),
        "Amount (₹)": float(r[4] or 0),
    } for r in rows if float(r[3] or 0) > 0]


def add_payment(customer_id, month, payment_date, amount, method, note):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO payments(customer_id, month, payment_date, amount, method, note)
            VALUES(:cid, :m, :p_date, :amt, :meth, :note)
        """), {"cid": customer_id, "m": month, "p_date": payment_date, "amt": amount, "meth": method, "note": note})
    st.cache_data.clear()


@st.cache_data(ttl=60)
def get_payments(customer_id, month):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, customer_id, payment_date, amount, method, note
            FROM payments WHERE customer_id=:cid AND month=:m ORDER BY payment_date
        """), {"cid": customer_id, "m": month}).fetchall()
    return rows


def delete_payment(payment_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM payments WHERE id=:i"), {"i": payment_id})
    st.cache_data.clear()


@st.cache_data(ttl=60)
def get_payments_between(start_date, end_date):
    """[(customer_id, 'YYYY-MM-DD', amount, txn_ref)] - used to spot payments already recorded."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT customer_id, payment_date, amount, txn_ref FROM payments
            WHERE payment_date BETWEEN :sd AND :ed
        """), {"sd": start_date, "ed": end_date}).fetchall()
    return [(int(r[0]), str(r[1]), float(r[2]), r[3] or "") for r in rows]


@st.cache_data(ttl=60)
def get_existing_txn_refs(refs):
    """Which of these statement references are already stored? (refs = tuple of str)"""
    refs = [r for r in refs if r]
    if not refs:
        return set()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT txn_ref FROM payments WHERE txn_ref IN :r").bindparams(
            bindparam("r", expanding=True)), {"r": refs}).fetchall()
    return {r[0] for r in rows}


def add_payments_bulk(rows):
    """rows: [{cid, month, date, amount, method, note, ref}] saved in ONE transaction.
    A row whose bank reference is already stored is skipped. Returns (saved, skipped)."""
    saved = skipped = 0
    with engine.begin() as conn:
        for r in rows:
            if r.get("ref") and conn.execute(text("SELECT 1 FROM payments WHERE txn_ref=:ref LIMIT 1"),
                                             {"ref": r["ref"]}).fetchone():
                skipped += 1
                continue
            conn.execute(text("""
                INSERT INTO payments(customer_id, month, payment_date, amount, method, note, txn_ref)
                VALUES(:cid, :m, :d, :amt, :meth, :note, :ref)
            """), {"cid": r["cid"], "m": r["month"], "d": r["date"], "amt": r["amount"],
                   "meth": r["method"], "note": r.get("note", ""), "ref": r.get("ref") or None})
            saved += 1
    st.cache_data.clear()
    return saved, skipped


@st.cache_data(ttl=60)
def get_payer_aliases():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT alias, customer_id FROM payer_aliases")).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def save_payer_aliases(mapping):
    """{normalised payer name: customer_id} - next statement matches these automatically."""
    if not mapping:
        return
    with engine.begin() as conn:
        for alias, cid in mapping.items():
            conn.execute(text("""
                INSERT INTO payer_aliases(alias, customer_id) VALUES(:a, :c)
                ON CONFLICT (alias) DO UPDATE SET customer_id=EXCLUDED.customer_id;
            """), {"a": alias[:200], "c": cid})
    st.cache_data.clear()


@st.cache_data(ttl=60)
def get_all_monthly_billing(month):
    """Bill + paid for EVERY customer in ONE query (old bulk report ran 2 queries per customer)."""
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT c.id, c.name, c.phone,
                   COALESCE(d.qty, 0), COALESCE(d.extra, 0), COALESCE(d.total, 0), COALESCE(d.extra_total, 0),
                   COALESCE(p.paid, 0)
            FROM customers c
            LEFT JOIN (
                SELECT customer_id,
                       SUM(quantity) AS qty,
                       SUM({_EXTRA}) AS extra,
                       SUM(quantity * rate) AS total,
                       SUM({_EXTRA} * rate) AS extra_total
                FROM deliveries WHERE delivery_date BETWEEN :sd AND :ed
                GROUP BY customer_id
            ) d ON d.customer_id = c.id
            LEFT JOIN (
                SELECT customer_id, SUM(amount) AS paid
                FROM payments WHERE month = :m
                GROUP BY customer_id
            ) p ON p.customer_id = c.id
        """), {"sd": sd, "ed": ed, "m": month}).fetchall()
    return sorted(rows, key=lambda x: natural_sort_key(x[1]))


@st.cache_data(ttl=60)
def get_saved_dates(month):
    """Dates of this month that have a saved Daily Delivery sheet, with a one-line summary each."""
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT delivery_date,
                   COUNT(DISTINCT customer_id),
                   COUNT(DISTINCT CASE WHEN {_DELIVERED} THEN customer_id END),
                   COUNT(DISTINCT CASE WHEN {_DELIVERED} AND {_EXTRA} > 0 THEN customer_id END),
                   COALESCE(SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} ELSE 0 END), 0)
            FROM deliveries WHERE delivery_date BETWEEN :sd AND :ed
            GROUP BY delivery_date ORDER BY delivery_date
        """), {"sd": sd, "ed": ed}).fetchall()
    return [{"date": str(r[0]), "customers": int(r[1]), "delivered": int(r[2]),
             "no_milk": int(r[1]) - int(r[2]), "extra_customers": int(r[3]), "extra_qty": float(r[4] or 0)}
            for r in rows]


@st.cache_data(ttl=60)
def get_no_milk_customers(delivery_date):
    """Customers saved for this date who got NOTHING delivered -> [{name, phone, note}]"""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT c.name, c.phone, COALESCE(STRING_AGG(NULLIF(d.note, ''), '; '), '')
            FROM deliveries d JOIN customers c ON c.id = d.customer_id
            WHERE d.delivery_date = :d
            GROUP BY c.id, c.name, c.phone
            HAVING SUM(CASE WHEN {_DELIVERED} THEN 1 ELSE 0 END) = 0
        """), {"d": delivery_date}).fetchall()
    rows = sorted(rows, key=lambda x: natural_sort_key(x[0]))
    return [{"Customer": r[0], "Phone": r[1] or "", "Note": r[2] or ""} for r in rows]


# ---------------------------------------------------------------------------
# Dashboard / reports
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_dashboard_stats(start_date, end_date=None):
    if not end_date:
        end_date = start_date
    params = {"sd": start_date, "ed": end_date}
    with engine.connect() as conn:  # one connection, two statements
        row = conn.execute(text(f"""
            SELECT
              (SELECT COUNT(*) FROM customers WHERE active=1),
              COALESCE(SUM(quantity), 0),
              COALESCE(SUM(CASE WHEN {_DELIVERED} THEN quantity * cost_rate ELSE 0 END), 0),
              COALESCE(SUM(CASE WHEN {_DELIVERED} THEN quantity * rate ELSE 0 END), 0),
              COALESCE(SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} ELSE 0 END), 0),
              COALESCE(SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} * rate ELSE 0 END), 0),
              COUNT(DISTINCT CASE WHEN {_DELIVERED} AND {_EXTRA} > 0 THEN customer_id END)
            FROM deliveries WHERE delivery_date BETWEEN :sd AND :ed
        """), params).fetchone()

        # A customer is "No Milk" only if NOTHING was delivered to them in the period.
        # (Old logic counted a customer as No Milk if ANY one of their items had qty 0,
        #  which gets wrong as soon as a customer has more than one item / extra items.)
        cust_row = conn.execute(text(f"""
            WITH per_cust AS (
                SELECT customer_id,
                       SUM(CASE WHEN {_DELIVERED} THEN 1 ELSE 0 END) AS d_rows,
                       SUM(CASE WHEN {_NOT_DELIVERED} THEN 1 ELSE 0 END) AS n_rows
                FROM deliveries WHERE delivery_date BETWEEN :sd AND :ed
                GROUP BY customer_id
            )
            SELECT COALESCE(SUM(CASE WHEN d_rows > 0 THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN d_rows = 0 AND n_rows > 0 THEN 1 ELSE 0 END), 0)
            FROM per_cust
        """), params).fetchone()

    t_cost = float(row[2] or 0)
    t_sell = float(row[3] or 0)
    return {
        "customers": int(row[0] or 0),
        "delivered": int(cust_row[0] or 0),
        "no_milk": int(cust_row[1] or 0),
        "litres": float(row[1] or 0),
        "total_cost": t_cost,
        "total_sell": t_sell,
        "profit": t_sell - t_cost,
        "extra_qty": float(row[4] or 0),
        "extra_sell": float(row[5] or 0),
        "extra_customers": int(row[6] or 0),
    }


@st.cache_data(ttl=60)
def get_item_breakdown_by_date_range(start_date, end_date=None):
    if not end_date:
        end_date = start_date
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                item_name,
                SUM(CASE WHEN {_DELIVERED} THEN quantity ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} ELSE 0 END),
                SUM(CASE WHEN {_NOT_DELIVERED} THEN 1 ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN quantity * cost_rate ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN quantity * rate ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} * rate ELSE 0 END)
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed
            GROUP BY item_name
            ORDER BY item_name
        """), {"sd": start_date, "ed": end_date}).fetchall()
    out = []
    for r in rows:
        total_qty, extra_qty = float(r[1] or 0), float(r[2] or 0)
        cost, sell = float(r[4] or 0), float(r[5] or 0)
        out.append({
            "item_name": r[0],
            "normal_qty": total_qty - extra_qty,
            "extra_qty": extra_qty,
            "delivered_qty": total_qty,
            "undelivered_count": int(r[3] or 0),
            "total_cost": cost,
            "total_sell": sell,
            "extra_sell": float(r[6] or 0),
            "profit": sell - cost,
        })
    return out


@st.cache_data(ttl=60)
def get_daily_breakdown_by_date_range(start_date, end_date):
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                delivery_date,
                SUM(CASE WHEN {_DELIVERED} THEN quantity ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN {_EXTRA} ELSE 0 END),
                COUNT(DISTINCT CASE WHEN {_DELIVERED} THEN customer_id END),
                COUNT(DISTINCT CASE WHEN {_DELIVERED} AND {_EXTRA} > 0 THEN customer_id END),
                COUNT(DISTINCT CASE WHEN {_NOT_DELIVERED} THEN customer_id END),
                SUM(CASE WHEN {_DELIVERED} THEN quantity * cost_rate ELSE 0 END),
                SUM(CASE WHEN {_DELIVERED} THEN quantity * rate ELSE 0 END)
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed
            GROUP BY delivery_date
            ORDER BY delivery_date ASC
        """), {"sd": start_date, "ed": end_date}).fetchall()
    return [{
        "delivery_date": str(r[0]),
        "delivered_qty": float(r[1] or 0),
        "extra_qty": float(r[2] or 0),
        "delivered_cust": int(r[3] or 0),
        "extra_cust": int(r[4] or 0),
        "undelivered_cust": int(r[5] or 0),
        "total_cost": float(r[6] or 0),
        "total_sell": float(r[7] or 0),
        "profit": float(r[7] or 0) - float(r[6] or 0)
    } for r in rows]


@st.cache_data(ttl=60)
def get_daily_brand_matrix(start_date, end_date):
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT delivery_date, item_name, SUM(quantity)
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed AND {_DELIVERED}
            GROUP BY delivery_date, item_name
            ORDER BY delivery_date ASC, item_name ASC
        """), {"sd": start_date, "ed": end_date}).fetchall()
    matrix = {}
    for r in rows:
        d_date, item, qty = str(r[0]), r[1], float(r[2] or 0)
        matrix.setdefault(d_date, {})[item] = qty
    return matrix


@st.cache_data(ttl=60)
def get_customer_date_totals(start_date, end_date):
    """[(customer_id, 'YYYY-MM-DD', item_name, qty, extra_qty), ...] for the Customer report.
    Item-level so the report can show '2A250 + 2N130'. Keyed by customer id and real date."""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT customer_id, delivery_date, item_name, SUM(quantity), SUM({_EXTRA})
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed AND {_DELIVERED}
            GROUP BY customer_id, delivery_date, item_name
        """), {"sd": start_date, "ed": end_date}).fetchall()
    return [(int(r[0]), str(r[1]), r[2], float(r[3] or 0), float(r[4] or 0)) for r in rows]


@st.cache_data(ttl=60)
def get_all_month_items(month):
    """Item-wise month bill for EVERY customer in ONE query -> {customer_id: [ {item, days, total, extra, amount} ]}.
    Used for receipts, WhatsApp messages and A4 slips."""
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT customer_id, item_name,
                   COUNT(DISTINCT CASE WHEN quantity > 0 THEN delivery_date END),
                   SUM(quantity), SUM({_EXTRA}), SUM(quantity * rate)
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed
            GROUP BY customer_id, item_name
            HAVING SUM(quantity) > 0
            ORDER BY customer_id, item_name
        """), {"sd": sd, "ed": ed}).fetchall()
    out = {}
    for r in rows:
        out.setdefault(int(r[0]), []).append({
            "item": r[1], "days": int(r[2] or 0), "total": float(r[3] or 0),
            "extra": float(r[4] or 0), "amount": float(r[5] or 0),
        })
    return out


@st.cache_data(ttl=60)
def get_all_month_daily(month):
    """Day-by-day deliveries for EVERY customer in ONE query.
    -> {customer_id: [ {date: 'YYYY-MM-DD', entries: [(item, qty, extra, amount)], amount} ]}
    A day with no entries means 'No Milk' that day."""
    sd, ed = _month_range(month)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT customer_id, delivery_date, item_name, quantity, {_EXTRA}, quantity * rate
            FROM deliveries
            WHERE delivery_date BETWEEN :sd AND :ed
            ORDER BY customer_id, delivery_date, item_name
        """), {"sd": sd, "ed": ed}).fetchall()
    tmp = {}
    for cid, d, item, qty, ex, amt in rows:
        day = tmp.setdefault(int(cid), {}).setdefault(str(d), {"entries": [], "amount": 0.0})
        if float(qty or 0) > 0:
            day["entries"].append((item, float(qty), float(ex or 0), float(amt or 0)))
            day["amount"] += float(amt or 0)
    return {cid: [{"date": d, "entries": v["entries"], "amount": v["amount"]} for d, v in sorted(days.items())]
            for cid, days in tmp.items()}


@st.cache_data(ttl=60)
def get_extra_report(start_date, end_date):
    """Every EXTRA-milk entry in the period (who asked, which brand, how many, how much)."""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT d.delivery_date, c.name, d.item_name, d.extra_qty, d.rate, d.note
            FROM deliveries d JOIN customers c ON c.id = d.customer_id
            WHERE d.delivery_date BETWEEN :sd AND :ed
              AND COALESCE(d.extra_qty, 0) > 0
              AND (d.status IN ('Delivered', 'விநியோகிக்கப்பட்டது') AND d.quantity > 0)
        """), {"sd": start_date, "ed": end_date}).fetchall()
    rows = sorted(rows, key=lambda x: (str(x[0]), natural_sort_key(x[1]), str(x[2])))
    return [{
        "Date": str(r[0]),
        "Customer": r[1],
        "Product": r[2],
        "Extra Qty": float(r[3] or 0),
        "Rate (₹)": float(r[4] or 0),
        "Amount (₹)": float(r[3] or 0) * float(r[4] or 0),
        "Note": r[5] or "",
    } for r in rows]


@st.cache_data(ttl=60)
def get_customer_deliveries_by_date_range(customer_id, start_date, end_date):
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT delivery_date, item_name, quantity, cost_rate, rate, status, note, {_EXTRA}
            FROM deliveries
            WHERE customer_id=:cid AND delivery_date BETWEEN :sd AND :ed
            ORDER BY delivery_date ASC, item_name ASC
        """), {"cid": customer_id, "sd": start_date, "ed": end_date}).fetchall()
    return [{
        "delivery_date": str(r[0]),
        "item_name": r[1],
        "quantity": float(r[2] or 0),
        "extra_qty": float(r[7] or 0),
        "cost_rate": float(r[3] or 0),
        "rate": float(r[4] or 0),
        "status": r[5],
        "note": r[6] or ""
    } for r in rows]


# ---------------------------------------------------------------------------
# CSV exports (cached so a Streamlit rerun doesn't rebuild them on every click)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def export_customers_csv():
    customers = get_customers(include_inactive=True)
    items_map = get_all_customer_items()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Name", "Phone", "Default Items & Qty", "Active", "Created At"])
    for c in customers:
        cid, name, phone, address, active, created = c
        items_str = " | ".join(f"{i} ({q:g})" for i, q in items_map.get(cid, []))
        writer.writerow([cid, name, phone or "", items_str, active, created])
    return out.getvalue().encode("utf-8-sig")


@st.cache_data(ttl=60)
def export_deliveries_csv():
    rows = get_deliveries()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Customer", "Date", "Item Name", "Quantity / Packets", "Selling Rate", "Status", "Note", "Cost Rate", "Extra Qty"])
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


@st.cache_data(ttl=60)
def export_range_deliveries_csv(start_date, end_date):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT d.id, c.name, c.phone, d.delivery_date, d.item_name,
                   d.quantity, COALESCE(d.extra_qty, 0), (d.quantity - COALESCE(d.extra_qty, 0)),
                   d.cost_rate, d.rate,
                   (d.quantity * d.cost_rate), (d.quantity * d.rate), ((d.quantity * d.rate) - (d.quantity * d.cost_rate)),
                   d.status, d.note
            FROM deliveries d JOIN customers c ON c.id=d.customer_id
            WHERE d.delivery_date BETWEEN :sd AND :ed
            ORDER BY d.delivery_date ASC, c.name ASC
        """), {"sd": start_date, "ed": end_date}).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Delivery ID", "Customer Name", "Phone", "Date", "Item / Brand",
                     "Total Quantity", "Extra Quantity", "Normal Quantity",
                     "Cost Rate (₹)", "Sell Rate (₹)", "Total Cost (₹)", "Total Revenue (₹)", "Profit (₹)", "Status", "Note"])
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


@st.cache_data(ttl=60)
def export_extra_report_csv(start_date, end_date):
    rows = get_extra_report(start_date, end_date)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Customer", "Product", "Extra Qty", "Rate (₹)", "Amount (₹)", "Note"])
    for r in rows:
        writer.writerow([r["Date"], r["Customer"], r["Product"], r["Extra Qty"], r["Rate (₹)"], f"{r['Amount (₹)']:.2f}", r["Note"]])
    return out.getvalue().encode("utf-8-sig")


@st.cache_data(ttl=60)
def export_daily_summary_csv(start_date, end_date):
    daily_rows = get_daily_breakdown_by_date_range(start_date, end_date)
    matrix = get_daily_brand_matrix(start_date, end_date)
    out = io.StringIO()
    writer = csv.writer(out)
    headers = ["Date", "Delivered Customers", "No Milk Customers", "Total Delivered Qty", "Extra Qty", "Extra Customers",
               "Total Cost (₹)", "Total Revenue (₹)", "Profit (₹)"] + AVAILABLE_ITEMS
    writer.writerow(headers)
    for row in daily_rows:
        d = row["delivery_date"]
        b_map = matrix.get(d, {})
        brand_qtys = [b_map.get(item, 0.0) for item in AVAILABLE_ITEMS]
        writer.writerow([d, row["delivered_cust"], row["undelivered_cust"], row["delivered_qty"], row["extra_qty"], row["extra_cust"],
                         row["total_cost"], row["total_sell"], row["profit"]] + brand_qtys)
    return out.getvalue().encode("utf-8-sig")


@st.cache_data(ttl=60)
def export_all_customers_monthly_report_csv(month):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Customer ID", "Customer Name", "Phone", "Month", "Total Items / Qty", "Extra Qty",
                     "Total Bill Amount (₹)", "Extra Amount (₹)", "Total Paid (₹)", "Balance Due (₹)"])
    for cid, name, phone, qty, extra, total, extra_total, paid in get_all_monthly_billing(month):
        total, paid = float(total), float(paid)
        writer.writerow([cid, name, phone or "", month, f"{float(qty):.2f}", f"{float(extra):.2f}",
                         f"{total:.2f}", f"{float(extra_total):.2f}", f"{paid:.2f}", f"{total - paid:.2f}"])
    return out.getvalue().encode("utf-8-sig")
