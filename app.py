import streamlit as st
import streamlit.components.v1 as components
import calendar
from datetime import date, datetime
import urllib.parse
from database import (
    init_db, AVAILABLE_ITEMS, get_item_rates, set_item_rate, add_customer, update_customer,
    delete_customer, get_customers, get_customer, get_customer_items, save_delivery, clear_deliveries_for_date,
    get_customer_deliveries_for_date, get_deliveries, get_monthly_summary, add_payment, get_payments,
    get_dashboard_stats, export_deliveries_csv, export_customers_csv, export_all_customers_monthly_report_csv,
    get_item_breakdown_by_date_range, get_daily_breakdown_by_date_range, get_daily_brand_matrix,
    export_range_deliveries_csv, export_daily_summary_csv
)

st.set_page_config(page_title="Milk & Curd Delivery Management", page_icon="🥛", layout="wide")
init_db()

# ---------------- Credentials Config ----------------
USER_CREDENTIALS = {
    "admin": "admin123",
    "muthu": "muthu123",
    "pechimuthu": "pechi2026",
    "staff": "staff123"
}

# ---------------- Session State Initialization ----------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "app_lang" not in st.session_state:
    st.session_state["app_lang"] = "English"

# Helper function for manual translation
def t(en_text, ta_text):
    return ta_text if st.session_state.get("app_lang", "English") == "தமிழ்" else en_text

# ---------------- Login Screen ----------------
if not st.session_state["authenticated"]:
    st.markdown("""
    <style>
    .login-header { text-align: center; margin-top: 30px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f'<h2 class="login-header">{t("🔐 Login to Delivery System", "🔐 விநியோக அமைப்பில் உள்நுழைக")}</h2>', unsafe_allow_html=True)
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

# ---------------- Custom CSS ----------------
st.markdown("""
<style>
.main-title {font-size: 32px; font-weight: bold;}
.custom-banner {padding: 12px 20px; border-radius: 8px; background: linear-gradient(90deg, #4CAF50, #2E7D32); color: white; font-weight: 600; margin-bottom: 15px;}
.warn-banner {padding: 12px 20px; border-radius: 8px; background: linear-gradient(90deg, #FF9800, #EF6C00); color: white; font-weight: 600; margin-bottom: 15px;}

@media print {
    body { background: white; color: black; margin: 0; padding: 0; }
    .no-print { display: none !important; }
    header, footer { visibility: hidden !important; display: none !important; }
    .stSidebar { display: none !important; }
    .printable-page { page-break-after: always; page-break-inside: avoid; break-inside: avoid; }
}
</style>
""", unsafe_allow_html=True)

# Top Bar Header with Language Selector
top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    st.markdown(f'<div class="main-title">{t("🥛 Milk & Curd Delivery Management", "🥛 பால் & தயிர் விநியோக மேலாண்மை")}</div>', unsafe_allow_html=True)
    st.caption(t("Multi-Brand Customer Management • Dynamic Add Buttons • Dual Language Billing • Profit Tracking", 
                 "வாடிக்கையாளர் மேலாண்மை • தமிழ் & ஆங்கில பில்லிங் • லாப கணக்கீடு"))

with top_col2:
    st.radio("🌐 Language / மொழி", ["English", "தமிழ்"], key="app_lang", horizontal=True)

menu_options_en = ["🏠 Dashboard", "⚙️️ Item Rates", "👥 Customers", "🥛 Daily Delivery", "🧾 Billing & Receipts", "💵 Payments", "📊 Reports"]
menu_options_ta = ["🏠 டாஷ்போர்டு", "⚙️ பொருள் விலைகள்", "👥 வாடிக்கையாளர்கள்", "🥛 தினசரி விநியோகம்", "🧾 பில் & ரசீதுகள்", "💵 செலுத்திய தொகைகள்", "📊 அறிக்கைகள்"]

# Sidebar Menu & Logout Button
with st.sidebar:
    st.markdown(f"👤 **{t('User', 'பயனர்')}:** `{st.session_state.get('username', 'admin')}`")
    if st.button(t("🚪 Logout", "🚪 வெளியேறு"), use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
    st.markdown("---")

menu_selection = st.sidebar.radio("Menu / மெனு", menu_options_ta if st.session_state.app_lang == "தமிழ்" else menu_options_en)

# Normalize Menu Key
if menu_selection in [menu_options_en[0], menu_options_ta[0]]:
    menu = "Dashboard"
elif menu_selection in [menu_options_en[1], menu_options_ta[1]]:
    menu = "Item Rates"
elif menu_selection in [menu_options_en[2], menu_options_ta[2]]:
    menu = "Customers"
elif menu_selection in [menu_options_en[3], menu_options_ta[3]]:
    menu = "Daily Delivery"
elif menu_selection in [menu_options_en[4], menu_options_ta[4]]:
    menu = "Billing & Receipts"
elif menu_selection in [menu_options_en[5], menu_options_ta[5]]:
    menu = "Payments"
else:
    menu = "Reports"

item_rates = get_item_rates()

# Helper for Date Range Selection
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
        s_val = col_s.date_input(t("From Date (e.g. 1st)", "தொடங்கும் தேதி (எ.கா. 1)"), value=today.replace(day=1), key=f"{key_prefix}_sdate")
        e_val = col_e.date_input(t("To Date (e.g. 30th)", "முடிவடையும் தேதி (எ.கா. 30)"), value=today, key=f"{key_prefix}_edate")
        s_date = s_val.isoformat()
        e_date = e_val.isoformat()
        period_label = f"{s_val.strftime('%d-%b-%Y')} to {e_val.strftime('%d-%b-%Y')}"

    return s_date, e_date, period_label

# ---------------- Dashboard ----------------
if menu == "Dashboard":
    st.subheader(t("Dashboard Overview", "டாஷ்போர்டு மேலோட்டம்"))
    
    s_date, e_date, period_label = render_date_range_picker("dash")
    st.info(f"📆 **{t('Selected Period:', 'தேர்ந்தெடுக்கப்பட்ட காலம்:')}** `{period_label}`")

    stats = get_dashboard_stats(s_date, e_date)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("Active Customers", "செயலில் உள்ள வாடிக்கையாளர்கள்"), stats["customers"])
    c2.metric(t("Delivered Customers", "பால் பெற்றவர்கள்"), stats["delivered"])
    c3.metric(t("No Milk Customers", "பால் வாங்காதவர்கள்"), stats["no_milk"])
    c4.metric(t("Total Quantity (Pkts)", "மொத்த அளவு (பாக்கெட்டுகள்)"), f'{stats["litres"]:.2f}')

    st.markdown("---")
    # Financial Summary Metrics
    f1, f2, f3 = st.columns(3)
    f1.metric(t("Total Cost (₹)", "மொத்த வாங்கிய விலை (₹)"), f"₹{stats['total_cost']:,.2f}")
    f2.metric(t("Total Revenue (₹)", "மொத்த விற்பனை (₹)"), f"₹{stats['total_sell']:,.2f}")
    f3.metric(t("Net Profit Earned (₹)", "நிகர லாபம் (₹)"), f"₹{stats['profit']:,.2f}", delta=f"₹{stats['profit']:,.2f}")

    st.markdown("---")
    
    # Tab layout for Brand Breakdown and Day-by-Day view
    tab_brand, tab_daily = st.tabs([
        t("🥛 Brand & Profit Breakdown", "🥛 பிராண்ட் மற்றும் லாப சுருக்கம்"),
        t("📅 Day-by-Day (1 to 30/31) Calculation", "📅 நாள் வாரியான (1 முதல் 30/31) கணக்கீடு")
    ])

    with tab_brand:
        breakdown = get_item_breakdown_by_date_range(s_date, e_date)
        if breakdown:
            table_data = []
            for b in breakdown:
                table_data.append({
                    t("Product / Brand", "பொருள் / பிராண்ட்"): b["item_name"],
                    t("Delivered Qty (Pkts)", "விநியோகிக்கப்பட்ட அளவு"): f"{b['delivered_qty']:g}",
                    t("Total Cost (₹)", "மொத்த அடக்க விலை (₹)"): f"₹{b['total_cost']:,.2f}",
                    t("Total Revenue (₹)", "மொத்த விற்பனை (₹)"): f"₹{b['total_sell']:,.2f}",
                    t("Net Profit (₹)", "நிகர லாபம் (₹)"): f"₹{b['profit']:,.2f}"
                })
            st.dataframe(table_data, use_container_width=True)
        else:
            st.info(t("No deliveries recorded for this period.", "இந்த காலத்தில் விநியோக பதிவுகள் இல்லை."))

    with tab_daily:
        st.markdown(f"### 🗓 {t('Day-by-Day Breakdown for Selected Range', 'நாள் வாரியான விநியோக விபரம்')}")
        daily_rows = get_daily_breakdown_by_date_range(s_date, e_date)
        matrix = get_daily_brand_matrix(s_date, e_date)

        if daily_rows:
            daily_table = []
            for row in daily_rows:
                d = row["delivery_date"]
                b_map = matrix.get(d, {})
                
                entry = {
                    t("Date", "தேதி"): d,
                    t("Delivered Cust", "பால் பெற்றவர்கள்"): row["delivered_cust"],
                    t("Total Qty (Pkts)", "மொத்த அளவு"): f"{row['delivered_qty']:g}",
                    t("Cost (₹)", "செலவு (₹)"): f"₹{row['total_cost']:,.2f}",
                    t("Revenue (₹)", "விற்பனை (₹)"): f"₹{row['total_sell']:,.2f}",
                    t("Profit (₹)", "லாபம் (₹)"): f"₹{row['profit']:,.2f}"
                }
                
                for item in AVAILABLE_ITEMS:
                    entry[item] = f"{b_map.get(item, 0.0):g}"
                
                daily_table.append(entry)

            st.dataframe(daily_table, use_container_width=True)
        else:
            st.info(t("No day-by-day delivery records found for this period.", "தேர்ந்தெடுக்கப்பட்ட காலத்தில் நாள் வாரியான பதிவுகள் இல்லை."))

    st.markdown(f'<div class="custom-banner">{t("🌟 Tip: Switch to Full Month mode to automatically calculate all days from 1 to 30/31!", "🌟 குறிப்பு: 1 முதல் 30/31 வரையிலான அனைத்து நாட்களையும் கணக்கிட முழு மாதம் முறையைத் தேர்ந்தெடுக்கவும்!")}</div>', unsafe_allow_html=True)

# ---------------- Item Rates ----------------
elif menu == "Item Rates":
    st.subheader(t("Configure Cost & Selling Prices (₹ per item/packet)", "பொருள் அடக்க மற்றும் விற்பனை விலைகளை அமைக்குக (₹)"))
    
    with st.form("item_rates_form"):
        new_rates = {}
        for item in AVAILABLE_ITEMS:
            curr_rates = item_rates.get(item, {"cost_price": 20.0, "sell_price": 25.0})
            st.markdown(f"#### 🥛 {item}")
            col_cp, col_sp = st.columns(2)
            cp_val = col_cp.number_input(f"{t('Cost Price / Buying Price (₹)', 'அடக்க / வாங்கிய விலை (₹)')} - {item}", min_value=0.0, value=float(curr_rates["cost_price"]), step=0.50, key=f"cp_{item}")
            sp_val = col_sp.number_input(f"{t('Selling Price (₹)', 'விற்பனை விலை (₹)')} - {item}", min_value=0.0, value=float(curr_rates["sell_price"]), step=0.50, key=f"sp_{item}")
            new_rates[item] = {"cost_price": cp_val, "sell_price": sp_val}
            st.markdown("---")
        
        submitted = st.form_submit_button(t("💾 Save Cost & Sell Rates", "💾 விலைகளை சேமிக்கவும்"), type="primary")
        if submitted:
            for item, r in new_rates.items():
                set_item_rate(item, r["cost_price"], r["sell_price"])
            st.toast(t("✅ Cost & Selling rates updated successfully!", "✅ அடக்க & விற்பனை விலைகள் புதுப்பிக்கப்பட்டன!"), icon="🎉")
            st.success(t("Rates updated successfully!", "விலைகள் புதுப்பிக்கப்பட்டன!"))
            st.rerun()

# ---------------- Customers ----------------
elif menu == "Customers":
    st.subheader(t("Customer Management", "வாடிக்கையாளர் மேலாண்மை"))
    tab1, tab2 = st.tabs([t("➕ Add Customer", "➕ வாடிக்கையாளர் சேர்க்க"), t("📋 Customer List", "📋 வாடிக்கையாளர் பட்டியல்")])

    with tab1:
        st.markdown(f"### {t('Add New Customer', 'புதிய வாடிக்கையாளரை சேர்க்க')}")
        
        if st.session_state.get("reset_cust_form", False):
            for k in list(st.session_state.keys()):
                if k.startswith("new_cust_") or k.startswith("add_it_") or k.startswith("add_qty_"):
                    del st.session_state[k]
            st.session_state.add_items_list = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]
            st.session_state.reset_cust_form = False

        if "add_items_list" not in st.session_state:
            st.session_state.add_items_list = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]

        name = st.text_input(t("Customer name *", "வாடிக்கையாளர் பெயர் *"), key="new_cust_name")
        phone = st.text_input(t("Phone", "தொலைபேசி எண்"), key="new_cust_phone")
        address = st.text_input(t("Address", "முகவரி"), key="new_cust_address")
        active = st.checkbox(t("Active customer", "செயலில் உள்ள வாடிக்கையாளர்"), value=True, key="new_cust_active")

        st.markdown(f"#### {t('Default Products / Brands', 'வழக்கமான பொருட்கள் / பிராண்டுகள்')}")
        for idx, itm in enumerate(st.session_state.add_items_list):
            c1, c2, c3 = st.columns([3, 2, 1])
            default_idx = AVAILABLE_ITEMS.index(itm["item"]) if itm["item"] in AVAILABLE_ITEMS else 0
            item_sel = c1.selectbox(f"{t('Product', 'பொருள்')} #{idx+1}", AVAILABLE_ITEMS, index=default_idx, key=f"add_it_{idx}")
            qty_inp = c2.number_input(f"{t('Quantity', 'அளவு')} #{idx+1}", min_value=0.0, value=float(itm["qty"]), step=1.0, key=f"add_qty_{idx}")
            
            st.session_state.add_items_list[idx]["item"] = item_sel
            st.session_state.add_items_list[idx]["qty"] = qty_inp

            if len(st.session_state.add_items_list) > 1:
                if c3.button("❌", key=f"rem_add_{idx}"):
                    st.session_state.add_items_list.pop(idx)
                    st.rerun()

        if st.button(t("➕ Add Another Brand/Product", "➕ மற்றொரு பிராண்ட் சேர்க்க"), key="btn_add_brand_new"):
            st.session_state.add_items_list.append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
            st.rerun()

        st.markdown("---")
        if st.button(t("💾 Save Customer", "💾 வாடிக்கையாளரை சேமிக்கவும்"), type="primary", key="btn_save_new_cust"):
            if not name.strip():
                st.error(t("Customer name is required.", "வாடிக்கையாளர் பெயர் அவசியம்."))
            else:
                items_to_save = [(x["item"], x["qty"]) for x in st.session_state.add_items_list]
                add_customer(name.strip(), phone.strip(), address.strip(), items_to_save, active)
                
                st.session_state.reset_cust_form = True
                st.toast(t("✅ Customer saved successfully!", "✅ வாடிக்கையாளர் சேமிக்கப்பட்டார்!"), icon="🎉")
                st.success(t("Customer added successfully.", "வாடிக்கையாளர் வெற்றிகரமாக சேர்க்கப்பட்டார்."))
                st.rerun()

    with tab2:
        customers = get_customers(include_inactive=True)
        if not customers:
            st.info(t("No customers added yet.", "வாடிக்கையாளர்கள் இல்லை."))
        else:
            for c in customers:
                cid, name, phone, address, active, created = c
                cust_items = get_customer_items(cid)
                items_summary = " | ".join([f"{i['item_name']} ({i['normal_qty']:g}/{t('day', 'நாள்')})" for i in cust_items])
                
                with st.expander(f"{name} — {items_summary} {'🟢' if active else '🔴'}"):
                    ename = st.text_input(t("Name", "பெயர்"), value=name, key=f"n_{cid}")
                    ephone = st.text_input(t("Phone", "தொலைபேசி"), value=phone or "", key=f"p_{cid}")
                    eaddress = st.text_input(t("Address", "முகவரி"), value=address or "", key=f"a_{cid}")
                    eactive = st.checkbox(t("Active", "செயலில் உள்ளவர்"), value=bool(active), key=f"ac_{cid}")
                    
                    edit_key = f"edit_items_{cid}"
                    if edit_key not in st.session_state:
                        st.session_state[edit_key] = [{"item": ci["item_name"], "qty": ci["normal_qty"]} for ci in cust_items] if cust_items else [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]

                    st.markdown(f"##### {t('Customer Products / Brands', 'பொருட்கள் / பிராண்டுகள்')}")
                    for idx, itm in enumerate(st.session_state[edit_key]):
                        c1, c2, c3 = st.columns([3, 2, 1])
                        ed_default_idx = AVAILABLE_ITEMS.index(itm["item"]) if itm["item"] in AVAILABLE_ITEMS else 0
                        st.session_state[edit_key][idx]["item"] = c1.selectbox(f"{t('Product', 'பொருள்')} #{idx+1}", AVAILABLE_ITEMS, index=ed_default_idx, key=f"ed_it_{cid}_{idx}")
                        st.session_state[edit_key][idx]["qty"] = c2.number_input(f"{t('Qty', 'அளவு')} #{idx+1}", min_value=0.0, value=float(itm["qty"]), step=1.0, key=f"ed_qty_{cid}_{idx}")
                        if len(st.session_state[edit_key]) > 1:
                            if c3.button("❌", key=f"rem_ed_{cid}_{idx}"):
                                st.session_state[edit_key].pop(idx)
                                st.rerun()

                    if st.button(t("➕ Add Brand/Product", "➕ பொருள் சேர்க்க"), key=f"btn_add_ed_{cid}"):
                        st.session_state[edit_key].append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
                        st.rerun()

                    if st.button(t("💾 Save Customer Changes", "💾 மாற்றங்களை சேமிக்கவும்"), key=f"btn_save_ed_{cid}", type="primary"):
                        items_to_save = [(x["item"], x["qty"]) for x in st.session_state[edit_key]]
                        update_customer(cid, ename.strip(), ephone.strip(), eaddress.strip(), items_to_save, eactive)
                        if edit_key in st.session_state:
                            del st.session_state[edit_key]
                        for k in list(st.session_state.keys()):
                            if k.startswith(f"ed_it_{cid}_") or k.startswith(f"ed_qty_{cid}_"):
                                del st.session_state[k]
                        st.toast(t("✅ Customer updated successfully!", "✅ புதுப்பிக்கப்பட்டது!"), icon="🎉")
                        st.rerun()

                    with st.form(f"delete_form_{cid}"):
                        st.markdown("---")
                        st.markdown(t("🔒 **Secure Deletion:** Enter deletion password (PIN: `1234`) to delete.", "🔒 **பாதுகாப்பான நீக்கம்:** வாடிக்கையாளரை நீக்க கடவுச்சொல்லை உள்ளிடவும் (PIN: `1234`)."))
                        del_password = st.text_input(t("Deletion Password", "கடவுச்சொல்"), type="password", key=f"del_pwd_{cid}")
                        remove = st.form_submit_button(t("🗑️ Delete Customer", "🗑️ நீக்கவும்"))
                        if remove:
                            if del_password == "1234":
                                delete_customer(cid)
                                st.toast(t("⚠️ Customer deleted!", "⚠ வாடிக்கையாளர் நீக்கப்பட்டார்!"), icon="🗑️")
                                st.rerun()
                            else:
                                st.error(t("❌ Incorrect password!", "❌ தவறான கடவுச்சொல்!"))

# ---------------- Daily Delivery ----------------
elif menu == "Daily Delivery":
    st.subheader(t("Daily Milk & Curd Delivery", "தினசரி பால் & தயிர் விநியோகம்"))
    delivery_date = st.date_input(t("Delivery date", "விநியோக தேதி"), value=date.today())
    formatted_delivery_date = delivery_date.strftime("%d-%b-%Y")
    customers = get_customers(include_inactive=False)

    if not customers:
        st.warning(t("Add customers before entering deliveries.", "விநியோகங்களை பதிவு செய்ய முதலில் வாடிக்கையாளர்களை சேர்க்கவும்."))
    else:
        existing_rows = get_deliveries(None, delivery_date.isoformat())
        is_modification = len(existing_rows) > 0

        if is_modification:
            st.markdown(
                f'<div class="warn-banner">{t(f"⚠ Delivery records for {formatted_delivery_date} already exist.", f"⚠ {formatted_delivery_date} தேதிக்கான விநியோக பதிவுகள் ஏற்கனவே உள்ளன.")}</div>', 
                unsafe_allow_html=True
            )
            overwrite_confirm = st.checkbox(t("Yes, I want to modify/update today's delivery records", "ஆம், இன்றைய பதிவுகளை மாற்றியமைக்க விரும்புகிறேன்"), value=True)
        else:
            overwrite_confirm = True

        st.markdown(f"### {t('Today\'s Customers', 'இன்றைய வாடிக்கையாளர்கள்')}")

        daily_state_key = f"daily_rows_{delivery_date.isoformat()}"
        if daily_state_key not in st.session_state:
            st.session_state[daily_state_key] = {}

        d_state = st.session_state[daily_state_key]

        form_data = {}
        for c in customers:
            cid, name, phone, address, active, created = c
            
            if cid not in d_state:
                existing = get_customer_deliveries_for_date(cid, delivery_date.isoformat())
                if existing:
                    d_state[cid] = [{"item": e["item_name"], "qty": float(e["quantity"]), "status": e["status"], "note": e["note"] or ""} for e in existing]
                else:
                    cust_items = get_customer_items(cid)
                    if cust_items:
                        d_state[cid] = [{"item": ci["item_name"], "qty": float(ci["normal_qty"]), "status": "Delivered", "note": ""} for ci in cust_items]
                    else:
                        d_state[cid] = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0, "status": "Delivered", "note": ""}]

            with st.container(border=True):
                st.markdown(f"**{name}**")
                rows_for_cust = d_state[cid]
                updated_rows = []
                
                for idx, row_data in enumerate(rows_for_cust):
                    col1, col2, col3, col4, col5 = st.columns([2.2, 1.1, 1.5, 2, 0.8])
                    item_def_idx = AVAILABLE_ITEMS.index(row_data["item"]) if row_data["item"] in AVAILABLE_ITEMS else 0
                    item_sel = col1.selectbox(t("Product", "பொருள்"), AVAILABLE_ITEMS, index=item_def_idx, key=f"d_item_{cid}_{idx}")
                    qty_inp = col2.number_input(t("Qty", "அளவு"), min_value=0.0, max_value=100.0, value=float(row_data["qty"]), step=1.0, key=f"d_qty_{cid}_{idx}")
                    status_sel = col3.selectbox(t("Status", "நிலை"), [t("Delivered", "Delivered"), t("No Milk", "No Milk")], index=0 if row_data["status"] in ["Delivered", "விநியோகிக்கப்பட்டது"] else 1, key=f"d_stat_{cid}_{idx}")
                    note_inp = col4.text_input(t("Note", "குறிப்பு"), value=row_data["note"], key=f"d_note_{cid}_{idx}")
                    
                    actual_status = "Delivered" if status_sel in ["Delivered", t("Delivered", "Delivered")] else "No Milk"
                    if actual_status == "No Milk":
                        qty_inp = 0.0

                    if len(rows_for_cust) > 1:
                        if col5.button("❌", key=f"d_del_{cid}_{idx}"):
                            continue
                    
                    updated_rows.append({"item": item_sel, "qty": qty_inp, "status": actual_status, "note": note_inp})

                d_state[cid] = updated_rows

                if st.button(t("➕ Add Product", "➕ பொருள் சேர்க்க"), key=f"btn_add_prod_{cid}"):
                    d_state[cid].append({"item": AVAILABLE_ITEMS[0], "qty": 1.0, "status": "Delivered", "note": ""})
                    st.rerun()

                form_data[cid] = d_state[cid]

        if st.button(t("💾 Save Today's Delivery", "💾 இன்றைய விநியோகத்தை சேமிக்கவும்"), type="primary", use_container_width=True):
            if not overwrite_confirm:
                st.error(t("Please check the confirmation box to modify existing records.", "பதிவுகளை மாற்ற உறுதிப்படுத்தல் பெட்டியை சரிபார்க்கவும்."))
            else:
                for cid, items in form_data.items():
                    clear_deliveries_for_date(cid, delivery_date.isoformat())
                    for itm in items:
                        stat = "No Milk" if itm["qty"] <= 0 else itm["status"]
                        q = 0.0 if stat == "No Milk" else itm["qty"]
                        
                        r_info = item_rates.get(itm["item"], {"cost_price": 20.0, "sell_price": 25.0})
                        cost_rate = r_info["cost_price"]
                        sell_rate = r_info["sell_price"]
                        
                        save_delivery(cid, delivery_date.isoformat(), itm["item"], q, cost_rate, sell_rate, stat, itm["note"])

                st.toast(t(f"✅ Delivery saved for {formatted_delivery_date}!", f"✅ {formatted_delivery_date} விநியோகம் சேமிக்கப்பட்டது!"), icon="🎉")
                st.rerun()

# ---------------- Billing & Receipts ----------------
elif menu == "Billing & Receipts":
    st.subheader(t("Monthly Billing & Receipt Generator", "மாதாந்திர பில் & ரசீது உருவாக்கம்"))
    customers = get_customers(include_inactive=True)
    if not customers:
        st.info(t("No customers available.", "வாடிக்கையாளர்கள் இல்லை."))
    else:
        selected_month = st.date_input(t("Select month", "மாதத்தை தேர்ந்தெடுக்கவும்"), value=date.today())
        month_key = selected_month.strftime("%Y-%m")

        tab_indiv, tab_bulk, tab_print = st.tabs([
            t("👤 Individual Customer Receipt", "👤 தனிநபர் ரசீது"), 
            t("📋 Bulk WhatsApp Queue", "📋 மொத்த வாட்ஸ்அப் வரிசை"), 
            t("🖨 Printable A4 Bill Slips", "🖨️ பிரிண்ட் A4 பில் ஸ்லிப்புகள்")
        ])

        with tab_indiv:
            options = {f"{c[1]} ({c[2] or 'No phone'})": c[0] for c in customers}
            selected = st.selectbox(t("Select Customer", "வாடிக்கையாளரை தேர்ந்தெடுக்கவும்"), list(options.keys()))
            cid = options[selected]
            
            customer_info = get_customer(cid)
            summary = get_monthly_summary(cid, month_key)
            payments = get_payments(cid, month_key)
            paid = sum(float(p[3]) for p in payments)
            total = summary["total"]
            balance = total - paid

            delivery_rows = get_deliveries(cid, month_key)
            item_breakdown = {}
            for r in delivery_rows:
                item_name = r[3]
                qty = r[4]
                rate = r[5]
                status = r[6]
                if status in ["Delivered", "விநியோகிக்கப்பட்டது"] and qty > 0:
                    if item_name not in item_breakdown:
                        item_breakdown[item_name] = {"total_qty": 0.0, "days": 0, "rate": rate}
                    item_breakdown[item_name]["total_qty"] += qty
                    item_breakdown[item_name]["days"] += 1

            phone = customer_info[2]
            if phone:
                clean_phone = "".join(filter(str.isdigit, str(phone)))
                if len(clean_phone) == 10:
                    clean_phone = "91" + clean_phone
                elif len(clean_phone) == 11 and clean_phone.startswith("0"):
                    clean_phone = "91" + clean_phone[1:]

                st.markdown(f"### 💬 {t('WhatsApp Text Message', 'வாட்ஸ்அப் குறுஞ்செய்தி')}")
                
                if st.session_state.app_lang == "தமிழ்":
                    wa_text = (
                        f"வணக்கம் {customer_info[1]},\n\n"
                        f"🥛 *ஆவின் / நஞ்சில் பால் & தயிர்*\n"
                        f"மாத பில் / ரசீது (Month: {selected_month.strftime('%B %Y')})\n\n"
                        f"வாடிக்கையாளர் பெயர்: {customer_info[1]}\n"
                        f"தொலைபேசி: {customer_info[2] or 'N/A'} | முகவரி: {customer_info[3] or 'N/A'}\n"
                        f"--------------------------------\n"
                    )
                    for itm_name, data in item_breakdown.items():
                        wa_text += f"• {itm_name}: {data['days']} நாட்கள் ({data['total_qty']:g} பா. × ₹{data['rate']:.2f}) = ₹{data['total_qty']*data['rate']:,.2f}\n"
                    wa_text += (
                        f"--------------------------------\n"
                        f"*மொத்த பில் தொகை (Total Bill Amount): ₹{total:,.2f}*\n"
                        f"--------------------------------\n"
                        f"💡 *பணம் செலுத்த (Payment Notice):*\n"
                        f"தயவுசெய்து GPay / UPI மூலம் பணம் செலுத்தவும், ரொக்கப் பரிவர்த்தனையைத் தவிர்க்கவும்: 9489002466 (பேச்சிமுத்து). செலுத்திய ரசீதை எங்களுக்கு அனுப்பவும்.\n\n"
                        f"• நஞ்சில் (Red) பால் கிடைக்கும்.\n"
                        f"• ஆவின் தயிர் கிடைக்கும்.\n"
                        f"• திருமண விழாக்கள் மற்றும் விசேஷங்களுக்கு பால் வீடு தேடி விநியோகம் செய்யப்படும் (24 மணி நேரத்திற்கு முன் முன்பதிவு தேவை).\n"
                        f"தொடர்புக்கு: 8838594492 / 9489002466\n\n"
                        f"_இது கணினி மூலம் உருவாக்கப்பட்ட பில். ஏதேனும் குறைகள் இருந்தால் 9489002466 என்ற எண்ணைத் தொடர்பு கொள்ளவும்._"
                    )
                else:
                    wa_text = (
                        f"Hello {customer_info[1]},\n\n"
                        f"🥛 *Aavin / Nanjil Milk & Curd*\n"
                        f"Monthly Bill / Receipt (Month: {selected_month.strftime('%B %Y')})\n\n"
                        f"Customer Name: {customer_info[1]}\n"
                        f"Phone: {customer_info[2] or 'N/A'} | Address: {customer_info[3] or 'N/A'}\n"
                        f"--------------------------------\n"
                    )
                    for itm_name, data in item_breakdown.items():
                        wa_text += f"• {itm_name}: {data['days']} days ({data['total_qty']:g} pkts × ₹{data['rate']:.2f}) = ₹{data['total_qty']*data['rate']:,.2f}\n"
                    wa_text += (
                        f"--------------------------------\n"
                        f"*Total Bill Amount: ₹{total:,.2f}*\n"
                        f"--------------------------------\n"
                        f"💡 *Payment Notice:*\n"
                        f"Please pay using GPay / UPI, avoid cash transactions: 9489002466 (Pechimuthu). Kindly share your payment receipt with us.\n\n"
                        f"• Nanjil Red Milk available.\n"
                        f"• Aavin Curd available.\n"
                        f"• Milk door delivery available for marriages & special functions (24-hour advance booking required).\n"
                        f"Contact: 8838594492 / 9489002466\n\n"
                        f"_This is a computer-generated bill. For queries contact 9489002466._"
                    )

                st.text_area(t("Preview WhatsApp Message", "வாட்ஸ்அப் முன்னோட்டம்"), value=wa_text, height=290, key="preview_wa")
                encoded_wa = urllib.parse.quote(wa_text, safe='')
                wa_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_wa}"
                st.link_button(t("💬 Send Bill via WhatsApp", "💬 வாட்ஸ்அப் மூலம் பில் அனுப்பவும்"), wa_url, use_container_width=True)
            else:
                st.warning(t("⚠️ No phone number saved for this customer.", "⚠️ இந்த வாடிக்கையாளருக்கு தொலைபேசி எண் இல்லை."))

            st.markdown("---")
            st.markdown(f"### 📸 {t('High-Quality HTML Receipt Preview', 'உயர்தர HTML ரசீது முன்னோட்டம்')}")
            
            item_rows_html = ""
            for itm_name, data in item_breakdown.items():
                subtotal = data["total_qty"] * data["rate"]
                item_rows_html += f"""
                <tr style="font-weight: bold;">
                    <td style="padding: 10px 5px; border-bottom: 1px solid #eaeaea; color: #111;">{itm_name}</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid #eaeaea; text-align: center; color: #111;">{data['days']} {t('days', 'நாட்கள்')} ({data['total_qty']:g} {t('pkts', 'பா.')})</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid #eaeaea; text-align: right; color: #111;">₹{data['rate']:.2f}</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid #eaeaea; text-align: right; color: #111;">₹{subtotal:,.2f}</td>
                </tr>
                """

            p_title = t("🥛 Aavin / Nanjil Milk & Curd", "🥛 ஆவின் / நஞ்சில் பால் & தயிர்")
            p_sub = t(f"Monthly Bill / Receipt (Month: <b>{selected_month.strftime('%B %Y')}</b>)", f"மாத பில் / ரசீது (Month: <b>{selected_month.strftime('%B %Y')}</b>)")
            p_cname = t("Customer Name", "வாடிக்கையாளர் பெயர்")
            p_phone = t("Phone", "தொலைபேசி")
            p_addr = t("Address", "முகவரி")
            p_prod = t("Product / Brand", "பொருள் / பிராண்ட்")
            p_qty = t("Days & Quantity", "நாட்கள் & அளவு")
            p_price = t("Rate", "விலை")
            p_tot = t("Total", "மொத்தம்")
            p_tot_bill = t("Total Bill Amount", "மொத்த பில் தொகை")
            p_pay_notice = t("💡 Payment Notice:", "💡 பணம் செலுத்த (Payment Notice):")
            p_pay_desc = t("Please pay using GPay / UPI and avoid cash transactions: <b>9489002466</b> (Pechimuthu). Please share payment receipt with us.", 
                           "தயவுசெய்து GPay / UPI மூலம் பணம் செலுத்தவும், ரொக்கப் பரிவர்த்தனையைத் தவிர்க்கவும்: <b>9489002466</b> (பேச்சிமுத்து). பணம் செலுத்திய பின் ரசீதை எங்களுக்கு அனுப்பவும்.")
            p_note1 = t("Nanjil Red Milk available.", "நஞ்சில் (Red) பால் கிடைக்கும்.")
            p_note2 = t("Aavin Curd available.", "ஆவின் தயிர் கிடைக்கும்.")
            p_note3 = t("Milk door delivery available for marriages & special functions (24-hour booking required).", "திருமண விழாக்கள் மற்றும் விசேஷங்களுக்கு பால் வீடு தேடி விநியோகம் செய்யப்படும் (24 மணி நேரத்திற்கு முன் முன்பதிவு தேவை).")
            p_contact = t("Contact:", "தொடர்புக்கு:")
            p_foot = t("This is a computer-generated bill. For any queries, please contact 9489002466.", "இது கணினி மூலம் உருவாக்கப்பட்ட பில். ஏதேனும் குறைகள் இருந்தால் 9489002466 என்ற எண்ணைத் தொடர்பு கொள்ளவும்.")

            receipt_html = f"""
            <div style="border: 2px solid #333; border-radius: 10px; padding: 25px 30px; background-color: #ffffff; font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; box-shadow: 0 2px 8px rgba(0,0,0,0.08); font-weight: bold; color: #000;">
                <h2 style="text-align: center; margin-bottom: 2px; color: #1b5e20; font-weight: 800; font-size: 24px;">{p_title}</h2>
                <p style="text-align: center; color: #333; margin-top: 0; font-size: 14px; font-weight: bold;">{p_sub}</p>

                <hr style="border: 0; border-top: 2px solid #000; margin: 15px 0;">

                <p style="font-size: 15px; color: #000; margin: 8px 0; font-weight: bold;"><b>{p_cname}:</b> {customer_info[1]}</p>
                <p style="font-size: 15px; color: #000; margin: 8px 0; font-weight: bold;"><b>{p_phone}:</b> {customer_info[2] or 'N/A'} | <b>{p_addr}:</b> {customer_info[3] or 'N/A'}</p>

                <hr style="border: 0; border-top: 2px solid #888; margin: 15px 0;">

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px; font-size: 14px; font-weight: bold;">
                    <thead>
                        <tr style="font-weight: 800; color: #000;">
                            <th style="text-align: left; border-bottom: 2px solid #000; padding: 8px 5px;">{p_prod}</th>
                            <th style="text-align: center; border-bottom: 2px solid #000; padding: 8px 5px;">{p_qty}</th>
                            <th style="text-align: right; border-bottom: 2px solid #000; padding: 8px 5px;">{p_price}</th>
                            <th style="text-align: right; border-bottom: 2px solid #000; padding: 8px 5px;">{p_tot}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {item_rows_html if item_rows_html else f'<tr><td colspan="4" style="text-align:center; padding: 15px; color: #000; font-weight: bold;">{t("No delivery records for this month", "இந்த மாதத்தில் விநியோக பதிவுகள் இல்லை")}</td></tr>'}
                    </tbody>
                </table>

                <hr style="border: 0; border-top: 2px solid #000; margin: 15px 0;">

                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 16px; padding: 5px 0; font-weight: 800; color: #000;">
                    <div>{p_tot_bill}:</div>
                    <div style="color: #1b5e20; font-size: 18px;">₹{total:,.2f}</div>
                </div>

                <hr style="border: 0; border-top: 2px solid #000; margin: 15px 0 20px 0;">

                <div style="background-color: #e8f5e9; padding: 12px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; color: #1b5e20; line-height: 1.5; font-weight: bold; border: 1px solid #a5d6a7;">
                    <span style="font-weight: 800;">{p_pay_notice}</span><br>
                    {p_pay_desc}
                </div>

                <ul style="font-size: 12px; color: #000; line-height: 1.6; margin: 0; padding-left: 20px; font-weight: bold;">
                    <li>{p_note1}</li>
                    <li>{p_note2}</li>
                    <li>{p_note3}</li>
                </ul>
                <p style="font-size: 12px; color: #000; margin-top: 8px; margin-bottom: 0; font-weight: bold;"><b>{p_contact}</b> 8838594492 / 9489002466</p>

                <hr style="border: 0; border-top: 1px solid #aaa; margin: 15px 0;">
                <p style="text-align: center; font-size: 11px; color: #333; font-style: italic; margin: 0; font-weight: bold;">{p_foot}</p>
            </div>
            """
            components.html(receipt_html, height=580, scrolling=True)

        with tab_bulk:
            st.markdown(f"### 📥 {t('Bulk Download', 'மொத்த பதிவிறக்கம்')}")
            all_csv_data = export_all_customers_monthly_report_csv(month_key)
            st.download_button(
                label=t("⬇️ Download All Customers Monthly Report (CSV)", "⬇ அனைத்து வாடிக்கையாளர்கள் மாதாந்திர அறிக்கை (CSV)"),
                data=all_csv_data,
                file_name=f"all_customers_milk_report_{month_key}.csv",
                mime="text/csv",
                type="primary"
            )

        with tab_print:
            st.markdown(f"### 🖨️ {t('Printable A4 Bill Slips', 'பிரிண்ட் A4 பில் ஸ்லிப்புகள்')}")
            st.info(t("💡 Press **`Ctrl + P`** in your browser to print. Set margins to **None**.", "💡 அச்சிட உங்கள் உலாவி பக்கத்தில் **`Ctrl + P`** அழுத்தவும்."))
            
            st.markdown("---")
            customer_batches = [customers[i:i + 10] for i in range(0, len(customers), 10)]

            for batch_idx, batch in enumerate(customer_batches):
                st.markdown('<div class="printable-page">', unsafe_allow_html=True)
                rows_data = [batch[i:i + 2] for i in range(0, len(batch), 2)]
                
                for row in rows_data:
                    cols = st.columns(2)
                    for col_idx, c in enumerate(row):
                        cid, name, phone, address, active, _ = c
                        summary = get_monthly_summary(cid, month_key)
                        total = summary["total"]

                        delivery_rows = get_deliveries(cid, month_key)
                        cust_item_breakdown = {}
                        for r in delivery_rows:
                            item_name = r[3]
                            qty = r[4]
                            rate = r[5]
                            status = r[6]
                            if status in ["Delivered", "விநியோகிக்கப்பட்டது"] and qty > 0:
                                if item_name not in cust_item_breakdown:
                                    cust_item_breakdown[item_name] = {"total_qty": 0.0, "days": 0, "rate": rate}
                                cust_item_breakdown[item_name]["total_qty"] += qty
                                cust_item_breakdown[item_name]["days"] += 1

                        slip_items_html = ""
                        for itm_name, data in cust_item_breakdown.items():
                            subtotal = data["total_qty"] * data["rate"]
                            slip_items_html += f"<div style='font-weight: bold; color: #000;'>• {itm_name}: <b>{data['days']} {t('day', 'நாள்')}</b> ({data['total_qty']:g} {t('pkts', 'பா.')} × ₹{data['rate']:.2f} = <b>₹{subtotal:,.2f}</b>)</div>"

                        with cols[col_idx]:
                            slip_html = f"""
                            <div style="border: 2px solid #000; padding: 5px 8px; background: #fff; font-size: 10px; color: #000; font-weight: bold; box-sizing: border-box; margin-bottom: 5px; border-radius: 4px; height: 46mm; display: flex; flex-direction: column; justify-content: space-between;">
                                <div>
                                    <div style="font-weight: 800; text-align: center; font-size: 11px; margin-bottom: 2px; border-bottom: 1.5px solid #000; padding-bottom: 2px; color: #1b5e20;">🥛 {t('Aavin / Nanjil Milk & Curd', 'ஆவின் / நஞ்சில் பால் & தயிர்')} ({selected_month.strftime('%b %Y')})</div>
                                    <div style="margin-bottom: 2px; font-weight: 800; font-size: 10.5px; color: #000;">{t('Name:', 'பெயர்:')} <span style="font-weight: 800; color: #000;">{name}</span></div>
                                    <div style="border-top: 1px solid #ddd; padding-top: 2px; min-height: 20px; font-weight: bold; color: #000;">
                                        {slip_items_html if slip_items_html else f'<div style="font-weight: bold;">{t("No deliveries", "விநியோக பதிவுகள் இல்லை")}</div>'}
                                    </div>
                                </div>
                                <div>
                                    <div style="border-top: 1.5px solid #000; margin-top: 2px; padding-top: 2px; font-weight: 800; font-size: 11px; display: flex; justify-content: space-between; color: #000;">
                                        <span>{t('Total Bill:', 'மொத்த பில்:')}</span> <span style="color: #1b5e20; font-weight: 800;">₹{total:,.2f}</span>
                                    </div>
                                    <div style="font-size: 7px; background: #e8f5e9; padding: 2px; border-radius: 2px; margin-top: 1px; text-align: center; line-height: 1.2; font-weight: 800; color: #1b5e20; border: 1px solid #a5d6a7;">
                                        GPay / UPI: <b>9489002466</b> ({t('Pechimuthu', 'பேச்சிமுத்து')})<br>
                                        {t('Please pay using GPay/UPI, avoid cash & share receipt.', 'தயவுசெய்து GPay/UPI மூலம் செலுத்தவும். ரொக்கத்தைத் தவிர்த்து, ரசீதைப் பகிரவும்.')}
                                    </div>
                                    <div style="font-size: 6.5px; color: #000; text-align: center; margin-top: 1px; border-top: 1px dotted #000; padding-top: 1px; font-weight: bold;">
                                        {t('Computer generated bill. Contact:', 'இது கணினி பில். குறைகளுக்கு:')} <b>9489002466</b>
                                    </div>
                                </div>
                            </div>
                            """
                            st.markdown(slip_html, unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Payments ----------------
elif menu == "Payments":
    st.subheader(t("Payments", "செலுத்திய தொகைகள்"))
    customers = get_customers(include_inactive=True)
    if not customers:
        st.info(t("No customers available.", "வாடிக்கையாளர்கள் இல்லை."))
    else:
        selected_month = st.date_input(t("Billing month", "பில் மாதம்"), value=date.today())
        month_key = selected_month.strftime("%Y-%m")
        options = {f"{c[1]}": c[0] for c in customers}
        selected = st.selectbox(t("Customer", "வாடிக்கையாளரை தேர்ந்தெடுக்கவும்"), list(options.keys()))
        cid = options[selected]
        summary = get_monthly_summary(cid, month_key)
        payments = get_payments(cid, month_key)
        paid = sum(float(p[3]) for p in payments)
        balance = summary["total"] - paid

        st.metric(t("Outstanding Balance", "நிலுவைத் தொகை"), f"₹{balance:,.2f}")
        with st.form("payment_form"):
            amount = st.number_input(t("Payment amount (₹)", "செலுத்தும் தொகை (₹)"), min_value=0.0, value=max(balance, 0.0), step=10.0)
            payment_date = st.date_input(t("Payment date", "செலுத்திய தேதி"), value=date.today())
            method = st.selectbox(t("Payment method", "பணம் செலுத்திய முறை"), ["Cash", "UPI", "Bank Transfer", "Other"])
            note = st.text_input(t("Note", "குறிப்பு"))
            submit = st.form_submit_button(t("Record Payment", "பதிவு செய்"))
            if submit:
                if amount <= 0:
                    st.error(t("Enter a payment amount greater than zero.", "பூஜ்யத்தை விட அதிகமான தொகையை உள்ளிடவும்."))
                else:
                    add_payment(cid, month_key, payment_date.isoformat(), amount, method, note)
                    st.toast(t("✅ Payment recorded successfully!", "✅ தொகை பதிவு செய்யப்பட்டது!"), icon="💵")
                    st.rerun()

# ---------------- Reports ----------------
elif menu == "Reports":
    st.subheader(t("Reports & Analytics", "அறிக்கைகள் & பகுப்பாய்வு"))
    
    s_date, e_date, period_label = render_date_range_picker("rep")
    st.info(f"📆 **{t('Selected Period:', 'தேர்ந்தெடுக்கப்பட்ட காலம்:')}** `{period_label}`")

    # Item/Brand Breakdown
    st.markdown(f"### 📊 {t('Brand & Profit Summary', 'பிராண்ட் மற்றும் லாப சுருக்கம்')}")
    breakdown = get_item_breakdown_by_date_range(s_date, e_date)
    if breakdown:
        table_data = []
        total_del_qty = 0
        total_undel_cnt = 0
        total_cost = 0.0
        total_sell = 0.0
        total_profit = 0.0
        
        for b in breakdown:
            total_del_qty += b["delivered_qty"]
            total_undel_cnt += b["undelivered_count"]
            total_cost += b["total_cost"]
            total_sell += b["total_sell"]
            total_profit += b["profit"]
            
            table_data.append({
                t("Product / Brand", "பொருள் / பிராண்ட்"): b["item_name"],
                t("Delivered Quantity", "விநியோகிக்கப்பட்ட அளவு"): f"{b['delivered_qty']:g}",
                t("Not Delivered Count", "பால் வாங்காத எண்ணிக்கை"): b["undelivered_count"],
                t("Total Cost (₹)", "மொத்த அடக்க விலை (₹)"): f"₹{b['total_cost']:,.2f}",
                t("Total Revenue (₹)", "மொத்த விற்பனை தொகை (₹)"): f"₹{b['total_sell']:,.2f}",
                t("Net Profit (₹)", "நிகர லாபம் (₹)"): f"₹{b['profit']:,.2f}"
            })
        
        st.dataframe(table_data, use_container_width=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("Total Quantity Delivered", "மொத்த விநியோக அளவு"), f"{total_del_qty:g}")
        m2.metric(t("Total Cost (₹)", "மொத்த அடக்க விலை (₹)"), f"₹{total_cost:,.2f}")
        m3.metric(t("Total Revenue (₹)", "மொத்த வருவாய் (₹)"), f"₹{total_sell:,.2f}")
        m4.metric(t("Net Profit (₹)", "நிகர லாபம் (₹)"), f"₹{total_profit:,.2f}", delta=f"₹{total_profit:,.2f}")
    else:
        st.info(t("No delivery records found for the selected period.", "தேர்ந்தெடுக்கப்பட்ட காலத்தில் விநியோக பதிவுகள் இல்லை."))

    st.markdown("---")
    
    # Day-by-Day Table
    st.markdown(f"### 📅 {t('Day-by-Day Breakdown (1 to 30/31)', 'நாள் வாரியான கணக்கீடு (1 முதல் 30/31 வரை)')}")
    daily_rows = get_daily_breakdown_by_date_range(s_date, e_date)
    matrix = get_daily_brand_matrix(s_date, e_date)

    if daily_rows:
        daily_table = []
        for row in daily_rows:
            d = row["delivery_date"]
            b_map = matrix.get(d, {})
            
            entry = {
                t("Date", "தேதி"): d,
                t("Delivered Cust", "பால் பெற்றவர்கள்"): row["delivered_cust"],
                t("No Milk Cust", "பால் வாங்காதவர்கள்"): row["undelivered_cust"],
                t("Total Delivered Qty", "மொத்த அளவு"): f"{row['delivered_qty']:g}",
                t("Total Cost (₹)", "மொத்த செலவு (₹)"): f"₹{row['total_cost']:,.2f}",
                t("Total Revenue (₹)", "மொத்த வருவாய் (₹)"): f"₹{row['total_sell']:,.2f}",
                t("Profit (₹)", "லாபம் (₹)"): f"₹{row['profit']:,.2f}"
            }
            
            for item in AVAILABLE_ITEMS:
                entry[item] = f"{b_map.get(item, 0.0):g}"
            
            daily_table.append(entry)

        st.dataframe(daily_table, use_container_width=True)

    st.markdown("---")
    st.markdown(f"### 📥 {t('Export Reports & Summaries', 'அறிக்கைகள் பதிவிறக்கம்')}")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    
    range_csv = export_range_deliveries_csv(s_date, e_date)
    col_ex1.download_button(
        t("⬇️ Export Detailed Deliveries CSV", "⬇️ விரிவான விநியோகங்கள் CSV"),
        data=range_csv,
        file_name=f"deliveries_{s_date}_to_{e_date}.csv",
        mime="text/csv",
        type="primary"
    )

    daily_summary_csv = export_daily_summary_csv(s_date, e_date)
    col_ex2.download_button(
        t("⬇️ Export Day-by-Day Summary CSV", "⬇️ நாள் வாரியான சுருக்கம் CSV"),
        data=daily_summary_csv,
        file_name=f"daily_summary_{s_date}_to_{e_date}.csv",
        mime="text/primary"
    )
    
    col_ex3.download_button(
        t("⬇️ Export Master Customers CSV", "⬇️ அனைத்து வாடிக்கையாளர்கள் மாஸ்டர் CSV"),
        data=export_customers_csv(),
        file_name="customers_list.csv",
        mime="text/csv"
    )
