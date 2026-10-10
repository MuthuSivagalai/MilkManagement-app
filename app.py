import html
import re
import streamlit as st
import streamlit.components.v1 as components
import calendar
import pandas as pd
from datetime import date, datetime
import urllib.parse
from database import (
    init_db, refresh_items, add_item, AVAILABLE_ITEMS, natural_sort_key, item_code, update_customer, get_item_rates, set_item_rates, add_customer,
    delete_customer, get_customers, get_customer, get_all_customer_items,
    get_deliveries_map_for_date, save_daily_deliveries,
    get_monthly_summary, get_all_month_items, get_all_monthly_billing, add_payment, get_payments,
    get_dashboard_stats, get_item_breakdown_by_date_range, get_daily_breakdown_by_date_range,
    get_customer_date_totals, get_extra_report, get_all_month_daily,
    export_range_deliveries_csv, export_daily_summary_csv, export_extra_report_csv,
    export_all_customers_monthly_report_csv,
    rename_item, get_settings_by_prefix, set_settings, get_item_tamil_names, set_item_tamil_name,
    add_payments_bulk, get_payments_between, get_payer_aliases, save_payer_aliases, delete_payment,
    get_existing_txn_refs, get_saved_dates, get_no_milk_customers
)
from tamil_text import (STR as _STR, DEFAULT_MSG, tamil_item, has_untranslated_words, ta_month_label, ta_short_date)
from payments_import import (read_statement, detect_columns, parse_transactions, extract_payer, match_customer,
                             suggest_month, month_add, norm as norm_payer)

st.set_page_config(page_title="Milk & Curd Delivery Management", page_icon="🥛", layout="wide")
init_db()  # cached: creates / migrates tables only once per server start
refresh_items()  # built-in items + items added by admin

# ---------------- Credentials Config ----------------
USER_CREDENTIALS = {
    "admin": "admin123",
    "muthu": "muthu123",
    "pechimuthu": "pechi2026",
    "staff": "staff123"
}

DEFAULT_RATE = {"cost_price": 20.0, "sell_price": 25.0}

# Only these users can add new items / brands (Item Rates page)
ADMIN_USERS = ["admin"]

# ---------------- Bill / receipt settings (edit these) ----------------
BILL_TITLE = "Aavin / Nanjil Milk & Curd"
BILL_TITLE_TA = "ஆவின் / நஞ்சில் பால் & தயிர்"
UPI_NUMBER = "9489002466"
UPI_NAME = "Pechimuthu"
CONTACT_NUMBERS = "8838594492 / 9489002466"
SLIPS_PER_PAGE = 8  # 2 columns x 4 rows on A4


def esc(x):
    return html.escape(str(x))


def _m(x):
    """Rupees without decimals when whole (56), with 2 decimals only if there really are paise (56.50)."""
    x = float(x or 0)
    return f"{x:,.0f}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}"


def num_cfg(df):
    """column_config that shows numbers without trailing zeros (130 instead of 130.000000)."""
    return {c: st.column_config.NumberColumn(format="%.8g") for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])}


def reset_daily_sheets():
    """Customer defaults changed -> any not-yet-saved daily sheet must be rebuilt from the new defaults."""
    for k in [k for k in st.session_state if k.startswith("daily_df_")]:
        del st.session_state[k]
    for k in [k for k in st.session_state if k.startswith("daily_ver_")]:
        st.session_state[k] += 1  # new editor key, so old cell edits are not re-applied


def purge_item_widgets():
    """An item was renamed: forget every widget / sheet that still holds the old name."""
    reset_daily_sheets()
    for pre in ("cust_add_item_", "e_item_", "edit_items_", "add_extra_prod"):
        for k in [k for k in st.session_state if k.startswith(pre)]:
            del st.session_state[k]
    st.session_state.pop("add_cust_items", None)


def drop_empty_extra_rows(df, name_to_id, default_map):
    """A row with Normal Qty 0 and Extra Qty 0 that is NOT one of the customer's regular products is a leftover of
    an extra that was removed (or set to 0) -> delete it. Regular-product rows with 0 are kept (that is how
    'No Milk' is stored). A customer never loses all his rows, so No Milk is still recorded for him."""
    if df.empty:
        return df
    total = df["Normal Qty"].fillna(0) + df["Extra Qty"].fillna(0)
    drop = []
    for cname, grp in df.groupby("Customer Name", sort=False):
        defaults = {i for i, _ in default_map.get(name_to_id.get(cname), [])}
        zero = [i for i in grp.index if total[i] <= 0 and grp.at[i, "Product"] not in defaults]
        if len(zero) == len(grp):  # nothing else left for this customer: keep one row
            zero = zero[1:]
        drop += zero
    return df.drop(index=drop).reset_index(drop=True)


def clean_phone(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return None


def whatsapp_link(phone, message):
    p = clean_phone(phone)
    if not p:
        return None
    return f"https://api.whatsapp.com/send?phone={p}&text={urllib.parse.quote(message)}"


# Greeting + announcements printed on receipts / WhatsApp. Filled from the database by receipt_message_panel().
RCFG = {"ta": {"greeting": "", "notes": []}, "en": {"greeting": "", "notes": []}}
ITEM_TA = {}  # Tamil names typed by the owner for items (Item Rates -> Edit item name)


def S(lang, key, **kw):
    s_ = _STR[lang][key]
    return s_.format(**kw) if kw else s_


def title_of(lang):
    return BILL_TITLE_TA if lang == "ta" else BILL_TITLE


def disp(item, lang):
    """Item name in the receipt language."""
    return tamil_item(item, ITEM_TA) if lang == "ta" else item


def _days(n, lang="en"):
    if lang == "ta":
        return f"{n} {S('ta', 'day_one') if n == 1 else S('ta', 'day_many')}"
    return f"{n} day{'s' if n != 1 else ''}"


def _rate(it):
    return it["amount"] / it["total"] if it["total"] else 0.0


# ---------------- Brand colours (Aavin = blue, Nanjil Red = red, Nanjil Green = green) ----------------
_FALLBACK_COLORS = ["#fde68a", "#e9d5ff", "#fbcfe8", "#a7f3d0", "#bae6fd", "#fed7aa"]


def brand_color(text_):
    s = str(text_).strip()
    if not s:
        return ""
    a, n = "Aavin" in s, "Nanjil" in s
    if a and n:
        return "#fef3c7"  # mixed cell -> amber
    if a:
        return "#dbeafe"
    if n:
        return "#dcfce7" if "Green" in s else "#fee2e2"
    first = s.split()[0]  # a brand added later by the admin gets its own stable colour
    if not first[:1].isalpha():
        return ""
    return _FALLBACK_COLORS[sum(map(ord, first.lower())) % len(_FALLBACK_COLORS)]


def style_brand(df, cols):
    """Colour the given columns of a DataFrame by brand (works for st.dataframe and st.data_editor)."""
    styler = df.style
    apply_fn = getattr(styler, "map", None) or styler.applymap
    return apply_fn(lambda v: f"background-color:{brand_color(v)}" if brand_color(v) else "", subset=cols)


def brand_span(item, lang="en"):
    c = brand_color(item)
    label = esc(disp(item, lang))
    return f"<span style='background:{c};padding:0 4px;border-radius:3px'>{label}</span>" if c else label


def _short_date(d, lang="en"):
    if lang == "ta":
        return ta_short_date(d)
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d %b")


def daily_line(day, lang="en"):
    """'09 Oct: 2 Aavin250 + 1 Nanjil130 = ₹56'  or  '10 Oct: No milk'  (Tamil: item names in Tamil)"""
    if not day["entries"]:
        return f"{_short_date(day['date'], lang)}: {S(lang, 'no_milk')}"
    nm = (lambda i: disp(i, "ta")) if lang == "ta" else item_code
    parts = " + ".join(f"{q:g} {nm(i)}" + (f" (+{e:g} {S(lang, 'extra')})" if e else "") for i, q, e, _ in day["entries"])
    return f"{_short_date(day['date'], lang)}: {parts} = ₹{_m(day['amount'])}"


def whatsapp_message(name, month_label, items, total, paid, daily=None, lang="en"):
    cfg = RCFG[lang]
    lines = []
    if cfg["greeting"]:
        lines += [cfg["greeting"], ""]
    lines += [f"*{title_of(lang)}*", S(lang, "bill_for", month=month_label), f"{S(lang, 'name')}: {name}", ""]
    for it in items:
        lines.append(f"• {disp(it['item'], lang)}: {_days(it['days'], lang)} "
                     f"({it['total']:g} {S(lang, 'pkts')} × ₹{_m(_rate(it))} = ₹{_m(it['amount'])})")
        if it["extra"] > 0:
            lines.append("   (" + S(lang, "incl_extra", n=f"{it['extra']:g}") + ")")
    if daily:
        lines += ["", f"*{S(lang, 'day_by_day')}*"] + [daily_line(d, lang) for d in daily]
    lines += ["", f"*{S(lang, 'total_wa')}: ₹{_m(total)}*"]
    if paid > 0:
        lines += [f"{S(lang, 'paid')}: ₹{_m(paid)}", f"*{S(lang, 'balance')}: ₹{_m(total - paid)}*"]
    lines += ["", "📲 " + S(lang, "upi_msg"), f"*{S(lang, 'upi_line')}: {UPI_NUMBER} ({UPI_NAME})*"]
    if cfg["notes"]:
        lines += ["", f"📢 *{S(lang, 'notes_title')}*"] + [f"✨ {n}" for n in cfg["notes"]]
    lines += ["", f"📞 {S(lang, 'contact')}: {CONTACT_NUMBERS}"]
    return "\n".join(lines)


_RECEIPT_CSS = """
body{font-family:'Noto Sans Tamil','Nirmala UI','Latha',Arial,Helvetica,sans-serif;margin:0;padding:8px;color:#111}
.greet{background:#eef2ff;border-radius:6px;padding:8px 10px;font-size:13px;margin:0 0 10px;text-align:center;font-weight:600}
.notes{background:#fffbeb;border:1px solid #fcd34d;border-radius:6px;padding:6px 10px;font-size:12px;margin:8px 0}
.notes ul{margin:4px 0 0}
.upi{font-size:15px;font-weight:700;color:#0f766e;margin-top:4px}
.card{max-width:640px;margin:auto;border:1.5px solid #4f46e5;border-radius:8px;padding:18px;background:#fff}
h2{margin:0;text-align:center;color:#4f46e5;font-size:20px}
.sub{text-align:center;font-size:13px;margin:4px 0 12px}
hr{border:0;border-top:1px solid #4f46e5;margin:10px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#4f46e5;color:#fff;padding:6px;text-align:left}
td{padding:6px;border-bottom:1px solid #e5e7eb}
.r{text-align:right}.c{text-align:center}
.total{display:flex;justify-content:space-between;font-size:17px;font-weight:700;margin:10px 0}
.total span:last-child{color:#4f46e5}
.pay{background:#f0fdfa;border:1px solid #99f6e4;border-radius:6px;padding:8px;font-size:12px;margin:10px 0}
ul{font-size:12px;padding-left:18px;margin:6px 0}
.foot{font-size:11px;text-align:center;font-style:italic;margin-top:10px}
.act{max-width:640px;margin:10px auto;display:flex;gap:8px}
.act button{flex:1;padding:10px;border:0;border-radius:6px;color:#fff;font-weight:700;font-size:14px;cursor:pointer}
"""

# Buttons under the preview: turn the receipt into a PNG picture, then share / download it.
_RECEIPT_ACTIONS = """
<div class='act'>
<button style='background:#16a34a' onclick='sh()'>📤 Share (WhatsApp)</button>
<button style='background:#4f46e5' onclick='dl()'>📥 Download image</button></div>
<script src='https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'></script>
<script>
async function mkBlob(){
  const c = await html2canvas(document.getElementById('rcpt'), {scale:2, backgroundColor:'#ffffff'});
  return await new Promise(r => c.toBlob(r, 'image/png'));
}
async function dl(){
  try{
    const b = await mkBlob(); const a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = '__FN__.png'; a.click();
  }catch(e){ alert('Could not create the image: ' + e); }
}
async function sh(){
  try{
    const b = await mkBlob(); const f = new File([b], '__FN__.png', {type:'image/png'});
    if(navigator.canShare && navigator.canShare({files:[f]})){
      try{ await navigator.share({files:[f], title:'__TITLE__'}); return; }
      catch(e){ if(e && e.name === 'AbortError') return; }
    }
    alert('Sharing is not available in this browser, so the image is downloaded. Attach it in WhatsApp.');
    dl();
  }catch(e){ alert('Could not create the image: ' + e); }
}
</script>"""


def receipt_html(name, phone, address, month_label, items, total, paid, daily=None, actions=False, filename="receipt", lang="en"):
    cfg = RCFG[lang]
    daily_html = ""
    if daily:
        drows = ""
        for d in daily:
            if d["entries"]:
                what = "<br>".join(f"{q:g} × {brand_span(i, lang)}" + (f" <i>(+{e:g} {S(lang, 'extra')})</i>" if e else "") for i, q, e, _ in d["entries"])
                amt = f"₹{_m(d['amount'])}"
            else:
                what, amt = f"<i>{S(lang, 'no_milk')}</i>", "₹0"
            drows += f"<tr><td>{_short_date(d['date'], lang)}</td><td>{what}</td><td class='r'>{amt}</td></tr>"
        daily_html = (f"<div style='font-weight:700;margin:6px 0'>{S(lang, 'daywise')}</div>"
                      f"<table><tr><th>{S(lang, 'col_date')}</th><th>{S(lang, 'col_items')}</th><th class='r'>{S(lang, 'col_amount')}</th></tr>{drows}</table><hr>")
    rows = ""
    for it in items:
        extra = f" <i>({S(lang, 'incl_extra', n=format(it['extra'], 'g'))})</i>" if it["extra"] > 0 else ""
        rows += (f"<tr><td><b>{brand_span(it['item'], lang)}</b></td>"
                 f"<td class='c'>{_days(it['days'], lang)} ({it['total']:g} {S(lang, 'pkts')}){extra}</td>"
                 f"<td class='r'>₹{_m(_rate(it))}</td><td class='r'>₹{_m(it['amount'])}</td></tr>")
    if not rows:
        rows = f"<tr><td colspan='4' class='c'>{S(lang, 'no_deliveries')}</td></tr>"
    paid_html = ""
    if paid > 0:
        paid_html = (f"<div class='total' style='font-size:14px'><span>{S(lang, 'paid')}</span><span>₹{_m(paid)}</span></div>"
                     f"<div class='total' style='font-size:14px'><span>{S(lang, 'balance')}</span><span>₹{_m(total - paid)}</span></div>")
    greet_html = f"<div class='greet'>{esc(cfg['greeting'])}</div>" if cfg["greeting"] else ""
    notes_html = ""
    if cfg["notes"]:
        notes_html = (f"<div class='notes'><b>📢 {S(lang, 'notes_title')}</b><ul>"
                      + "".join(f"<li>{esc(n)}</li>" for n in cfg["notes"]) + "</ul></div>")
    actions_html = ""
    if actions:
        fn = re.sub(r"[^A-Za-z0-9_-]+", "_", str(filename)).strip("_") or "receipt"
        actions_html = _RECEIPT_ACTIONS.replace("__FN__", fn).replace("__TITLE__", BILL_TITLE.replace("'", ""))
    return f"""<html><head><meta charset='utf-8'><style>{_RECEIPT_CSS}</style></head><body><div class='card' id='rcpt'>
<h2>{esc(title_of(lang))}</h2><div class='sub'>{S(lang, 'monthly_bill', month='<b>' + esc(month_label) + '</b>')}</div>{greet_html}<hr>
<div style='font-size:13px'><b>{S(lang, 'customer_name')}:</b> {esc(name)}<br><b>{S(lang, 'phone')}:</b> {esc(phone or 'N/A')}</div><hr>
<table><tr><th>{S(lang, 'col_product')}</th><th class='c'>{S(lang, 'col_days')}</th><th class='r'>{S(lang, 'col_rate')}</th><th class='r'>{S(lang, 'col_total')}</th></tr>{rows}</table><hr>{daily_html}
<div class='total'><span>{S(lang, 'total_bill')}</span><span>₹{_m(total)}</span></div>{paid_html}
<div class='pay'><b>📲 {S(lang, 'pay_notice')}:</b><br>{esc(S(lang, 'upi_msg'))}<div class='upi'>{S(lang, 'upi_line')}: {esc(UPI_NUMBER)} ({esc(UPI_NAME)})</div></div>
{notes_html}<div style='font-size:12px'><b>{S(lang, 'contact')}:</b> {esc(CONTACT_NUMBERS)}</div>
<div class='foot'>{esc(S(lang, 'footer', num=UPI_NUMBER))}</div></div>{actions_html}</body></html>"""


_SLIP_CSS = """
*{box-sizing:border-box}
body{font-family:'Noto Sans Tamil','Nirmala UI','Latha',Arial,Helvetica,sans-serif;margin:0;background:#e5e7eb;color:#111}
.bar{position:sticky;top:0;background:#1e293b;color:#fff;padding:8px 12px;font-size:13px;display:flex;gap:12px;align-items:center}
.bar button{background:#4f46e5;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-weight:700;cursor:pointer}
.page{width:210mm;height:297mm;padding:8mm;margin:10px auto;background:#fff;display:grid;
      grid-template-columns:1fr 1fr;grid-template-rows:repeat(4,1fr);gap:4mm;box-shadow:0 1px 6px #0004}
.slip{border:1.5px solid #4f46e5;border-radius:6px;padding:2.5mm 3mm;font-size:8.5pt;overflow:hidden;
      display:flex;flex-direction:column}
.ttl{text-align:center;font-weight:700;color:#4f46e5;border-bottom:1px solid #4f46e5;padding-bottom:1mm;margin-bottom:1.5mm}
.nm{font-weight:700;margin-bottom:1mm}.items{flex:1}.ln{margin:.6mm 0}
.tot{display:flex;justify-content:space-between;font-weight:700;border-top:1px solid #4f46e5;padding-top:1mm;margin-top:1mm}
.pay{background:#f0fdfa;border:1px solid #99f6e4;text-align:center;font-size:6.5pt;padding:.8mm;margin-top:1mm}
.ft{text-align:center;font-size:6pt;margin-top:.8mm}
@page{size:A4;margin:0}
@media print{
  body{background:#fff}.bar{display:none}
  .page{margin:0;box-shadow:none;page-break-after:always;break-after:page}
  .page:last-child{page-break-after:auto;break-after:auto}
}
"""


def slip_html(name, items, total, paid, month_label, lang="en"):
    lines = ""
    for it in items:
        extra = f" <i>[{it['extra']:g} {S(lang, 'extra')}]</i>" if it["extra"] > 0 else ""
        lines += (f"<div class='ln'>• <b>{brand_span(it['item'], lang)}:</b> {_days(it['days'], lang)} "
                  f"({it['total']:g} {S(lang, 'pkts')} × ₹{_m(_rate(it))} = ₹{_m(it['amount'])}){extra}</div>")
    paid_line = ""
    if paid > 0:
        paid_line = (f"<div class='tot' style='border:0;font-weight:400'><span>{S(lang, 'paid')} ₹{_m(paid)}</span>"
                     f"<span>{S(lang, 'balance')} ₹{_m(total - paid)}</span></div>")
    notes = " • ".join(RCFG[lang]["notes"])
    notes_line = f"<div class='ft' style='font-weight:700'>📢 {esc(notes[:150])}</div>" if notes else ""
    return (f"<div class='slip'><div class='ttl'>{esc(title_of(lang))} ({esc(month_label)})</div>"
            f"<div class='nm'>{S(lang, 'name')}: {esc(name)}</div><div class='items'>{lines}</div>"
            f"<div class='tot'><span>{S(lang, 'total_wa')}:</span><span>₹{_m(total)}</span></div>{paid_line}"
            f"<div class='pay'>{S(lang, 'upi_line')}: {esc(UPI_NUMBER)} ({esc(UPI_NAME)})<br>{S(lang, 'slip_pay')}</div>{notes_line}"
            f"<div class='ft'>{esc(S(lang, 'slip_footer', num=CONTACT_NUMBERS))}</div></div>")


def slips_document(entries, month_label, lang="en"):
    """entries: [(name, items, total, paid)] -> printable A4 HTML, SLIPS_PER_PAGE per page."""
    pages = ""
    for i in range(0, len(entries), SLIPS_PER_PAGE):
        chunk = entries[i:i + SLIPS_PER_PAGE]
        pages += "<div class='page'>" + "".join(slip_html(n, it, tot, pd_, month_label, lang) for n, it, tot, pd_ in chunk) + "</div>"
    return (f"<html><head><meta charset='utf-8'><title>Bill slips {esc(month_label)}</title><style>{_SLIP_CSS}</style></head><body>"
            f"<div class='bar'><button onclick='window.print()'>🖨️ Print A4</button>"
            f"<span>{len(entries)} slips · {SLIPS_PER_PAGE} per page · In the print dialog set Margins = None</span></div>{pages}</body></html>")

# ---------------- Session State Initialization ----------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "app_lang" not in st.session_state:
    st.session_state["app_lang"] = "English"

# Helper function for manual translation
def t(en_text, ta_text):
    return ta_text if st.session_state.get("app_lang", "English") == "தமிழ்" else en_text

# ---------------- Minimal Clean Styling ----------------
st.markdown("""
<style>
.stApp {
    background: linear-gradient(180deg, #e0e7ff 0%, #f8fafc 260px);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.main-title {
    font-size: 26px;
    font-weight: 700;
    color: #1e293b;
    margin-bottom: 5px;
}
.block-container {
    padding-top: 4rem;
    padding-bottom: 1.5rem;
}
.stButton>button {
    border-radius: 6px;
    font-weight: 600;
}
.main-banner {
    background: linear-gradient(90deg, #4f46e5, #0ea5e9);
    color: #ffffff;
    padding: 14px 22px;
    border-radius: 12px;
    font-size: 26px;
    font-weight: 800;
    box-shadow: 0 4px 14px #4f46e540;
}
[data-testid="stSidebar"] { background: linear-gradient(180deg, #312e81 0%, #4338ca 60%, #0ea5e9 100%); }
[data-testid="stSidebar"] * { color: #ffffff !important; }
[data-testid="stSidebar"] code { color: #1e293b !important; background: #e0e7ff !important; }
[data-testid="stSidebar"] .stButton>button { background: #ffffff25; border: 1px solid #ffffff88; }
[data-testid="stMetric"] {
    background: #ffffff; border-radius: 12px; padding: 14px 16px;
    border-left: 6px solid #4f46e5; box-shadow: 0 2px 8px #0f172a14;
}
[data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetric"] { border-left-color: #0ea5e9; }
[data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetric"] { border-left-color: #10b981; }
[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetric"] { border-left-color: #f59e0b; }
.stApp h3 { color: #3730a3; }
[data-testid="stExpander"] { background: #ffffff; border-radius: 10px; border: 1px solid #c7d2fe; }
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
    background: linear-gradient(90deg, #4f46e5, #7c3aed) !important; border: 0 !important; color: #ffffff !important;
}
.stTabs [aria-selected="true"] { color: #4f46e5 !important; }
@media print {
    body { background: white; color: black; margin: 0; padding: 0; }
    .no-print { display: none !important; }
    header, footer { visibility: hidden !important; display: none !important; }
    .stSidebar { display: none !important; }
    .printable-page { page-break-after: always; page-break-inside: avoid; break-inside: avoid; }
}
</style>
""", unsafe_allow_html=True)

# ---------------- Login Screen ----------------
if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f'<h2>{t("🔐 Login to Delivery System", "🔐 விநியோக அமைப்பில் உள்நுழைக")}</h2>', unsafe_allow_html=True)
        st.markdown("---")
        with st.form("login_form"):
            username = st.text_input(t("Username", "பயனர் பெயர்"))
            password = st.text_input(t("Password", "கடவுச்சொல்"), type="password")
            submitted = st.form_submit_button(t("🔑 Login", "🔑 உள்நுழைக"), type="primary", use_container_width=True)

            if submitted:
                if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.toast(t("✅ Login successful!", "✅ வெற்றிகரமாக உள்நுழைந்துள்ளீர்கள்!"), icon="🎉")
                    st.rerun()
                else:
                    st.error(t("❌ Invalid Username or Password", "❌ தவறான பயனர் பெயர் அல்லது கடவுச்சொல்"))
    st.stop()

# Top Bar Header
top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    st.markdown(f'<div class="main-banner">{t("🥛 Milk & Curd Delivery Management", "🥛 பால் & தயிர் விநியோக மேலாண்மை")}</div>', unsafe_allow_html=True)

with top_col2:
    st.radio("🌐 Language / மொழி", ["English", "தமிழ்"], key="app_lang", horizontal=True)

menu_options_en = ["🏠 Dashboard", "⚙ Item Rates", "👥 Customers", "🥛 Daily Delivery", "🧾 Billing & Receipts", "💵 Payments", "📊 Reports"]
menu_options_ta = ["🏠 டாஷ்போர்டு", "⚙️ பொருள் விலைகள்", "👥 வாடிக்கையாளர்கள்", "🥛 தினசரி விநியோகம்", "🧾 பில் & ரசீதுகள்", "💵 செலுத்திய தொகைகள்", "📊 அறிக்கைகள்"]
menu_keys = ["Dashboard", "Item Rates", "Customers", "Daily Delivery", "Billing & Receipts", "Payments", "Reports"]

with st.sidebar:
    st.markdown(f"👤 **{t('User', 'பயனர்')}:** `{st.session_state.get('username', 'admin')}`")
    if st.button(t("🚪 Logout", "🚪 வெளியேறு"), use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
    st.markdown("---")

menu_selection = st.sidebar.radio("Menu / மெனு", menu_options_ta if st.session_state.app_lang == "தமிழ்" else menu_options_en)
_all_options = dict(zip(menu_options_en, menu_keys)) | dict(zip(menu_options_ta, menu_keys))
menu = _all_options.get(menu_selection, "Reports")


def render_date_range_picker(key_prefix="dash"):
    calc_mode = st.radio(
        t("Calculation Mode / கணக்கீட்டு முறை", "Calculation Mode / கணக்கீட்டு முறை"),
        [
            t("📅 Single Day", "📅 ஒரு நாள் மட்டும்"),
            t("🗓️ Full Month (1 to 30/31)", "🗓️ முழு மாதம் (1 முதல் 30/31 வரை)"),
            t("📆 Custom Date Range", "📆 குறிப்பிட்ட தேதி வரம்பு")
        ],
        horizontal=True,
        key=f"{key_prefix}_mode"
    )

    today = date.today()
    if "Single" in calc_mode or "ஒரு நாள்" in calc_mode:
        selected_date = st.date_input(t("Select Date", "தேதியை தேர்ந்தெடுக்கவும்"), value=today, key=f"{key_prefix}_single_date")
        s_date = selected_date.isoformat()
        e_date = selected_date.isoformat()
        period_label = selected_date.strftime("%d-%b-%Y")
    elif "Full Month" in calc_mode or "முழு மாதம்" in calc_mode:
        col_m, col_y = st.columns(2)
        month_idx = col_m.selectbox(
            t("Select Month", "மாதம்"),
            list(range(1, 13)),
            index=today.month - 1,
            format_func=lambda m: datetime(2000, m, 1).strftime('%B'),
            key=f"{key_prefix}_month_sel"
        )
        year_val = col_y.number_input(t("Select Year", "ஆண்டு"), min_value=2020, max_value=2035, value=today.year, key=f"{key_prefix}_year_sel")
        last_day = calendar.monthrange(year_val, month_idx)[1]

        s_date = f"{year_val:04d}-{month_idx:02d}-01"
        e_date = f"{year_val:04d}-{month_idx:02d}-{last_day:02d}"
        period_label = f"01 to {last_day} {datetime(2000, month_idx, 1).strftime('%B')} {year_val}"
    else:
        col_s, col_e = st.columns(2)
        s_val = col_s.date_input(t("From Date", "தொடங்கும் தேதி"), value=today.replace(day=1), key=f"{key_prefix}_sdate")
        e_val = col_e.date_input(t("To Date", "முடிவடையும் தேதி"), value=today, key=f"{key_prefix}_edate")
        if e_val < s_val:
            st.error(t("'To Date' must be on or after 'From Date'.", "'முடிவடையும் தேதி' தொடக்க தேதிக்குப் பின் இருக்க வேண்டும்."))
            st.stop()
        s_date = s_val.isoformat()
        e_date = e_val.isoformat()
        period_label = f"{s_val.strftime('%d-%b-%Y')} to {e_val.strftime('%d-%b-%Y')}"

    return s_date, e_date, period_label


def _fmt_items(entries):
    """[(item, qty, extra)] -> '2 Aavin250 + 2 Nanjil130 (+1 extra)'."""
    order = {item: i for i, item in enumerate(AVAILABLE_ITEMS)}
    entries = sorted(entries, key=lambda e: order.get(e[0], 999))
    return " + ".join(f"{q:g} {item_code(i)}" + (f" (+{e:g} extra)" if e else "") for i, q, e in entries)


def build_customer_matrix(s_date, e_date, customers_list):
    """Customer x Date table. Each cell shows brand codes, e.g. '2A250 + 2N130'."""
    ids = [c[0] for c in customers_list]
    names = [c[1] for c in customers_list]
    all_dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(s_date, e_date)]
    show_days = len(all_dates) <= 62  # for very long ranges show totals only

    cell, per_item = {}, {}
    total = {cid: 0.0 for cid in ids}
    extra = {cid: 0.0 for cid in ids}
    for cid, d, item, qty, ex in get_customer_date_totals(s_date, e_date):
        cell.setdefault((cid, d), []).append((item, qty, ex))
        pi = per_item.setdefault(cid, {})
        q0, e0 = pi.get(item, (0.0, 0.0))
        pi[item] = (q0 + qty, e0 + ex)
        if cid in total:
            total[cid] += qty
            extra[cid] += ex

    data = {"Customer Name": names}
    if show_days:
        same_month = all_dates[0][:7] == all_dates[-1][:7]
        fmt = "%d" if same_month else "%d %b"
        for d in all_dates:
            label = datetime.strptime(d, "%Y-%m-%d").strftime(fmt)
            data[label] = [_fmt_items(cell.get((cid, d), [])) for cid in ids]
    data["Total"] = [total[cid] for cid in ids]
    data["Extra"] = [extra[cid] for cid in ids]
    data["Items Summary"] = [_fmt_items([(i, q, e) for i, (q, e) in per_item.get(cid, {}).items()]) for cid in ids]
    return pd.DataFrame(data)


def receipt_message_panel(month_key):
    """Asks the owner what to print on this month's receipts (greeting + new brand / offer / notice).
    Saved text is loaded into RCFG, which receipt_html / whatsapp_message / slip_html read."""
    cfg = get_settings_by_prefix("receipt_")
    val = lambda k: cfg[k] if cfg.get(k) is not None else DEFAULT_MSG[k]
    confirmed = cfg.get("receipt_confirmed_month") == month_key
    ITEM_TA.clear()
    ITEM_TA.update(get_item_tamil_names())

    if not confirmed:
        st.warning(t("📢 Anything NEW this month – a new brand, an offer, a holiday / price notice? "
                     "Type it below and press Save. If nothing changed, press 'Keep the same'. It is printed on every receipt & WhatsApp message.",
                     "📢 இந்த மாதம் புதிதாக ஏதாவது உள்ளதா - புதிய பிராண்ட், சலுகை, விடுமுறை / விலை அறிவிப்பு? "
                     "கீழே எழுதி Save அழுத்தவும். மாற்றம் இல்லையெனில் 'Keep the same' அழுத்தவும். இது ஒவ்வொரு ரசீது & வாட்ஸ்அப்பிலும் வரும்."))
    with st.expander(t("📢 Greeting & announcements on receipts / WhatsApp", "📢 ரசீது / வாட்ஸ்அப்பில் வரும் வாழ்த்து & அறிவிப்புகள்"), expanded=not confirmed):
        c_ta, c_en = st.columns(2)
        g_ta = c_ta.text_area("தமிழ் வாழ்த்து (Tamil greeting)", value=val("receipt_greeting_ta"), key=f"rm_gta_{month_key}", height=110)
        n_ta = c_ta.text_area("தமிழ் அறிவிப்புகள் - ஒரு வரிக்கு ஒன்று (Tamil announcements)", value=val("receipt_notes_ta"), key=f"rm_nta_{month_key}", height=150,
                              help="e.g. புதிய பிராண்ட் ... கிடைக்கும் / தீபாவளி விடுமுறை அறிவிப்பு")
        g_en = c_en.text_area("English greeting", value=val("receipt_greeting_en"), key=f"rm_gen_{month_key}", height=110)
        n_en = c_en.text_area("English announcements - one per line", value=val("receipt_notes_en"), key=f"rm_nen_{month_key}", height=150,
                              help="e.g. New brand ... now available")
        b1, b2, _ = st.columns([2, 2, 3])
        if b1.button(t("💾 Save message", "💾 சேமி"), type="primary", key=f"rm_save_{month_key}", use_container_width=True):
            set_settings({"receipt_greeting_ta": g_ta.strip(), "receipt_notes_ta": n_ta.strip(),
                          "receipt_greeting_en": g_en.strip(), "receipt_notes_en": n_en.strip(),
                          "receipt_confirmed_month": month_key})
            st.toast(t("Message saved!", "சேமிக்கப்பட்டது!"), icon="✅")
            st.rerun()
        if not confirmed and b2.button(t("✅ Keep the same", "✅ மாற்றம் இல்லை"), key=f"rm_keep_{month_key}", use_container_width=True):
            set_settings({"receipt_confirmed_month": month_key})
            st.rerun()
        missing_ta = [i for i in AVAILABLE_ITEMS if has_untranslated_words(tamil_item(i, ITEM_TA))]
        if missing_ta:
            st.caption(t("These items have no Tamil name yet (Item Rates → Edit Item Name): ", "இவற்றுக்கு தமிழ் பெயர் இல்லை (Item Rates → Edit Item Name): ") + ", ".join(missing_ta))
    for lg in ("ta", "en"):  # receipts use the SAVED text
        RCFG[lg] = {"greeting": val(f"receipt_greeting_{lg}").strip(),
                    "notes": [ln.strip() for ln in val(f"receipt_notes_{lg}").splitlines() if ln.strip()]}


def statement_import_ui(customers):
    """Upload a bank / PhonePe / GPay CSV -> table of received payments with the customer guessed -> record."""
    msg = st.session_state.pop("stmt_msg", None)
    if msg:
        st.success(msg)
    st.caption(t("Upload the CSV statement from your bank, PhonePe or GPay. Money RECEIVED is matched to customers by name / phone "
                 "(names you confirm once are remembered). Check the table, correct anything wrong, then press Record - nothing is saved before that.",
                 "வங்கி, PhonePe அல்லது GPay CSV ஐ பதிவேற்றவும். வரவு தொகை பெயர் / தொலைபேசி மூலம் வாடிக்கையாளருடன் பொருத்தப்படும். "
                 "அட்டவணையை சரிபார்த்து Record அழுத்தவும் - அதுவரை எதுவும் சேமிக்கப்படாது."))
    up = st.file_uploader(t("Statement file (.csv)", "ஸ்டேட்மெண்ட் கோப்பு (.csv)"), type=["csv", "txt"], key="stmt_file")
    if up is None:
        return
    raw = up.getvalue()
    try:
        df_raw = read_statement(raw)
    except Exception as err:
        st.error(t(f"Could not read this file: {err}", f"கோப்பை படிக்க முடியவில்லை: {err}"))
        return
    if df_raw.empty:
        st.warning(t("The file has no rows.", "கோப்பில் வரிசைகள் இல்லை."))
        return

    fk = f"{up.name}_{up.size}"
    none = "—"
    guess = detect_columns(df_raw)
    all_cols = list(df_raw.columns)
    opts = [none] + all_cols
    ix = lambda c: opts.index(c) if c in opts else 0
    with st.expander(t("⚙️ Columns detected (change only if something looks wrong)", "⚙️ கண்டறிந்த நெடுவரிசைகள் (தவறாக இருந்தால் மட்டும் மாற்றவும்)")):
        c1, c2, c3 = st.columns(3)
        sel = {
            "date": c1.selectbox(t("Date", "தேதி"), opts, index=ix(guess["date"]), key=f"sc_date_{fk}"),
            "amount": c2.selectbox(t("Amount (single column)", "தொகை (ஒரே நெடுவரிசை)"), opts, index=ix(guess["amount"]), key=f"sc_amt_{fk}"),
            "type": c3.selectbox(t("Type (Credit / Debit)", "வகை (Credit / Debit)"), opts, index=ix(guess["type"]), key=f"sc_type_{fk}"),
        }
        c4, c5, c6 = st.columns(3)
        sel["credit"] = c4.selectbox(t("Credit / Deposit column", "வரவு நெடுவரிசை"), opts, index=ix(guess["credit"]), key=f"sc_cr_{fk}")
        sel["debit"] = c5.selectbox(t("Debit / Withdrawal column", "செலவு நெடுவரிசை"), opts, index=ix(guess["debit"]), key=f"sc_dr_{fk}")
        sel["ref"] = c6.selectbox(t("Reference / UTR / Txn ID", "குறிப்பு எண் / UTR"), opts, index=ix(guess["ref"]), key=f"sc_ref_{fk}")
        desc_cols = st.multiselect(t("Details / narration column(s) - used to find the customer name", "விவரம் / narration நெடுவரிசை"),
                                   all_cols, default=guess["desc"], key=f"sc_desc_{fk}")
        st.dataframe(df_raw.head(5), use_container_width=True, hide_index=True)
    cols = {k: (None if v == none else v) for k, v in sel.items()}
    cols["desc"] = desc_cols
    cols["status"] = guess["status"]

    credits, info = parse_transactions(df_raw, cols)
    st.caption(t(f"{len(df_raw)} rows read · {len(credits)} payments received · left out: {info['debits']} money-out, "
                 f"{info['failed']} failed/pending, {info['no_date_or_amount']} without date/amount.",
                 f"{len(df_raw)} வரிகள் · {len(credits)} வரவுகள் · தவிர்த்தவை: {info['debits']} செலவு, "
                 f"{info['failed']} தோல்வி/நிலுவை, {info['no_date_or_amount']} தேதி/தொகை இல்லாதவை."))
    if info["assumed_credit"]:
        st.warning(t(f"In {info['assumed_credit']} rows the file does not say whether money came in or went out - they are treated as RECEIVED. Please check them.",
                     f"{info['assumed_credit']} வரிகளில் வரவா செலவா என்று இல்லை - வரவாக எடுக்கப்பட்டுள்ளது. சரிபார்க்கவும்."))
    if not credits:
        st.info(t("No received payments found. Check the column settings above.", "வரவுகள் எதுவும் இல்லை. மேலுள்ள நெடுவரிசை அமைப்பை சரிபார்க்கவும்."))
        return

    # ---- what is already owed / already recorded ----
    cust_list = [(c[0], c[1], c[2]) for c in customers]
    id_to_name = {c[0]: c[1] for c in customers}
    name_to_id = {n: i for i, n in id_to_name.items()}
    aliases = get_payer_aliases()
    month_keys = set()
    for tx in credits:
        for back in range(0, 4):
            yy, mm = month_add(tx["date"].year, tx["date"].month, -back)
            month_keys.add(f"{yy:04d}-{mm:02d}")
    due_by_month = {mk: {r[0]: float(r[5]) - float(r[7]) for r in get_all_monthly_billing(mk)} for mk in sorted(month_keys)}
    lo = min(tx["date"] for tx in credits).isoformat()
    hi = max(tx["date"] for tx in credits).isoformat()
    known_pay = {(c, d, round(a, 2)) for c, d, a, _ in get_payments_between(lo, hi)}
    known_refs = get_existing_txn_refs(tuple(sorted({tx["ref"] for tx in credits if tx["ref"]})))

    SKIP = t("— skip —", "— தவிர் —")
    HOW = {"learned": t("Matched (remembered)", "பொருத்தம் (நினைவில்)"), "phone": t("Matched (phone)", "பொருத்தம் (போன்)"),
           "name": t("Matched (name)", "பொருத்தம் (பெயர்)")}
    rows, payer_keys, refs = [], [], []
    for tx in credits:
        payer = extract_payer(tx["desc"])
        pm_y, pm_m = month_add(tx["date"].year, tx["date"].month, -1)
        cid, how = match_customer(tx["desc"], payer, tx["amount"], cust_list, aliases, due_by_month.get(f"{pm_y:04d}-{pm_m:02d}"))
        month = suggest_month(cid if cid else -1, tx["date"], due_by_month)
        dup = False
        if tx["ref"] and tx["ref"] in known_refs:
            status, dup = t("Already recorded (same reference)", "ஏற்கனவே பதிவு (அதே குறிப்பு எண்)"), True
        elif cid and (cid, tx["date"].isoformat(), round(tx["amount"], 2)) in known_pay:
            status, dup = t("Looks already recorded", "ஏற்கனவே பதிவானது போல் உள்ளது"), True
        elif cid:
            status = HOW[how]
        elif how == "ambiguous":
            status = t("Several customers fit – pick one", "பல வாடிக்கையாளர்கள் - ஒருவரை தேர்வு செய்யவும்")
        else:
            status = t("No match – pick customer", "பொருத்தம் இல்லை - தேர்வு செய்யவும்")
        method = "Bank Transfer" if re.search(r"neft|imps|rtgs", tx["desc"], re.I) else "UPI"
        rows.append({"Record": bool(cid) and not dup, "Date": tx["date"].isoformat(), "Details": tx["desc"][:90],
                     "Amount (₹)": float(tx["amount"]), "Customer": id_to_name.get(cid, SKIP), "Month": month,
                     "Method": method, "Status": status})
        payer_keys.append(norm_payer(payer))
        refs.append(tx["ref"])

    n_ok = sum(1 for r in rows if r["Record"])
    st.markdown(f"**{len(rows)}** " + t("payments found", "வரவுகள்") + f" · ✅ **{n_ok}** " + t("ready to record (ticked)", "பதிவுக்கு தயார் (டிக் செய்தவை)"))
    ver = st.session_state.setdefault("stmt_ver", 0)
    with st.form(f"stmt_form_{fk}_{ver}"):
        edited = st.data_editor(
            pd.DataFrame(rows),
            column_config={
                "Record": st.column_config.CheckboxColumn(t("Record?", "பதிவு?")),
                "Customer": st.column_config.SelectboxColumn(options=[SKIP] + list(name_to_id), required=True),
                "Month": st.column_config.TextColumn(help="Bill month, YYYY-MM (the oldest unpaid month is suggested)"),
                "Method": st.column_config.SelectboxColumn(options=["UPI", "Cash", "Bank Transfer"], required=True),
                "Amount (₹)": st.column_config.NumberColumn(format="%.8g"),
            },
            disabled=["Date", "Details", "Amount (₹)", "Status"],
            hide_index=True, use_container_width=True, num_rows="fixed", key=f"stmt_editor_{fk}_{ver}")
        go = st.form_submit_button(t("💾 Record ticked payments", "💾 டிக் செய்த தொகைகளை பதிவு செய்"), type="primary", use_container_width=True)

    if go:
        to_save, alias_map, bad = [], {}, 0
        for i, r in enumerate(edited.to_dict("records")):
            if not r["Record"]:
                continue
            mk = str(r["Month"]).strip()
            if r["Customer"] not in name_to_id or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mk):
                bad += 1
                continue
            cid = name_to_id[r["Customer"]]
            to_save.append({"cid": cid, "month": mk, "date": r["Date"], "amount": float(r["Amount (₹)"]), "method": r["Method"],
                            "note": "Statement: " + str(r["Details"])[:80], "ref": refs[i]})
            if len(payer_keys[i]) >= 3:
                alias_map[payer_keys[i]] = cid
        if bad:
            st.error(t(f"{bad} ticked rows have no customer or a wrong month (use YYYY-MM, e.g. 2026-09). Fix them and press Record again.",
                       f"{bad} வரிகளில் வாடிக்கையாளர் இல்லை அல்லது மாதம் தவறு (YYYY-MM). சரிசெய்து மீண்டும் அழுத்தவும்."))
        elif not to_save:
            st.info(t("Nothing ticked.", "எதுவும் டிக் செய்யப்படவில்லை."))
        else:
            saved, skipped = add_payments_bulk(to_save)
            save_payer_aliases(alias_map)
            st.session_state["stmt_ver"] = ver + 1
            total_amt = sum(r["amount"] for r in to_save)
            st.session_state["stmt_msg"] = t(f"✅ {saved} payments recorded (₹{_m(total_amt)}). " + (f"{skipped} skipped - already recorded." if skipped else ""),
                                             f"✅ {saved} தொகைகள் பதிவு செய்யப்பட்டன (₹{_m(total_amt)}). " + (f"{skipped} ஏற்கனவே பதிவானவை." if skipped else ""))
            st.rerun()


# ---------------- Dashboard ----------------
if menu == "Dashboard":
    st.subheader(t("Dashboard Overview", "டாஷ்போர்டு மேலோட்டம்"))
    s_date, e_date, period_label = render_date_range_picker("dash")

    stats = get_dashboard_stats(s_date, e_date)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("Active Customers", "செயலில் உள்ள வாடிக்கையாளர்கள்"), stats["customers"])
    c2.metric(t("Delivered Customers", "பால் பெற்றவர்கள்"), stats["delivered"])
    c3.metric(t("No Milk Customers", "பால் வாங்காதவர்கள்"), stats["no_milk"])
    c4.metric(t("Total Quantity (Pkts)", "மொத்த அளவு"), f'{stats["litres"]:g}')

    st.markdown("---")
    f1, f2, f3 = st.columns(3)
    f1.metric(t("Total Cost (₹)", "மொத்த வாங்கிய விலை (₹)"), f"₹{_m(stats['total_cost'])}")
    f2.metric(t("Total Revenue (₹)", "மொத்த விற்பனை (₹)"), f"₹{_m(stats['total_sell'])}")
    f3.metric(t("Net Profit Earned (₹)", "நிகர லாபம் (₹)"), f"₹{_m(stats['profit'])}")

    x1, x2, x3 = st.columns(3)
    x1.metric(t("➕ Extra Packets", "➕ கூடுதல் பாக்கெட்டுகள்"), f"{stats['extra_qty']:g}")
    x2.metric(t("➕ Extra Revenue (₹)", "➕ கூடுதல் விற்பனை (₹)"), f"₹{_m(stats['extra_sell'])}")
    x3.metric(t("Customers Who Took Extra", "கூடுதல் வாங்கியவர்கள்"), stats["extra_customers"])

    st.markdown("---")

    # st.tabs() runs the code of EVERY tab on every click. A radio only runs the selected view,
    # so the dashboard now does 1-2 queries instead of 5.
    views = {
        "brand": t("🥛 Brand Breakdown", "🥛 பிராண்ட் சுருக்கம்"),
        "daily": t("📅 Day-by-Day", "📅 நாள் வாரியான"),
        "extra": t("➕ Extra Milk Report", "➕ கூடுதல் பால் அறிக்கை"),
        "customer": t("👥 Customer Monthly Report", "👥 வாடிக்கையாளர் மாதாந்திர அறிக்கை"),
    }
    view = st.radio("View", list(views), format_func=views.get, horizontal=True,
                    key="dash_view", label_visibility="collapsed")

    if view == "brand":
        breakdown = get_item_breakdown_by_date_range(s_date, e_date)
        if breakdown:
            df = pd.DataFrame(breakdown).rename(columns={
                "item_name": "Product", "normal_qty": "Normal Qty", "extra_qty": "Extra Qty",
                "delivered_qty": "Total Qty", "undelivered_count": "No-Milk Entries",
                "total_cost": "Cost (₹)", "total_sell": "Revenue (₹)", "extra_sell": "Extra Revenue (₹)", "profit": "Profit (₹)"
            })
            st.dataframe(style_brand(df, ["Product"]), use_container_width=True, hide_index=True, column_config=num_cfg(df))
        else:
            st.info(t("No deliveries recorded.", "பதிவுகள் இல்லை."))

    elif view == "daily":
        daily_rows = get_daily_breakdown_by_date_range(s_date, e_date)
        if daily_rows:
            df = pd.DataFrame(daily_rows).rename(columns={
                "delivery_date": "Date", "delivered_qty": "Total Qty", "extra_qty": "Extra Qty",
                "delivered_cust": "Delivered Customers", "extra_cust": "Extra Customers",
                "undelivered_cust": "No Milk Customers", "total_cost": "Cost (₹)",
                "total_sell": "Revenue (₹)", "profit": "Profit (₹)"
            })
            st.dataframe(df, use_container_width=True, hide_index=True, column_config=num_cfg(df))
        else:
            st.info(t("No records found.", "பதிவுகள் இல்லை."))

    elif view == "extra":
        extra_rows = get_extra_report(s_date, e_date)
        if extra_rows:
            df = pd.DataFrame(extra_rows)
            st.markdown("**" + t("Extra packets by customer", "வாடிக்கையாளர் வாரியாக கூடுதல் பாக்கெட்டுகள்") + "**")
            pivot = df.pivot_table(index="Customer", columns="Product", values="Extra Qty", aggfunc="sum", fill_value=0)
            pivot["Total Extra"] = pivot.sum(axis=1)
            pivot["Amount (₹)"] = df.groupby("Customer")["Amount (₹)"].sum()
            pivot = pivot.loc[sorted(pivot.index, key=natural_sort_key)].reset_index()
            st.dataframe(pivot, use_container_width=True, hide_index=True, column_config=num_cfg(pivot))

            st.markdown("**" + t("Every extra entry", "ஒவ்வொரு கூடுதல் பதிவு") + "**")
            st.dataframe(df, use_container_width=True, hide_index=True, column_config=num_cfg(df))
        else:
            st.info(t("No extra milk recorded in this period.", "இந்த காலத்தில் கூடுதல் பால் பதிவு இல்லை."))

    else:
        customers_list = get_customers(include_inactive=False)
        if customers_list:
            st.caption(t("Each cell = packets + brand name, e.g. 2 Nanjil130 = 2 packets of Nanjil Red 130ml. "
                         "Blue = Aavin, Red = Nanjil Red, Green = Nanjil Green, Amber = mixed brands.",
                         "ஒவ்வொரு கட்டமும் = பாக்கெட் + பிராண்ட் பெயர். எ.கா. 2 Nanjil130 = 2 நஞ்சில் 130ml. நீலம் = ஆவின், சிவப்பு = நஞ்சில், பச்சை = நஞ்சில் கிரீன்."))
            cust_search = st.text_input(t("🔍 Search customer name", "🔍 வாடிக்கையாளர் பெயர் தேடு"), key="matrix_search").strip().lower()
            if cust_search:
                customers_list = [c for c in customers_list if cust_search in c[1].lower()]
            mdf = build_customer_matrix(s_date, e_date, customers_list)
            color_cols = [c for c in mdf.columns if c not in ("Customer Name", "Total", "Extra")]
            st.dataframe(style_brand(mdf, color_cols), use_container_width=True, hide_index=True, column_config=num_cfg(mdf))

# ---------------- Item Rates ----------------
elif menu == "Item Rates":
    st.subheader(t("Configure Item Rates", "பொருள் அடக்க மற்றும் விற்பனை விலைகள்"))
    item_rates = get_item_rates()

    rates_data = []
    for item in AVAILABLE_ITEMS:
        curr = item_rates.get(item, DEFAULT_RATE)
        rates_data.append({
            "Item Name": item,
            "Cost Price (₹)": float(curr["cost_price"]),
            "Selling Price (₹)": float(curr["sell_price"])
        })

    df_rates = pd.DataFrame(rates_data)

    with st.form("rates_form"):
        edited_rates = st.data_editor(
            df_rates,
            column_config={
                "Item Name": st.column_config.Column(disabled=True),
                "Cost Price (₹)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.8g"),
                "Selling Price (₹)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.8g")
            },
            use_container_width=True,
            hide_index=True
        )
        if st.form_submit_button(t("💾 Save Item Rates", "💾 விலைகளை சேமிக்கவும்"), type="primary"):
            changes = {}
            for _, row in edited_rates.iterrows():
                item = row["Item Name"]
                cp, sp = float(row["Cost Price (₹)"]), float(row["Selling Price (₹)"])
                old = item_rates.get(item, DEFAULT_RATE)
                if abs(old["cost_price"] - cp) > 1e-9 or abs(old["sell_price"] - sp) > 1e-9:
                    changes[item] = (cp, sp)  # only touch what really changed
            if changes:
                set_item_rates(changes)
                st.toast(t("Rates updated successfully!", "விலைகள் புதுப்பிக்கப்பட்டன!"), icon="🎉")
                st.rerun()
            else:
                st.toast(t("No changes to save.", "மாற்றங்கள் இல்லை."), icon="ℹ️")

    st.markdown("---")
    st.markdown("### " + t("➕ Add New Item / Brand", "➕ புதிய பொருள் / பிராண்ட் சேர்க்க"))
    if st.session_state.get("username") in ADMIN_USERS:
        with st.form("add_item_form", clear_on_submit=True):
            n_name = st.text_input(t("New item name *", "புதிய பொருளின் பெயர் *"), placeholder="e.g. Aavin Milk (1 Litre)")
            ci, cj = st.columns(2)
            n_cp = ci.number_input(t("Cost Price (₹)", "அடக்க விலை (₹)"), min_value=0.0, value=20.0, step=0.5)
            n_sp = cj.number_input(t("Selling Price (₹)", "விற்பனை விலை (₹)"), min_value=0.0, value=25.0, step=0.5)
            if st.form_submit_button(t("💾 Add Item", "💾 பொருளை சேர்க்க"), type="primary"):
                try:
                    add_item(n_name, n_cp, n_sp)
                    st.toast(t("Item added!", "பொருள் சேர்க்கப்பட்டது!"), icon="🎉")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
        st.caption(t("Tip: write names like the existing ones, e.g. 'Aavin Milk (1 Litre)'. "
                     "Names containing 'Aavin' or 'Nanjil' get the blue / red colour; shop stock should contain '(Shop)'. "
                     "The new item appears in every product list straight away.",
                     "எ.கா. 'Aavin Milk (1 Litre)'. புதிய பொருள் அனைத்து பட்டியலிலும் உடனே தோன்றும்."))
    else:
        st.info(t("🔒 Only the admin can add new items.", "🔒 புதிய பொருட்களை நிர்வாகி (admin) மட்டுமே சேர்க்க முடியும்."))

    st.markdown("---")
    st.markdown("### " + t("✏️ Edit Item Name", "✏️ பொருளின் பெயரை திருத்து"))
    if st.session_state.get("username") in ADMIN_USERS:
        st.caption(t("The new name replaces the old one everywhere – customer lists, all past deliveries, bills and rates. "
                     "The Tamil name is optional: it is printed on Tamil receipts / WhatsApp (leave blank to use the automatic Tamil).",
                     "புதிய பெயர் எல்லா இடங்களிலும் மாறும் - வாடிக்கையாளர் பட்டியல், பழைய விநியோகங்கள், பில்கள், விலைகள். "
                     "தமிழ் பெயர் விருப்பத்திற்குரியது - தமிழ் ரசீதில் அச்சாகும்."))
        with st.form("rename_item_form", clear_on_submit=True):
            r_old = st.selectbox(t("Item to edit", "திருத்த வேண்டிய பொருள்"), AVAILABLE_ITEMS)
            r_new = st.text_input(t("New item name (leave blank to keep)", "புதிய பெயர் (மாற்ற வேண்டாமெனில் காலியாக விடவும்)"),
                                  placeholder="e.g. Aavin Milk (250 ml)")
            r_ta = st.text_input(t("Tamil name for receipts (optional)", "தமிழ் பெயர் (விருப்பம்)"), placeholder="ஆவின் பால் (250 மி.லி)")
            if st.form_submit_button(t("💾 Save Item Name", "💾 பெயரை சேமி"), type="primary"):
                try:
                    target = r_old
                    new_clean = " ".join(r_new.split())
                    if new_clean and new_clean != r_old:
                        rename_item(r_old, new_clean)
                        target = new_clean
                        purge_item_widgets()
                    if r_ta.strip():
                        set_item_tamil_name(target, r_ta)
                    if target == r_old and not r_ta.strip():
                        st.toast(t("Nothing to change.", "மாற்றம் இல்லை."), icon="ℹ️")
                    else:
                        st.toast(t("Item updated!", "பொருள் புதுப்பிக்கப்பட்டது!"), icon="✅")
                        st.rerun()
                except ValueError as err:
                    st.error(str(err))
    else:
        st.info(t("🔒 Only the admin can edit item names.", "🔒 பொருள் பெயர்களை நிர்வாகி (admin) மட்டுமே திருத்த முடியும்."))

# ---------------- Customers ----------------
elif menu == "Customers":
    st.subheader(t("Customer Management", "வாடிக்கையாளர் மேலாண்மை"))
    tab1, tab2 = st.tabs([t("➕ Add Customer", "➕ வாடிக்கையாளர் சேர்க்க"), t("📋 Customer List", "📋 வாடிக்கையாளர் பட்டியல்")])

    with tab1:
        if "add_cust_items" not in st.session_state:
            st.session_state["add_cust_items"] = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]

        name = st.text_input(t("Customer Name *", "வாடிக்கையாளர் பெயர் *"))
        phone = st.text_input(t("Phone", "தொலைபேசி எண்"))
        active = st.checkbox(t("Active Customer", "செயலில் உள்ள வாடிக்கையாளர்"), value=True)

        st.markdown("### " + t("Assigned Products / Brands", "ஒதுக்கப்பட்ட பொருட்கள் / பிராண்டுகள்"))

        items_to_remove = []
        for idx, item_entry in enumerate(st.session_state["add_cust_items"]):
            c1, c2, c3 = st.columns([4, 2, 1])
            curr_item_idx = AVAILABLE_ITEMS.index(item_entry["item"]) if item_entry["item"] in AVAILABLE_ITEMS else 0

            selected_item = c1.selectbox(f"{t('Product', 'பொருள்')} #{idx+1}", AVAILABLE_ITEMS, index=curr_item_idx, key=f"cust_add_item_{idx}")
            selected_qty = c2.number_input(f"{t('Quantity', 'அளவு')} #{idx+1}", min_value=1, value=max(int(round(item_entry["qty"])), 1), step=1, key=f"cust_add_qty_{idx}")

            st.session_state["add_cust_items"][idx]["item"] = selected_item
            st.session_state["add_cust_items"][idx]["qty"] = selected_qty

            if len(st.session_state["add_cust_items"]) > 1:
                if c3.button("❌", key=f"remove_cust_item_{idx}"):
                    items_to_remove.append(idx)

        if items_to_remove:
            for i in sorted(items_to_remove, reverse=True):
                st.session_state["add_cust_items"].pop(i)
            st.rerun()

        if st.button(t("➕ Add Another Product / Brand", "➕ மற்றொரு பொருள் சேர்க்க")):
            st.session_state["add_cust_items"].append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
            st.rerun()

        st.markdown("---")
        if st.button(t("💾 Save Customer", "💾 சேமிக்கவும்"), type="primary", use_container_width=True):
            if name.strip():
                assigned_items = [(x["item"], x["qty"]) for x in st.session_state["add_cust_items"]]
                add_customer(name.strip(), phone.strip(), "", assigned_items, active)
                reset_daily_sheets()

                st.session_state["add_cust_items"] = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]
                st.toast(t("Customer added successfully!", "வாடிக்கையாளர் சேர்க்கப்பட்டார்!"), icon="🎉")
                st.rerun()
            else:
                st.error(t("Customer name required", "பெயர் கட்டாயம்"))

    with tab2:
        customers = get_customers(include_inactive=True)
        if customers:
            items_map = get_all_customer_items()  # cached single query

            table_data = []
            for c in customers:
                cid, cname, cphone, _, cactive, _ = c
                its = items_map.get(cid, [])
                table_data.append({
                    "ID": cid,
                    "Customer Name": cname,
                    "Phone": cphone or "-",
                    "Default Products / Brands": " | ".join(i for i, _ in its) if its else "None",
                    "Default Quantity": " | ".join(f"{q:g}" for _, q in its) if its else "0",
                    "Active Status": "Active" if cactive == 1 else "Inactive"
                })

            list_search = st.text_input(t("🔍 Search customer name", "🔍 வாடிக்கையாளர் பெயர் தேடு"), key="cust_list_search").strip().lower()
            if list_search:
                table_data = [r for r in table_data if list_search in r["Customer Name"].lower()]
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

            # ---------------- EDIT CUSTOMER ----------------
            st.markdown("---")
            st.markdown("### " + t("✏️ Edit Customer", "✏️ வாடிக்கையாளரை திருத்து"))
            id_to_name = {c[0]: c[1] for c in customers}
            edit_cid = st.selectbox(t("Select customer to edit", "திருத்த வேண்டிய வாடிக்கையாளர்"),
                                    list(id_to_name), format_func=id_to_name.get, key="edit_cust_sel")
            cust = next(c for c in customers if c[0] == edit_cid)
            ver = st.session_state.setdefault(f"edit_ver_{edit_cid}", 0)
            items_key = f"edit_items_{edit_cid}_{ver}"
            if items_key not in st.session_state:
                st.session_state[items_key] = [{"item": i, "qty": q} for i, q in items_map.get(edit_cid, [])] \
                    or [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]
            k = f"{edit_cid}_{ver}"  # widget keys change after each save => fields reload fresh

            e_name = st.text_input(t("Name", "பெயர்"), value=cust[1], key=f"e_name_{k}")
            e_phone = st.text_input(t("Phone", "தொலைபேசி எண்"), value=cust[2] or "", key=f"e_phone_{k}")
            e_active = st.checkbox(t("Active", "செயலில்"), value=(cust[4] == 1), key=f"e_active_{k}")

            st.markdown("**" + t("Customer Products / Brands", "வாடிக்கையாளர் பொருட்கள் / பிராண்டுகள்") + "**")
            edit_items = st.session_state[items_key]
            remove_idx = None
            for idx, entry in enumerate(edit_items):
                c1, c2, c3 = st.columns([4, 2, 1])
                cur = AVAILABLE_ITEMS.index(entry["item"]) if entry["item"] in AVAILABLE_ITEMS else 0
                entry["item"] = c1.selectbox(f"{t('Product', 'பொருள்')} #{idx+1}", AVAILABLE_ITEMS, index=cur, key=f"e_item_{k}_{idx}")
                entry["qty"] = c2.number_input(f"{t('Qty', 'அளவு')} #{idx+1}", min_value=1, value=max(int(round(entry["qty"])), 1), step=1, key=f"e_qty_{k}_{idx}")
                if len(edit_items) > 1 and c3.button("❌", key=f"e_rm_{k}_{idx}"):
                    remove_idx = idx
            if remove_idx is not None:
                edit_items.pop(remove_idx)
                st.rerun()

            if st.button(t("➕ Add Brand/Product", "➕ பிராண்ட் / பொருள் சேர்க்க"), key=f"e_add_{k}"):
                edit_items.append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
                st.rerun()

            st.caption(t("Changes apply to every day that is NOT already saved in Daily Delivery. "
                         "Days already saved keep their old quantities - so to start extra milk from tomorrow, just edit here today.",
                         "சேமிக்கப்படாத நாட்களுக்கு மாற்றம் பொருந்தும். ஏற்கனவே சேமித்த நாட்கள் மாறாது."))
            if st.button(t("💾 Save Customer Changes", "💾 மாற்றங்களை சேமி"), type="primary", key=f"e_save_{k}"):
                names_chosen = [e["item"] for e in edit_items]
                if not e_name.strip():
                    st.error(t("Customer name required", "பெயர் கட்டாயம்"))
                elif len(set(names_chosen)) != len(names_chosen):
                    st.error(t("Same product is added twice - merge them into one row with the total quantity.",
                               "ஒரே பொருள் இரண்டு முறை உள்ளது - ஒரே வரியாக மொத்த அளவுடன் சேர்க்கவும்."))
                else:
                    update_customer(edit_cid, e_name.strip(), e_phone.strip(), (cust[3] or ""),
                                    [(e["item"], e["qty"]) for e in edit_items], e_active)
                    reset_daily_sheets()
                    st.session_state.pop(items_key, None)
                    st.session_state[f"edit_ver_{edit_cid}"] = ver + 1
                    st.toast(t("Customer updated!", "வாடிக்கையாளர் புதுப்பிக்கப்பட்டது!"), icon="✅")
                    st.rerun()

            st.markdown("---")
            with st.expander(t("🗑️ Delete Customer", "🗑️ வாடிக்கையாளரை நீக்கவும்")):
                cid_del = st.selectbox("Select Customer to Delete", list(id_to_name), format_func=id_to_name.get, key="del_cust_sel")
                pin = st.text_input("PIN (1234)", type="password")
                if st.button("Confirm Delete", type="primary"):
                    if pin == "1234":
                        delete_customer(cid_del)
                        reset_daily_sheets()
                        st.toast("Customer Deleted!", icon="🗑️")
                        st.rerun()
                    else:
                        st.error("Invalid PIN")

# ---------------- Daily Delivery (Normal + Extra milk) ----------------
elif menu == "Daily Delivery":
    st.subheader(t("Daily Milk & Curd Delivery", "தினசரி பால் & தயிர் விநியோகம்"))

    col_d, _ = st.columns([2, 2])
    with col_d:
        delivery_date = st.date_input(t("Delivery Date", "விநியோக தேதி"), value=date.today())
    date_str = delivery_date.isoformat()
    customers = get_customers(include_inactive=False)

    # ---- Which dates are already saved? ----
    saved_list = get_saved_dates(delivery_date.strftime("%Y-%m"))
    saved_by_date = {r["date"]: r for r in saved_list}
    if date_str in saved_by_date:
        r_ = saved_by_date[date_str]
        st.success(t(f"✅ {delivery_date:%d-%b-%Y} is SAVED – {r_['delivered']} customers got milk, {r_['no_milk']} no milk, "
                     f"{r_['extra_qty']:g} extra packets. You can edit and save again.",
                     f"✅ {delivery_date:%d-%b-%Y} சேமிக்கப்பட்டது – {r_['delivered']} பேருக்கு பால், {r_['no_milk']} பேருக்கு இல்லை, "
                     f"{r_['extra_qty']:g} கூடுதல் பாக்கெட். மீண்டும் திருத்தி சேமிக்கலாம்."))
    else:
        st.warning(t(f"⚠️ {delivery_date:%d-%b-%Y} is NOT saved yet.", f"⚠️ {delivery_date:%d-%b-%Y} இன்னும் சேமிக்கப்படவில்லை."))
    with st.expander(t(f"📅 Saved dates in {delivery_date:%B %Y}", f"📅 {delivery_date:%B %Y} இல் சேமித்த தேதிகள்")):
        _today = date.today()
        _yr, _mo = delivery_date.year, delivery_date.month
        _last = calendar.monthrange(_yr, _mo)[1]
        _upto = _last if (_yr, _mo) < (_today.year, _today.month) else (_today.day if (_yr, _mo) == (_today.year, _today.month) else 0)
        _missing = [d for d in range(1, _upto + 1) if f"{_yr:04d}-{_mo:02d}-{d:02d}" not in saved_by_date]
        if _missing:
            st.warning(t("Not saved yet: ", "சேமிக்காத தேதிகள்: ") + ", ".join(f"{d:02d}" for d in _missing))
        elif _upto:
            st.success(t("All dates up to today are saved ✅", "இன்று வரை அனைத்து தேதிகளும் சேமிக்கப்பட்டுள்ளன ✅"))
        if saved_list:
            sdf = pd.DataFrame([{
                "Date": datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d %b (%a)"),
                "Delivered Customers": r["delivered"], "No Milk Customers": r["no_milk"],
                "Extra Customers": r["extra_customers"], "Extra Packets": r["extra_qty"],
            } for r in saved_list])
            st.dataframe(sdf, use_container_width=True, hide_index=True, column_config=num_cfg(sdf))
        else:
            st.caption(t("No date saved in this month yet.", "இந்த மாதத்தில் சேமித்த தேதி இல்லை."))

    if not customers:
        st.warning(t("No active customers found.", "செயலில் உள்ள வாடிக்கையாளர்கள் இல்லை."))
    else:
        item_rates = get_item_rates()
        cust_lookup = {c[0]: c[1] for c in customers}
        name_to_id = {name: cid for cid, name in cust_lookup.items()}
        cust_names = list(cust_lookup.values())

        state_key = f"daily_df_{date_str}"
        ver_key = f"daily_ver_{date_str}"

        # drop sheets of other dates so session memory doesn't grow
        for k in [k for k in st.session_state if k.startswith("daily_df_") and k != state_key]:
            del st.session_state[k]

        # DB is only queried when the sheet for this date is first opened (not on every click)
        if state_key not in st.session_state:
            existing_map = get_deliveries_map_for_date(date_str)
            default_map = get_all_customer_items()

            table_data = []
            for cid, name, *_ in customers:
                if cid in existing_map:
                    for r in existing_map[cid]:
                        delivered = r["status"] in ["Delivered", "விநியோகிக்கப்பட்டது"]
                        table_data.append({
                            "Customer Name": name, "Product": r["item"],
                            "Normal Qty": max(r["qty"] - r["extra"], 0.0), "Extra Qty": r["extra"],
                            "Status": "Delivered" if delivered else "No Milk", "Note": r["note"]
                        })
                else:
                    defaults = default_map.get(cid) or [(AVAILABLE_ITEMS[0], 1.0)]
                    for item, qty in defaults:
                        table_data.append({
                            "Customer Name": name, "Product": item,
                            "Normal Qty": float(qty), "Extra Qty": 0.0,
                            "Status": "Delivered", "Note": ""
                        })
            st.session_state[state_key] = pd.DataFrame(table_data)
        st.session_state.setdefault(ver_key, 0)

        # ---- Quick add: customer asked for EXTRA milk ----
        with st.expander(t("➕ Customer asked for EXTRA milk / brand", "➕ வாடிக்கையாளர் கூடுதல் பால் / பிராண்ட் கேட்டார்"), expanded=False):
            st.caption(t("Adds to the 'Extra Qty' of that customer's row (or creates a new row). "
                         "It refreshes the table below, so save other edits first.",
                         "அந்த வாடிக்கையாளரின் 'Extra Qty' இல் சேர்க்கப்படும். மற்ற திருத்தங்களை முதலில் சேமிக்கவும்."))
            col_c, col_p, col_q, col_b = st.columns([3, 3, 2, 2])
            selected_cust_name = col_c.selectbox(t("Customer", "வாடிக்கையாளர்"), cust_names, key="add_extra_cust")
            selected_product = col_p.selectbox(t("Product", "பொருள்"), AVAILABLE_ITEMS, key="add_extra_prod")
            selected_qty = col_q.number_input(t("Extra Qty", "கூடுதல் அளவு"), min_value=1, value=1, step=1, key="add_extra_qty")

            if col_b.button(t("➕ Add Extra", "➕ சேர்க்க"), type="primary", use_container_width=True):
                df = st.session_state[state_key]
                mask = (df["Customer Name"] == selected_cust_name) & (df["Product"] == selected_product)
                if mask.any():
                    idx = df.index[mask][0]
                    df.loc[idx, "Extra Qty"] = float(df.loc[idx, "Extra Qty"] or 0) + float(selected_qty)
                    df.loc[idx, "Status"] = "Delivered"
                else:
                    df = pd.concat([df, pd.DataFrame([{
                        "Customer Name": selected_cust_name, "Product": selected_product,
                        "Normal Qty": 0.0, "Extra Qty": float(selected_qty),
                        "Status": "Delivered", "Note": ""
                    }])], ignore_index=True)
                st.session_state[state_key] = df
                st.session_state[ver_key] += 1  # new editor key => editor reloads from the updated sheet
                st.toast(f"Extra added for {selected_cust_name}!", icon="🎉")
                st.rerun()

        # ---- Remove an extra that was added by mistake ----
        with st.expander(t("🗑️ Remove EXTRA milk (added by mistake)", "🗑️ கூடுதல் பாலை நீக்கு (தவறாக சேர்த்தால்)"), expanded=False):
            df_x = st.session_state[state_key]
            ex_rows = df_x[df_x["Extra Qty"].fillna(0) > 0]
            if ex_rows.empty:
                st.caption(t("There is no extra milk on this sheet.", "இந்த பட்டியலில் கூடுதல் பால் இல்லை."))
            else:
                st.caption(t("Removes the extra packets. A row that was only created for the extra is deleted too. "
                             "You can also set Extra Qty to 0 in the table - it is cleaned up automatically on Save.",
                             "கூடுதல் பாக்கெட்டுகளை நீக்கும். Extra Qty ஐ 0 ஆக்கினாலும் Save செய்யும்போது தானாக நீங்கும்."))
                labels = {i: f"{r['Customer Name']} — {r['Product']} (extra {float(r['Extra Qty']):g})" for i, r in ex_rows.iterrows()}
                pick = st.selectbox(t("Extra entry", "கூடுதல் பதிவு"), list(labels), format_func=labels.get)
                rx1, rx2 = st.columns(2)
                if rx1.button(t("🗑️ Remove this extra", "🗑️ இதை நீக்கு"), type="primary", use_container_width=True):
                    df_x.loc[pick, "Extra Qty"] = 0.0
                    st.session_state[state_key] = drop_empty_extra_rows(df_x, name_to_id, get_all_customer_items())
                    st.session_state[ver_key] += 1
                    st.rerun()
                if rx2.button(t("🗑️ Remove ALL extras on this sheet", "🗑️ அனைத்து கூடுதலையும் நீக்கு"), use_container_width=True):
                    df_x["Extra Qty"] = 0.0
                    st.session_state[state_key] = drop_empty_extra_rows(df_x, name_to_id, get_all_customer_items())
                    st.session_state[ver_key] += 1
                    st.rerun()

        # ---- Quick action: customer takes NO milk today (quantities become 0) ----
        with st.expander(t("🚫 Customer NOT taking milk today (No Milk)", "🚫 இன்று பால் வேண்டாம் (No Milk)"), expanded=False):
            st.caption(t("Sets Normal Qty and Extra Qty to 0 and Status to No Milk for all rows of that customer. "
                         "'Restore' brings back the customer's default quantities. Save other edits first.",
                         "அந்த வாடிக்கையாளரின் அனைத்து அளவுகளும் 0 ஆகும். 'Restore' இயல்பு அளவுகளை மீட்கும். மற்ற திருத்தங்களை முதலில் சேமிக்கவும்."))
            nm_c, nm_b1, nm_b2 = st.columns([5, 2, 2])
            nm_cust = nm_c.selectbox(t("Customer", "வாடிக்கையாளர்"), cust_names, key="no_milk_cust")
            if nm_b1.button(t("🚫 No Milk", "🚫 பால் இல்லை"), type="primary", use_container_width=True):
                df = st.session_state[state_key]
                m_ = df["Customer Name"] == nm_cust
                df.loc[m_, ["Normal Qty", "Extra Qty"]] = 0.0
                df.loc[m_, "Status"] = "No Milk"
                st.session_state[state_key] = df
                st.session_state[ver_key] += 1
                st.rerun()
            if nm_b2.button(t("↩ Restore", "↩ மீட்டமை"), use_container_width=True):
                df = st.session_state[state_key]
                df = df[df["Customer Name"] != nm_cust]
                defaults = get_all_customer_items().get(name_to_id[nm_cust]) or [(AVAILABLE_ITEMS[0], 1.0)]
                restored = pd.DataFrame([{"Customer Name": nm_cust, "Product": i, "Normal Qty": float(q), "Extra Qty": 0.0,
                                          "Status": "Delivered", "Note": ""} for i, q in defaults])
                df = pd.concat([df, restored], ignore_index=True)
                names_ = df["Customer Name"].tolist()
                order_ = sorted(range(len(names_)), key=lambda i: natural_sort_key(names_[i]))
                df = df.iloc[order_].reset_index(drop=True)
                st.session_state[state_key] = df
                st.session_state[ver_key] += 1
                st.rerun()

        st.info(t("💡 Normal Qty = regular supply. Extra Qty = extra packets the customer asked for today "
                  "(billed too, and shown in the Extra Milk Report). Edit freely – nothing is sent until you press Save.",
                  "💡 Normal Qty = வழக்கமான அளவு. Extra Qty = இன்று கூடுதலாக கேட்டது. சேமி பொத்தானை அழுத்தும் வரை எதுவும் சேமிக்கப்படாது."))

        # ---- Search by customer name (filters the sheet; hidden rows are kept and saved untouched) ----
        search_q = st.text_input(t("🔍 Search customer name", "🔍 வாடிக்கையாளர் பெயர் தேடு"), key="daily_search",
                                 placeholder=t("type part of a name…", "பெயரின் ஒரு பகுதியை தட்டச்சு செய்க…")).strip().lower()
        full_df = st.session_state[state_key]
        if search_q:
            view_df = full_df[full_df["Customer Name"].astype(str).str.lower().str.contains(search_q, regex=False)]
            st.caption(t(f"Showing {len(view_df)} of {len(full_df)} rows. Press Save before changing the search, "
                         "otherwise unsaved edits are lost.",
                         f"{len(full_df)} இல் {len(view_df)} வரிகள். தேடலை மாற்றும் முன் சேமிக்கவும்."))
        else:
            view_df = full_df

        # The editor lives in a FORM: typing in cells no longer re-runs the whole app each time.
        with st.form(f"daily_form_{date_str}"):
            edited_df = st.data_editor(
                style_brand(view_df, ["Product"]),
                column_config={
                    "Customer Name": st.column_config.SelectboxColumn(options=cust_names, required=True),
                    "Product": st.column_config.SelectboxColumn(options=AVAILABLE_ITEMS, required=True),
                    "Normal Qty": st.column_config.NumberColumn(min_value=0, max_value=100, step=1, format="%d"),
                    "Extra Qty": st.column_config.NumberColumn(min_value=0, max_value=100, step=1, format="%d"),
                    "Status": st.column_config.SelectboxColumn(options=["Delivered", "No Milk"], required=True),
                    "Note": st.column_config.TextColumn()
                },
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                key=f"daily_editor_{date_str}_{st.session_state[ver_key]}_{search_q}"
            )
            save_clicked = st.form_submit_button(t("💾 Save Today's Delivery", "💾 இன்றைய விநியோகத்தை சேமிக்கவும்"),
                                                 type="primary", use_container_width=True)

        if save_clicked:
            # Merge duplicate (customer, product) rows by summing – the DB allows one row per pair,
            # the old code silently let the last duplicate overwrite the earlier ones.
            merged = {}
            # rows hidden by the search filter + the (possibly edited) visible rows
            hidden_df = full_df.drop(index=view_df.index)
            all_rows_df = pd.concat([hidden_df, pd.DataFrame(edited_df)], ignore_index=True)
            # Extra Qty = 0 (and nothing else on that row) -> the row is removed automatically
            all_rows_df = drop_empty_extra_rows(all_rows_df, name_to_id, get_all_customer_items())
            for _, row in all_rows_df.iterrows():
                c_name, item = row["Customer Name"], row["Product"]
                if c_name not in name_to_id or item not in AVAILABLE_ITEMS:
                    continue
                normal = float(round(row["Normal Qty"])) if pd.notnull(row["Normal Qty"]) else 0.0
                extra = float(round(row["Extra Qty"])) if pd.notnull(row["Extra Qty"]) else 0.0
                status = row["Status"] if pd.notnull(row["Status"]) else "Delivered"
                note = str(row["Note"]).strip() if pd.notnull(row["Note"]) else ""
                if status == "No Milk":
                    normal = extra = 0.0

                m = merged.setdefault((name_to_id[c_name], item), {"normal": 0.0, "extra": 0.0, "notes": []})
                m["normal"] += normal
                m["extra"] += extra
                if note and note not in m["notes"]:
                    m["notes"].append(note)

            rows_to_save = []
            for (cid, item), m in merged.items():
                total = m["normal"] + m["extra"]
                r_info = item_rates.get(item, DEFAULT_RATE)
                rows_to_save.append({
                    "cid": cid, "item": item, "qty": total, "extra": m["extra"],
                    "cp": r_info["cost_price"], "sp": r_info["sell_price"],
                    "status": "Delivered" if total > 0 else "No Milk",
                    "note": "; ".join(m["notes"])
                })

            save_daily_deliveries(date_str, list(name_to_id.values()), rows_to_save)  # 1 transaction

            st.session_state.pop(state_key, None)
            st.session_state[ver_key] += 1  # fresh editor key so old cell edits are not re-applied
            st.toast(t("Delivery saved successfully!", "விநியோகம் சேமிக்கப்பட்டது!"), icon="🎉")
            st.rerun()

        # ---- Report of what is SAVED for this date: extra milk + customers who did not get milk ----
        if date_str in saved_by_date:
            st.markdown("---")
            st.markdown("### " + t(f"📋 Saved report – {delivery_date:%d-%b-%Y}", f"📋 சேமித்த அறிக்கை – {delivery_date:%d-%b-%Y}"))
            saved_extra = get_extra_report(date_str, date_str)
            saved_no_milk = get_no_milk_customers(date_str)
            r_ = saved_by_date[date_str]
            q1, q2, q3, q4 = st.columns(4)
            q1.metric(t("Delivered customers", "பால் பெற்றவர்கள்"), r_["delivered"])
            q2.metric(t("Not delivered", "பால் வழங்காதவர்கள்"), len(saved_no_milk))
            q3.metric(t("➕ Extra packets", "➕ கூடுதல் பாக்கெட்"), f"{r_['extra_qty']:g}")
            q4.metric(t("➕ Extra amount (₹)", "➕ கூடுதல் தொகை (₹)"), f"₹{_m(sum(x['Amount (₹)'] for x in saved_extra))}")
            col_e, col_n = st.columns(2)
            with col_e:
                st.markdown("**" + t("➕ Extra milk added", "➕ கூடுதல் பால் சேர்க்கப்பட்டது") + "**")
                if saved_extra:
                    edf = pd.DataFrame(saved_extra).drop(columns=["Date"])
                    st.dataframe(style_brand(edf, ["Product"]), use_container_width=True, hide_index=True, column_config=num_cfg(edf))
                else:
                    st.info(t("No extra milk on this date.", "இந்த தேதியில் கூடுதல் பால் இல்லை."))
            with col_n:
                st.markdown("**" + t("🚫 Customers NOT delivered", "🚫 பால் வழங்காத வாடிக்கையாளர்கள்") + "**")
                if saved_no_milk:
                    st.dataframe(pd.DataFrame(saved_no_milk), use_container_width=True, hide_index=True)
                else:
                    st.success(t("Everyone got their milk ✅", "அனைவருக்கும் பால் வழங்கப்பட்டது ✅"))
            st.caption(t("This report shows what is saved in the database for this date.", "இது சேமிக்கப்பட்ட தரவின் அறிக்கை."))


# ---------------- Billing & Receipts ----------------
elif menu == "Billing & Receipts":
    st.subheader(t("Monthly Billing & Receipt Generator", "மாதாந்திர பில் & ரசீது"))
    customers = get_customers(include_inactive=True)
    if customers:
        selected_month = st.date_input(t("Select month", "மாதம்"), value=date.today())
        month_key = selected_month.strftime("%Y-%m")
        month_label = selected_month.strftime("%B %Y")

        rcpt_lang = st.radio(t("Receipt / WhatsApp language", "ரசீது / வாட்ஸ்அப் மொழி"), ["ta", "en"],
                             format_func={"ta": "தமிழ்", "en": "English"}.get, horizontal=True, key="rcpt_lang")
        receipt_message_panel(month_key)
        if rcpt_lang == "ta":
            month_label = ta_month_label(selected_month.year, selected_month.month)

        # 2 cached queries serve all three views (items for every customer + paid amounts)
        month_items = get_all_month_items(month_key)
        paid_map = {r[0]: float(r[7]) for r in get_all_monthly_billing(month_key)}
        daily_map = get_all_month_daily(month_key)  # day-by-day deliveries, one query for everyone
        include_daily = st.checkbox(t("📅 Include day-by-day delivery details in receipt & WhatsApp",
                                      "📅 தினசரி விநியோக விவரங்களை ரசீது & வாட்ஸ்அப்பில் சேர்க்க"), value=True)

        def daily_of(cid):
            return daily_map.get(cid, []) if include_daily else None

        def bill_of(cid):
            items = month_items.get(cid, [])
            return items, sum(i["amount"] for i in items), paid_map.get(cid, 0.0)

        # radio (not tabs) => only the selected view is built
        bviews = {
            "single": t("👤 Individual Customer Receipt", "👤 தனிநபர் ரசீது"),
            "queue": t("📋 Bulk WhatsApp Queue", "📋 மொத்த வாட்ஸ்அப்"),
            "slips": t("🖨️ Printable A4 Bill Slips", "🖨️ A4 பில் ஸ்லிப்கள்"),
        }
        bview = st.radio("View", list(bviews), format_func=bviews.get, horizontal=True,
                         key="bill_view", label_visibility="collapsed")

        if bview == "single":
            options = {f"{c[1]}" + ("" if c[2] else " (No phone)"): c[0] for c in customers}
            selected = st.selectbox(t("Select Customer", "வாடிக்கையாளரை தேர்ந்தெடுக்கவும்"), list(options.keys()))
            cid = options[selected]
            info = get_customer(cid)
            items, total, paid = bill_of(cid)

            m1, m2, m3 = st.columns(3)
            m1.metric(t("Total Bill", "மொத்த பில்"), f"₹{_m(total)}")
            m2.metric(t("Paid", "செலுத்தியது"), f"₹{_m(paid)}")
            m3.metric(t("Balance", "நிலுவை"), f"₹{_m(total - paid)}")

            link = whatsapp_link(info[2], whatsapp_message(info[1], month_label, items, total, paid, daily_of(cid), lang=rcpt_lang))
            if link:
                st.link_button(t("💬 Send as Text via WhatsApp", "💬 வாட்ஸ்அப்பில் எழுத்தாக அனுப்பு"), link, type="primary")
                st.caption(t("Opens WhatsApp with the full item-wise bill typed in - you only press Send.",
                             "வாட்ஸ்அப் திறக்கும்; முழு பில் தயாராக இருக்கும் - Send அழுத்தவும்."))
            else:
                st.warning(t("No valid phone number saved for this customer (add it in Customers → Edit Customer).",
                             "இந்த வாடிக்கையாளருக்கு தொலைபேசி எண் இல்லை (Customers → Edit)."))

            st.markdown("#### " + t("📷 Receipt Preview", "📷 ரசீது முன்னோட்டம்"))
            st.caption(t("To send the receipt exactly as shown: press 📤 Share → choose WhatsApp → pick the customer (works on a phone). "
                         "On a computer press 📥 Download image, then attach the picture in WhatsApp.",
                         "ரசீதை அப்படியே அனுப்ப: 📤 Share → WhatsApp → வாடிக்கையாளரை தேர்வு செய்யவும் (மொபைலில்). கணினியில் 📥 Download image அழுத்தி படத்தை WhatsApp இல் இணைக்கவும்."))
            components.html(receipt_html(info[1], info[2], info[3], month_label, items, total, paid, daily_of(cid), actions=True, filename=f"bill_{info[1]}_{month_key}", lang=rcpt_lang), height=780, scrolling=True)

        elif bview == "queue":
            c_a, c_b = st.columns(2)
            only_due = c_a.checkbox(t("Only customers with balance due", "நிலுவை உள்ளவர்கள் மட்டும்"), value=True)
            only_phone = c_b.checkbox(t("Only customers with a phone number", "தொலைபேசி உள்ளவர்கள் மட்டும்"), value=False)

            queue = []
            for c in customers:
                cid, cname, cphone = c[0], c[1], c[2]
                items, total, paid = bill_of(cid)
                if total <= 0 or (only_due and total - paid <= 0):
                    continue
                link = whatsapp_link(cphone, whatsapp_message(cname, month_label, items, total, paid, daily_of(cid), lang=rcpt_lang))
                if only_phone and not link:
                    continue
                queue.append({"Customer": cname, "Phone": cphone or "—", "Bill (₹)": total, "Paid (₹)": paid,
                              "Balance (₹)": total - paid, "WhatsApp": link})
            if queue:
                st.caption(t(f"{len(queue)} customers. Click 📲 Send on a row - WhatsApp opens with the bill ready.",
                             f"{len(queue)} வாடிக்கையாளர்கள். 📲 Send அழுத்தவும்."))
                st.dataframe(pd.DataFrame(queue), use_container_width=True, hide_index=True, height=520,
                             column_config={**num_cfg(pd.DataFrame(queue)), "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="📲 Send")})
            else:
                st.info(t("Nothing to send for this month.", "இந்த மாதம் அனுப்ப எதுவும் இல்லை."))

            st.download_button(
                label=t("⬇️ Download All Reports (CSV)", "⬇️ அனைத்து அறிக்கைகளையும் பதிவிறக்குக"),
                data=export_all_customers_monthly_report_csv(month_key),
                file_name=f"monthly_report_{month_key}.csv", mime="text/csv"
            )

        else:
            st.markdown("### 🖨️ " + t("Printable A4 Bill Slips", "அச்சிடக்கூடிய A4 பில் ஸ்லிப்கள்"))
            c_a, c_b = st.columns([1, 2])
            only_bill = c_a.checkbox(t("Only customers with a bill", "பில் உள்ளவர்கள் மட்டும்"), value=True)
            id_to_name = {c[0]: c[1] for c in customers}
            picked = c_b.multiselect(t("Limit to these customers (empty = all)", "குறிப்பிட்ட வாடிக்கையாளர்கள் (காலி = அனைவரும்)"),
                                     list(id_to_name), format_func=id_to_name.get)
            entries = []
            for c in customers:
                if picked and c[0] not in picked:
                    continue
                items, total, paid = bill_of(c[0])
                if only_bill and total <= 0:
                    continue
                entries.append((c[1], items, total, paid))

            if entries:
                doc = slips_document(entries, month_label, lang=rcpt_lang)
                st.info(t("💡 Click **Print A4** in the preview (or Ctrl+P), set Margins to **None**. "
                          f"{SLIPS_PER_PAGE} slips per page.",
                          f"💡 'Print A4' அழுத்தவும் (அல்லது Ctrl+P), Margins = None. ஒரு பக்கத்தில் {SLIPS_PER_PAGE} ஸ்லிப்கள்."))
                st.download_button(t("⬇️ Download slips (open file → Print)", "⬇️ ஸ்லிப்களை பதிவிறக்கு"),
                                   data=doc.encode("utf-8"), file_name=f"bill_slips_{month_key}.html", mime="text/html")
                components.html(doc, height=900, scrolling=True)
            else:
                st.info(t("No bills to print for this month.", "இந்த மாதம் அச்சிட பில்கள் இல்லை."))

# ---------------- Payments ----------------
elif menu == "Payments":
    st.subheader(t("Payments", "செலுத்திய தொகைகள்"))
    customers = get_customers(include_inactive=True)
    if customers:
        pviews = {"manual": t("✍️ Record a payment", "✍️ தொகையை பதிவு செய்"),
                  "upload": t("📤 Upload bank / PhonePe / GPay statement (CSV)", "📤 வங்கி / PhonePe / GPay ஸ்டேட்மெண்ட் (CSV)")}
        pview = st.radio("View", list(pviews), format_func=pviews.get, horizontal=True, key="pay_view", label_visibility="collapsed")

        if pview == "upload":
            statement_import_ui(customers)
        else:
            selected_month = st.date_input(t("Billing Month", "பில் மாதம்"), value=date.today())
            month_key = selected_month.strftime("%Y-%m")
            options = {f"{c[1]}": c[0] for c in customers}
            selected = st.selectbox(t("Select Customer", "வாடிக்கையாளரை தேர்ந்தெடுக்கவும்"), list(options.keys()))
            cid = options[selected]

            summary = get_monthly_summary(cid, month_key)
            payments = get_payments(cid, month_key)
            paid = sum(float(p[3]) for p in payments)
            balance = summary["total"] - paid

            st.metric(t("Outstanding Balance", "நிலுவைத் தொகை"), f"₹{_m(balance)}")

            with st.form("payment_form"):
                amount = st.number_input(t("Amount (₹)", "தொகை (₹)"), min_value=0.0, value=max(balance, 0.0))
                payment_date = st.date_input(t("Date", "தேதி"), value=date.today())
                method = st.selectbox(t("Method", "முறை"), ["UPI", "Cash", "Bank Transfer"])
                note = st.text_input(t("Note", "குறிப்பு"))

                if st.form_submit_button(t("Record Payment", "பதிவு செய்"), type="primary"):
                    if amount > 0:
                        add_payment(cid, month_key, payment_date.isoformat(), amount, method, note)
                        st.toast(t("Payment Recorded!", "தொகை பதிவு செய்யப்பட்டது!"), icon="💵")
                        st.rerun()

            if payments:
                st.markdown("#### " + t("Payments recorded for this month", "இந்த மாதம் பதிவான தொகைகள்"))
                pdf = pd.DataFrame([{"ID": p[0], "Date": str(p[2]), "Amount (₹)": float(p[3]), "Method": p[4], "Note": p[5] or ""} for p in payments])
                st.dataframe(pdf, use_container_width=True, hide_index=True, column_config=num_cfg(pdf))
                with st.expander(t("🗑️ Delete a payment (recorded by mistake)", "🗑️ தவறான பதிவை நீக்கு")):
                    plabel = {p[0]: f"{p[2]} · ₹{_m(p[3])} · {p[4]}" for p in payments}
                    del_id = st.selectbox(t("Payment", "பதிவு"), list(plabel), format_func=plabel.get)
                    if st.button(t("Delete this payment", "இந்த பதிவை நீக்கு"), type="primary"):
                        delete_payment(del_id)
                        st.toast(t("Payment deleted", "பதிவு நீக்கப்பட்டது"), icon="🗑️")
                        st.rerun()

# ---------------- Reports ----------------
elif menu == "Reports":
    st.subheader(t("Reports & Exports", "அறிக்கைகள்"))
    s_date, e_date, period_label = render_date_range_picker("rep")

    col_ex1, col_ex2, col_ex3 = st.columns(3)
    col_ex1.download_button(
        t("⬇️ Detailed Deliveries CSV", "⬇️ விரிவான விநியோகங்கள் CSV"),
        data=export_range_deliveries_csv(s_date, e_date),
        file_name=f"deliveries_{s_date}_to_{e_date}.csv",
        mime="text/csv",
        type="primary"
    )
    col_ex2.download_button(
        t("⬇️ Day-by-Day Summary CSV", "⬇️ நாள் வாரியான சுருக்கம் CSV"),
        data=export_daily_summary_csv(s_date, e_date),
        file_name=f"summary_{s_date}_to_{e_date}.csv",
        mime="text/csv"
    )
    col_ex3.download_button(
        t("⬇️ Extra Milk Report CSV", "⬇️ கூடுதல் பால் அறிக்கை CSV"),
        data=export_extra_report_csv(s_date, e_date),
        file_name=f"extra_milk_{s_date}_to_{e_date}.csv",
        mime="text/csv"
    )
