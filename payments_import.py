"""Read a bank / PhonePe / GPay statement (CSV) and work out which customer paid.
No Streamlit / database here: app.py passes in the customers, learned names and balances."""
import csv
import difflib
import io
import re
from datetime import date

import pandas as pd

_DATE_PRIORITY = ["transaction date", "txn date", "date", "value date", "value dt", "time"]
_DESC_KEYS = ["transaction details", "details", "narration", "description", "particulars", "remark",
              "transaction name", "paid to", "received from", "sender", "recipient", "merchant", "to/from", "name", "note"]
_REF_KEYS = ["utr", "transaction id", "txn id", "upi ref", "reference", "ref no", "ref.no", "chq", "ref"]
_BAD_STATUS = ("fail", "declin", "cancel", "pending", "reverse", "refund", "expired")
_STOP = {"mr", "mrs", "ms", "sri", "shri", "smt", "dr", "the", "and", "shop", "stores", "store"}
_HANDLES = {"upi", "cr", "dr", "imps", "neft", "rtgs", "okaxis", "okhdfcbank", "okicici", "oksbi", "ybl", "ibl", "axl",
            "paytm", "sbi", "hdfc", "icici", "axis", "payment", "from", "phonepe", "gpay", "google", "pay", "bank", "mob", "ib"}


# ----------------------------------------------------------------------------- reading the file
def _decode(raw):
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


def read_statement(raw):
    """bytes -> DataFrame of strings. Skips the bank's title lines above the real header row."""
    text = _decode(raw)
    sample = text[:5000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    hdr = 0
    for i, row in enumerate(rows[:40]):
        cells = [c.strip().lower() for c in row]
        filled = [c for c in cells if c]
        has_date = any("date" in c for c in cells)
        has_amt = any(k in c for c in cells for k in ("amount", "credit", "deposit", "debit", "withdraw"))
        if len(filled) >= 3 and has_date and has_amt:
            hdr = i
            break
    header, seen = [], {}
    for j, h in enumerate(rows[hdr] if rows else []):
        h = h.strip() or f"col{j + 1}"
        seen[h] = seen.get(h, 0) + 1
        header.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    data = []
    for row in rows[hdr + 1:]:
        if not any(c.strip() for c in row):
            continue
        row = (row + [""] * len(header))[:len(header)]
        data.append([c.strip() for c in row])
    return pd.DataFrame(data, columns=header)


def detect_columns(df):
    """Guess which column is what. Returns {date, desc (list), credit, debit, amount, type, ref, status}."""
    low = {c: c.lower().strip() for c in df.columns}
    out = {"date": None, "desc": [], "credit": None, "debit": None, "amount": None, "type": None, "ref": None, "status": None}
    for key in _DATE_PRIORITY:
        hit = next((c for c, n in low.items() if n == key), None) or next((c for c, n in low.items() if key in n), None)
        if hit:
            out["date"] = hit
            break
    for c, n in low.items():
        if "balance" in n:
            continue
        if out["credit"] is None and (("credit" in n and "debit" not in n and "type" not in n) or "deposit" in n):
            out["credit"] = c
        elif out["debit"] is None and (("debit" in n and "credit" not in n and "type" not in n) or "withdraw" in n):
            out["debit"] = c
        elif out["amount"] is None and "amount" in n:
            out["amount"] = c
        elif out["type"] is None and (n in ("type", "dr/cr", "cr/dr", "debit/credit", "credit/debit", "transaction type", "cr/dr indicator")):
            out["type"] = c
    for c, n in low.items():
        if "status" in n:
            out["status"] = c
    used = {v for k, v in out.items() if k not in ("desc",) and v}
    for k in _REF_KEYS:
        hit = next((c for c, n in low.items() if k in n and c not in used and "date" not in n), None)
        if hit:
            out["ref"] = hit
            break
    skip = used | ({out["ref"]} if out["ref"] else set())
    desc = [c for c, n in low.items() if c not in skip and any(k in n for k in _DESC_KEYS) and "balance" not in n]
    if not desc:
        desc = [c for c in df.columns if c not in skip and "balance" not in low[c]
                and df[c].astype(str).str.contains(r"[A-Za-z]{3,}", regex=True).mean() > 0.5]
    out["desc"] = desc
    return out


def parse_amount(s):
    """'₹1,234.50' -> 1234.5 ; '(500)' -> -500 ; '500 Dr' -> -500 ; '' -> None"""
    s = str(s or "").strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    neg = s.startswith("(") or s.startswith("-") or bool(re.search(r"\bdr\b\.?$", s, re.I))
    num = re.sub(r"[^0-9.]", "", s.replace(",", ""))
    if num.count(".") > 1 or not num.replace(".", ""):
        return None
    try:
        v = float(num)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s):
    s = str(s or "").strip()
    if not s:
        return None
    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(d):
        d = pd.to_datetime(s, errors="coerce")
    return None if pd.isna(d) else d.date()


def _direction(row, cols, desc):
    """'credit' (money received) / 'debit' / 'unknown'."""
    if cols["credit"] or cols["debit"]:
        cr = parse_amount(row.get(cols["credit"], "")) if cols["credit"] else None
        dr = parse_amount(row.get(cols["debit"], "")) if cols["debit"] else None
        if cr and cr > 0:
            return "credit", cr
        if dr and abs(dr) > 0:
            return "debit", abs(dr)
        return "unknown", None
    amt = parse_amount(row.get(cols["amount"], "")) if cols["amount"] else None
    if amt is None:
        return "unknown", None
    kind = ""
    if cols["type"]:
        kind = str(row.get(cols["type"], "")).lower()
    d = (kind + " " + desc).lower()
    if re.search(r"\b(credit|cr|received|deposit)\b|upi/cr|received from", d):
        return "credit", abs(amt)
    if re.search(r"\b(debit|dr|paid|sent|withdraw)\b|upi/dr|paid to|sent to", d):
        return "debit", abs(amt)
    return ("debit", abs(amt)) if amt < 0 else ("unknown", abs(amt))


def parse_transactions(df, cols):
    """-> (credits, info). credits = [{date, desc, amount, ref, assumed}], info = counts of what was left out."""
    credits, info = [], {"debits": 0, "failed": 0, "no_date_or_amount": 0, "assumed_credit": 0}
    for _, r in df.iterrows():
        row = r.to_dict()
        if cols["status"] and any(b in str(row.get(cols["status"], "")).lower() for b in _BAD_STATUS):
            info["failed"] += 1
            continue
        desc = " ".join(str(row.get(c, "")) for c in cols["desc"]).strip()
        kind, amount = _direction(row, cols, desc)
        d = parse_date(row.get(cols["date"], "")) if cols["date"] else None
        if kind == "debit":
            info["debits"] += 1
            continue
        if amount is None or amount <= 0 or d is None:
            info["no_date_or_amount"] += 1
            continue
        ref = str(row.get(cols["ref"], "")).strip() if cols["ref"] else ""
        if len(ref) < 6 or not ref.strip("0 -"):
            ref = ""
        if kind == "unknown":
            info["assumed_credit"] += 1
        credits.append({"date": d, "desc": desc, "amount": amount, "ref": ref, "assumed": kind == "unknown"})
    return credits, info


# ----------------------------------------------------------------------------- who paid?
def norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))


def extract_payer(desc):
    """Pull the payer's name out of a narration. 'Received from RAMESH K' / 'UPI/CR/4123/RAMESH K/okaxis/..' """
    d = " ".join(str(desc).split())
    m = re.search(r"received from\s+(.+?)(?:\s+(?:utr|ref|upi|txn|transaction|on)\b.*)?$", d, re.I)
    if m:
        return m.group(1).strip()
    if "/" in d:
        for part in d.split("/"):
            p = part.strip()
            if p and re.search(r"[A-Za-z]{3,}", p) and "@" not in p and norm(p) not in _HANDLES and not p.isdigit():
                return p
    for part in re.split(r"[-]", d):
        p = part.strip()
        if re.search(r"[A-Za-z]{3,}", p) and "@" not in p and norm(p) not in _HANDLES:
            if not re.fullmatch(r"(upi|imps|neft)", p, re.I):
                return p
    return d[:50]


def _name_tokens(name):
    name = re.sub(r"^\s*\d+\s*[).\-]\s*", "", str(name))
    return [t for t in re.findall(r"[a-z]{3,}", name.lower()) if t not in _STOP]


def _tok_match(a, b):
    return a == b or (len(a) >= 4 and len(b) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)


def _last10(s):
    digits = re.sub(r"\D", "", str(s or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def match_customer(desc, payer, amount, customers, aliases, balances=None):
    """customers = [(id, name, phone)], aliases = {norm(payer): id}, balances = {id: amount due}
    -> (customer_id or None, how)  how in 'learned' | 'phone' | 'name' | 'ambiguous' | ''"""
    key = norm(payer)
    if key and key in aliases:
        return aliases[key], "learned"
    nums = set(re.findall(r"(?<!\d)(?:91)?([6-9]\d{9})(?!\d)", re.sub(r"[\s-]", "", str(desc))))
    if nums:
        for cid, _, phone in customers:
            if _last10(phone) in nums:
                return cid, "phone"
    dtokens = set(re.findall(r"[a-z]{2,}", (str(payer) + " " + str(desc)).lower()))
    scored = []
    for cid, name, _ in customers:
        ct = _name_tokens(name)
        if not ct:
            continue
        hit = sum(1 for c in ct if any(_tok_match(c, d) for d in dtokens))
        score = hit / len(ct)
        if score >= 0.5 and hit >= 1:
            if balances and abs(balances.get(cid, 0) - amount) < 0.5:
                score += 0.2  # exact outstanding amount: strong hint, mainly breaks ties
            scored.append((score, cid))
    if not scored:
        return None, ""
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        return None, "ambiguous"
    return scored[0][1], "name"


def month_add(year, month, delta):
    n = year * 12 + (month - 1) + delta
    return n // 12, n % 12 + 1


def suggest_month(cid, pay_date, due_by_month):
    """Oldest month (up to 3 months back from the payment) that still has a balance; otherwise the month before
    the payment (bills are usually paid after the month ends). due_by_month = {'2026-09': {cid: due}}"""
    y, m = pay_date.year, pay_date.month
    for back in (3, 2, 1, 0):
        yy, mm = month_add(y, m, -back)
        if due_by_month.get(f"{yy:04d}-{mm:02d}", {}).get(cid, 0) > 0.5:
            return f"{yy:04d}-{mm:02d}"
    yy, mm = month_add(y, m, -1)
    return f"{yy:04d}-{mm:02d}"
