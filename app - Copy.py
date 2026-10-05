import streamlit as st
from datetime import date, datetime
import urllib.parse
from database import (
    init_db, AVAILABLE_ITEMS, get_item_rates, set_item_rate, add_customer, update_customer,
    delete_customer, get_customers, get_customer, get_customer_items, save_delivery, clear_deliveries_for_date,
    get_customer_deliveries_for_date, get_deliveries, get_monthly_summary, add_payment, get_payments,
    get_dashboard_stats, export_deliveries_csv, export_customers_csv, export_all_customers_monthly_report_csv
)

st.set_page_config(page_title="Milk & Curd Delivery Management", page_icon="🥛", layout="wide")
init_db()

st.markdown("""
<style>
.main-title {font-size: 32px; font-weight: 700;}
.receipt-box {border: 2px solid #333; padding: 20px; border-radius: 10px; background-color: #fafafa; color: #111;}
.custom-banner {padding: 12px 20px; border-radius: 8px; background: linear-gradient(90deg, #4CAF50, #2E7D32); color: white; font-weight: 600; margin-bottom: 15px;}
.warn-banner {padding: 12px 20px; border-radius: 8px; background: linear-gradient(90deg, #FF9800, #EF6C00); color: white; font-weight: 600; margin-bottom: 15px;}

@media print {
    body { background: white; color: black; margin: 0; padding: 0; }
    .no-print { display: none !important; }
    header, footer { visibility: hidden !important; display: none !important; }
    .stSidebar { display: none !important; }
}

.printable-slip {
    border: 2px dashed #333;
    padding: 10px 14px;
    background: #fff;
    font-size: 13px;
    color: #111;
    box-sizing: border-box;
    margin-bottom: 10px;
    page-break-inside: avoid;
    break-inside: avoid;
}

.slip-title {
    font-weight: bold;
    text-align: center;
    font-size: 14px;
    margin-bottom: 6px;
    border-bottom: 1.5px solid #333;
    padding-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🥛 Milk & Curd Delivery Management</div>', unsafe_allow_html=True)
st.caption("Multi-Brand Customer Management • Dynamic Add Buttons • Printable A4 Slips • Reports")

menu = st.sidebar.radio(
    "Menu",
    ["🏠 Dashboard", "⚙️ Item Rates", "👥 Customers", "🥛 Daily Delivery", "🧾 Billing & Receipts", "💵 Payments", "📊 Reports"]
)

item_rates = get_item_rates()

# ---------------- Dashboard ----------------
if menu == "🏠 Dashboard":
    st.subheader("Dashboard")
    selected_date = st.date_input("Delivery date", value=date.today())
    stats = get_dashboard_stats(selected_date.isoformat())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Customers", stats["customers"])
    c2.metric("Delivered", stats["delivered"])
    c3.metric("No Milk/Curd", stats["no_milk"])
    c4.metric("Today's Total Quantity", f'{stats["litres"]:.2f}')

    st.markdown('<div class="custom-banner">🌟 Tip: Use the "Printable A4 Slips" tab in Billing & Receipts to print 10 clean, easy-to-read bill slips per page (2 columns x 5 rows)!</div>', unsafe_allow_html=True)

# ---------------- Item Rates ----------------
elif menu == "⚙️ Item Rates":
    st.subheader("Configure Product & Packet Rates (₹ per item/packet)")
    with st.form("item_rates_form"):
        new_rates = {}
        for item in AVAILABLE_ITEMS:
            new_rates[item] = st.number_input(f"{item} Rate (₹)", min_value=0.0, value=float(item_rates.get(item, 30.0)), step=0.50)
        
        submitted = st.form_submit_button("Save Rates")
        if submitted:
            for item, rate in new_rates.items():
                set_item_rate(item, rate)
            st.toast("✅ Item rates updated successfully!", icon="🎉")
            st.success("Item rates updated successfully!")
            st.rerun()

# ---------------- Customers ----------------
elif menu == "👥 Customers":
    st.subheader("Customer Management")
    tab1, tab2 = st.tabs(["➕ Add Customer", "📋 Customer List"])

    with tab1:
        st.markdown("### Add New Customer")
        
        if st.session_state.get("reset_cust_form", False):
            for k in list(st.session_state.keys()):
                if k.startswith("new_cust_") or k.startswith("add_it_") or k.startswith("add_qty_"):
                    del st.session_state[k]
            st.session_state.add_items_list = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]
            st.session_state.reset_cust_form = False

        if "add_items_list" not in st.session_state:
            st.session_state.add_items_list = [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]

        name = st.text_input("Customer name *", key="new_cust_name")
        phone = st.text_input("Phone", key="new_cust_phone")
        address = st.text_input("Address", key="new_cust_address")
        active = st.checkbox("Active customer", value=True, key="new_cust_active")

        st.markdown("#### Default Products / Brands")
        for idx, itm in enumerate(st.session_state.add_items_list):
            c1, c2, c3 = st.columns([3, 2, 1])
            default_idx = AVAILABLE_ITEMS.index(itm["item"]) if itm["item"] in AVAILABLE_ITEMS else 0
            item_sel = c1.selectbox(f"Product #{idx+1}", AVAILABLE_ITEMS, index=default_idx, key=f"add_it_{idx}")
            qty_inp = c2.number_input(f"Quantity #{idx+1}", min_value=0.0, value=float(itm["qty"]), step=1.0, key=f"add_qty_{idx}")
            
            st.session_state.add_items_list[idx]["item"] = item_sel
            st.session_state.add_items_list[idx]["qty"] = qty_inp

            if len(st.session_state.add_items_list) > 1:
                if c3.button("❌", key=f"rem_add_{idx}"):
                    st.session_state.add_items_list.pop(idx)
                    st.rerun()

        if st.button("➕ Add Another Brand/Product", key="btn_add_brand_new"):
            st.session_state.add_items_list.append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
            st.rerun()

        st.markdown("---")
        if st.button("💾 Save Customer", type="primary", key="btn_save_new_cust"):
            if not name.strip():
                st.error("Customer name is required.")
            else:
                items_to_save = [(x["item"], x["qty"]) for x in st.session_state.add_items_list]
                add_customer(name.strip(), phone.strip(), address.strip(), items_to_save, active)
                
                st.session_state.reset_cust_form = True
                st.toast(f"✅ Customer saved successfully! Form cleared.", icon="🎉")
                st.success("Customer added successfully. Form is now ready for the next customer.")
                st.rerun()

    with tab2:
        customers = get_customers(include_inactive=True)
        if not customers:
            st.info("No customers added yet.")
        else:
            for c in customers:
                cid, name, phone, address, active, created = c
                cust_items = get_customer_items(cid)
                items_summary = " | ".join([f"{i['item_name']} ({i['normal_qty']:g}/day)" for i in cust_items])
                
                with st.expander(f"{name} — {items_summary} {'🟢' if active else '🔴'}"):
                    ename = st.text_input("Name", value=name, key=f"n_{cid}")
                    ephone = st.text_input("Phone", value=phone or "", key=f"p_{cid}")
                    eaddress = st.text_input("Address", value=address or "", key=f"a_{cid}")
                    eactive = st.checkbox("Active", value=bool(active), key=f"ac_{cid}")
                    
                    edit_key = f"edit_items_{cid}"
                    if edit_key not in st.session_state:
                        st.session_state[edit_key] = [{"item": ci["item_name"], "qty": ci["normal_qty"]} for ci in cust_items] if cust_items else [{"item": AVAILABLE_ITEMS[0], "qty": 1.0}]

                    st.markdown("##### Customer Products / Brands")
                    for idx, itm in enumerate(st.session_state[edit_key]):
                        c1, c2, c3 = st.columns([3, 2, 1])
                        ed_default_idx = AVAILABLE_ITEMS.index(itm["item"]) if itm["item"] in AVAILABLE_ITEMS else 0
                        st.session_state[edit_key][idx]["item"] = c1.selectbox(f"Product #{idx+1}", AVAILABLE_ITEMS, index=ed_default_idx, key=f"ed_it_{cid}_{idx}")
                        st.session_state[edit_key][idx]["qty"] = c2.number_input(f"Qty #{idx+1}", min_value=0.0, value=float(itm["qty"]), step=1.0, key=f"ed_qty_{cid}_{idx}")
                        if len(st.session_state[edit_key]) > 1:
                            if c3.button("❌", key=f"rem_ed_{cid}_{idx}"):
                                st.session_state[edit_key].pop(idx)
                                st.rerun()

                    if st.button("➕ Add Brand/Product", key=f"btn_add_ed_{cid}"):
                        st.session_state[edit_key].append({"item": AVAILABLE_ITEMS[0], "qty": 1.0})
                        st.rerun()

                    if st.button("💾 Save Customer Changes", key=f"btn_save_ed_{cid}", type="primary"):
                        items_to_save = [(x["item"], x["qty"]) for x in st.session_state[edit_key]]
                        update_customer(cid, ename.strip(), ephone.strip(), eaddress.strip(), items_to_save, eactive)
                        if edit_key in st.session_state:
                            del st.session_state[edit_key]
                        for k in list(st.session_state.keys()):
                            if k.startswith(f"ed_it_{cid}_") or k.startswith(f"ed_qty_{cid}_"):
                                del st.session_state[k]
                        st.toast("✅ Customer updated successfully!", icon="🎉")
                        st.success("Customer updated.")
                        st.rerun()

                    # Password Protected Deletion Form
                    with st.form(f"delete_form_{cid}"):
                        st.markdown("---")
                        st.markdown("🔒 **Secure Deletion:** Enter deletion password (PIN: `1234`) to delete this customer.")
                        del_password = st.text_input("Deletion Password", type="password", key=f"del_pwd_{cid}")
                        remove = st.form_submit_button("🗑️ Delete Customer")
                        if remove:
                            if del_password == "1234":
                                delete_customer(cid)
                                st.toast("⚠️ Customer deleted!", icon="🗑️")
                                st.warning("Customer deleted.")
                                st.rerun()
                            else:
                                st.error("❌ Incorrect deletion password! Customer was not deleted.")

# ---------------- Daily Delivery ----------------
elif menu == "🥛 Daily Delivery":
    st.subheader("Daily Milk & Curd Delivery")
    delivery_date = st.date_input("Delivery date", value=date.today())
    customers = get_customers(include_inactive=False)

    if not customers:
        st.warning("Add customers before entering deliveries.")
    else:
        existing_rows = get_deliveries(None, delivery_date.isoformat())
        is_modification = len(existing_rows) > 0

        if is_modification:
            st.markdown(f'<div class="warn-banner">⚠️ Delivery records for {delivery_date.strftime("%d-%b-%Y")} already exist. You are modifying existing records.</div>', unsafe_allow_html=True)
            overwrite_confirm = st.checkbox("Yes, I want to modify/update today's delivery records", value=True)
        else:
            overwrite_confirm = True

        st.write("Record quantities for today. Use the **➕ Add Product** button for customers taking multiple brands/packets.")
        st.markdown("### Today's customers")

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
                    item_sel = col1.selectbox("Product", AVAILABLE_ITEMS, index=item_def_idx, key=f"d_item_{cid}_{idx}")
                    qty_inp = col2.number_input("Qty", min_value=0.0, max_value=100.0, value=float(row_data["qty"]), step=1.0, key=f"d_qty_{cid}_{idx}")
                    status_sel = col3.selectbox("Status", ["Delivered", "No Milk"], index=0 if row_data["status"]=="Delivered" else 1, key=f"d_stat_{cid}_{idx}")
                    note_inp = col4.text_input("Note", value=row_data["note"], key=f"d_note_{cid}_{idx}")
                    
                    if status_sel == "No Milk":
                        qty_inp = 0.0

                    if len(rows_for_cust) > 1:
                        if col5.button("❌", key=f"d_del_{cid}_{idx}"):
                            continue
                    
                    updated_rows.append({"item": item_sel, "qty": qty_inp, "status": status_sel, "note": note_inp})

                d_state[cid] = updated_rows

                if st.button("➕ Add Product", key=f"btn_add_prod_{cid}"):
                    d_state[cid].append({"item": AVAILABLE_ITEMS[0], "qty": 1.0, "status": "Delivered", "note": ""})
                    st.rerun()

                form_data[cid] = d_state[cid]

        if st.button("💾 Save Today's Delivery", type="primary", use_container_width=True):
            if not overwrite_confirm:
                st.error("Please check the confirmation box to modify existing records.")
            else:
                for cid, items in form_data.items():
                    clear_deliveries_for_date(cid, delivery_date.isoformat())
                    for itm in items:
                        if itm["qty"] <= 0:
                            stat = "No Milk"
                            q = 0.0
                        else:
                            stat = itm["status"]
                            q = itm["qty"]
                        rate = item_rates.get(itm["item"], 30.0)
                        save_delivery(cid, delivery_date.isoformat(), itm["item"], q, rate, stat, itm["note"])

                st.toast(f"✅ Today's report saved successfully for {delivery_date.strftime('%d-%b-%Y')}!", icon="🎉")
                st.success(f"✅ Today's report saved successfully for {delivery_date.strftime('%d-%b-%Y')}!")
                st.rerun()

# ---------------- Billing & Receipts ----------------
elif menu == "🧾 Billing & Receipts":
    st.subheader("Monthly Billing & Receipt Generator")
    customers = get_customers(include_inactive=True)
    if not customers:
        st.info("No customers available.")
    else:
        selected_month = st.date_input("Select month (any date in month)", value=date.today())
        month_key = selected_month.strftime("%Y-%m")

        tab_indiv, tab_bulk, tab_print = st.tabs(["👤 Individual Customer Receipt", "📋 Bulk All-Customer List & WhatsApp Queue", "🖨️ Printable A4 Bill Slips"])

        with tab_indiv:
            options = {f"{c[1]} ({c[2] or 'No phone'})": c[0] for c in customers}
            selected = st.selectbox("Select Individual Customer", list(options.keys()))
            cid = options[selected]
            
            customer_info = get_customer(cid)
            summary = get_monthly_summary(cid, month_key)
            payments = get_payments(cid, month_key)
            paid = sum(float(p[3]) for p in payments)
            total = summary["total"]
            balance = total - paid

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Items Delivered", f'{summary["litres"]:.2f}')
            c2.metric("Total Bill Amount", f'₹{total:,.2f}')
            c3.metric("Outstanding Balance", f'₹{balance:,.2f}')

            phone = customer_info[2]
            if phone:
                clean_phone = "".join(filter(str.isdigit, phone))
                if len(clean_phone) == 10:
                    clean_phone = "91" + clean_phone
                
                st.markdown("### 💬 WhatsApp Message Templates")
                msg_tab1, msg_tab2, msg_tab3 = st.tabs(["📄 Standard Invoice & Updates", "🔔 Payment Reminder / Due", "✨ Special / Custom Message"])
                
                with msg_tab1:
                    wa_text_1 = (
                        f"🥛 *MILK & CURD DELIVERY INVOICE*\n"
                        f"Month: {selected_month.strftime('%B %Y')}\n"
                        f"Customer: {customer_info[1]}\n"
                        f"--------------------------------\n"
                        f"Total Units/Packets: {summary['litres']:.2f}\n"
                        f"Gross Bill Amount: ₹{total:,.2f}\n"
                        f"Payments Made: ₹{paid:,.2f}\n"
                        f"*Balance Due: ₹{balance:,.2f}*\n"
                        f"--------------------------------\n"
                        f"Thanks for your cooperation!\n\n"
                        f"📢 *Updates & Offerings:*\n"
                        f"• Nanjil 250ml milk newly introduced (₹22) along with curd.\n"
                        f"• Ready-made Chapathi & Poori available.\n"
                        f"• Aavin Curd (₹10) available.\n"
                        f"• Milk & items provided for marriage functions, temple festivals, and other functions with doorstep delivery (24-hour advance prebooking required).\n\n"
                        f"For bulk orders, please contact:\n"
                        f"📞 8838594492 / 9489002466 / 8870225231"
                    )
                    st.text_area("Preview Message #1", value=wa_text_1, height=220, key="preview_msg_1")
                    encoded_wa_1 = urllib.parse.quote(wa_text_1)
                    st.link_button("💬 Send Standard Invoice via WhatsApp", f"https://wa.me/{clean_phone}?text={encoded_wa_1}", use_container_width=True)

                with msg_tab2:
                    wa_text_2 = (
                        f"⚠️ *PAYMENT REMINDER - MILK & CURD*\n"
                        f"Dear {customer_info[1]},\n"
                        f"Your outstanding balance for {selected_month.strftime('%B %Y')} is *₹{balance:,.2f}*.\n"
                        f"Please clear your dues at your earliest convenience. Thank you!\n\n"
                        f"Contact: 8838594492 / 9489002466 / 8870225231"
                    )
                    st.text_area("Preview Message #2", value=wa_text_2, height=150, key="preview_msg_2")
                    encoded_wa_2 = urllib.parse.quote(wa_text_2)
                    st.link_button("💬 Send Payment Reminder via WhatsApp", f"https://wa.me/{clean_phone}?text={encoded_wa_2}", use_container_width=True)

                with msg_tab3:
                    custom_user_msg = st.text_area("Type your special/custom message here:", value=f"Hello {customer_info[1]}, wishing you a wonderful day! Please let us know if you need any extra milk packets or bulk orders for functions.", height=130, key="custom_msg_input")
                    encoded_wa_3 = urllib.parse.quote(custom_user_msg)
                    st.link_button("💬 Send Special/Custom Message via WhatsApp", f"https://wa.me/{clean_phone}?text={encoded_wa_3}", use_container_width=True)
            else:
                st.warning("⚠️ No phone number saved for this customer.")

            st.markdown("### Daily delivery details")
            rows = get_deliveries(cid, month_key)
            if rows:
                date_grouped = {}
                for r in rows:
                    d_date = r[2]
                    if d_date not in date_grouped:
                        date_grouped[d_date] = []
                    date_grouped[d_date].append(r)

                display_list = []
                for d_date, items in date_grouped.items():
                    item_desc = " + ".join([f"{i[4]:g}x {i[3]}" for i in items])
                    total_amount = sum([i[4] * i[5] for i in items])
                    statuses = ", ".join(set([i[6] for i in items]))
                    notes = ", ".join([i[7] for i in items if i[7]])
                    display_list.append({"Date": d_date, "Items Delivered (+)": item_desc, "Status": statuses, "Daily Total": f"₹{total_amount:,.2f}", "Note": notes})

                st.dataframe(display_list, use_container_width=True, hide_index=True)
            else:
                st.info("No delivery records for this month.")

            st.markdown("---")
            st.markdown("### 📄 Monthly Billing Receipt / Invoice")
            receipt_html = f"""
            <div class="receipt-box">
                <h2 style="text-align: center; margin-bottom: 5px;">MILK & CURD DELIVERY INVOICE</h2>
                <p style="text-align: center; color: #555; margin-top: 0;">Month: <b>{selected_month.strftime('%B %Y')}</b></p>
                <hr>
                <p><b>Customer Name:</b> {customer_info[1]}</p>
                <p><b>Phone:</b> {customer_info[2] or 'N/A'} | <b>Address:</b> {customer_info[3] or 'N/A'}</p>
                <hr>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
                    <tr>
                        <th style="text-align: left; border-bottom: 1px solid #ddd; padding: 6px;">Description</th>
                        <th style="text-align: right; border-bottom: 1px solid #ddd; padding: 6px;">Total Qty / Amount</th>
                    </tr>
                    <tr>
                        <td style="padding: 6px;">Total Deliveries</td>
                        <td style="text-align: right; padding: 6px;">{summary["litres"]:.2f} units</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px;"><b>Gross Bill Amount</b></td>
                        <td style="text-align: right; padding: 6px;"><b>₹{total:,.2f}</b></td>
                    </tr>
                    <tr>
                        <td style="padding: 6px;">Total Payments Made</td>
                        <td style="text-align: right; padding: 6px; color: green;">- ₹{paid:,.2f}</td>
                    </tr>
                    <tr style="border-top: 2px solid #333;">
                        <td style="padding: 8px;"><b>Net Balance Due</b></td>
                        <td style="text-align: right; padding: 8px; color: {'red' if balance > 0 else 'green'};"><b>₹{balance:,.2f}</b></td>
                    </tr>
                </table>
                <p style="text-align: center; font-size: 13px; color: #666; margin-top: 20px;">Thank you for your business!</p>
            </div>
            """
            st.markdown(receipt_html, unsafe_allow_html=True)

        with tab_bulk:
            st.markdown("### 📥 Bulk Download")
            all_csv_data = export_all_customers_monthly_report_csv(month_key)
            st.download_button(
                label="⬇️ Download All Customers Monthly Report (CSV)",
                data=all_csv_data,
                file_name=f"all_customers_milk_report_{month_key}.csv",
                mime="text/csv",
                type="primary"
            )
            st.markdown("---")
            st.markdown("### 💬 All-Customer WhatsApp Message Queue & Templates")
            
            bulk_msg_tab1, bulk_msg_tab2, bulk_msg_tab3 = st.tabs(["📄 Standard Invoice Queue", "🔔 Payment Reminder Queue", "✨ Special / Custom Message Queue"])
            
            with bulk_msg_tab1:
                st.write(f"Send **Standard Monthly Invoice & Business Updates** for **{selected_month.strftime('%B %Y')}**:")
                for c in customers:
                    cid, name, phone, address, active, _ = c
                    summary = get_monthly_summary(cid, month_key)
                    payments = get_payments(cid, month_key)
                    paid = sum(float(p[3]) for p in payments)
                    total = summary["total"]
                    balance = total - paid

                    with st.container(border=True):
                        col_info, col_action = st.columns([3, 2])
                        col_info.markdown(f"**{name}** &nbsp;|&nbsp; `Ph: {phone or 'N/A'}`")
                        col_info.caption(f"Delivered: {summary['litres']:.2f} units | Bill: ₹{total:,.2f} | Paid: ₹{paid:,.2f} | **Due: ₹{balance:,.2f}**")

                        if phone:
                            clean_phone = "".join(filter(str.isdigit, phone))
                            if len(clean_phone) == 10:
                                clean_phone = "91" + clean_phone
                            
                            wa_text = (
                                f"🥛 *MILK & CURD DELIVERY INVOICE*\n"
                                f"Month: {selected_month.strftime('%B %Y')}\n"
                                f"Customer: {name}\n"
                                f"--------------------------------\n"
                                f"Total Units/Packets: {summary['litres']:.2f}\n"
                                f"Gross Bill Amount: ₹{total:,.2f}\n"
                                f"Payments Made: ₹{paid:,.2f}\n"
                                f"*Balance Due: ₹{balance:,.2f}*\n"
                                f"--------------------------------\n"
                                f"Thanks for your cooperation!\n\n"
                                f"📢 *Updates & Offerings:*\n"
                                f"• Nanjil 250ml milk newly introduced (₹22) along with curd.\n"
                                f"• Ready-made Chapathi & Poori available.\n"
                                f"• Aavin Curd (₹10) available.\n"
                                f"• Milk & items provided for marriage functions, temple festivals, and other functions with doorstep delivery (24-hour advance prebooking required).\n\n"
                                f"For bulk orders, please contact:\n"
                                f"📞 8838594492 / 9489002466 / 8870225231"
                            )
                            encoded_wa = urllib.parse.quote(wa_text)
                            col_action.link_button("💬 Send Invoice", f"https://wa.me/{clean_phone}?text={encoded_wa}", use_container_width=True)
                        else:
                            col_action.warning("No phone number")

            with bulk_msg_tab2:
                st.write(f"Send **Payment Reminder / Due Notice** for **{selected_month.strftime('%B %Y')}**:")
                for c in customers:
                    cid, name, phone, address, active, _ = c
                    summary = get_monthly_summary(cid, month_key)
                    payments = get_payments(cid, month_key)
                    paid = sum(float(p[3]) for p in payments)
                    total = summary["total"]
                    balance = total - paid

                    with st.container(border=True):
                        col_info, col_action = st.columns([3, 2])
                        col_info.markdown(f"**{name}** &nbsp;|&nbsp; `Ph: {phone or 'N/A'}`")
                        col_info.caption(f"**Due: ₹{balance:,.2f}**")

                        if phone and balance > 0:
                            clean_phone = "".join(filter(str.isdigit, phone))
                            if len(clean_phone) == 10:
                                clean_phone = "91" + clean_phone
                            
                            wa_text_rem = (
                                f"⚠️ *PAYMENT REMINDER - MILK & CURD*\n"
                                f"Dear {name},\n"
                                f"Your outstanding balance for {selected_month.strftime('%B %Y')} is *₹{balance:,.2f}*.\n"
                                f"Please clear your dues at your earliest convenience. Thank you!\n\n"
                                f"Contact: 8838594492 / 9489002466 / 8870225231"
                            )
                            encoded_wa_rem = urllib.parse.quote(wa_text_rem)
                            col_action.link_button("💬 Send Reminder", f"https://wa.me/{clean_phone}?text={encoded_wa_rem}", use_container_width=True)
                        elif not phone:
                            col_action.warning("No phone number")
                        else:
                            col_action.info("No balance due")

            with bulk_msg_tab3:
                bulk_custom_text = st.text_input("Enter custom message to send to all customers with phone numbers:", value="Hello! Wishing you a happy day. We take bulk orders for marriage functions, temple festivals, and other events (24 hrs advance notice). Contact: 8838594492 / 9489002466 / 8870225231")
                st.write("Clicking send will open WhatsApp with your custom message for each customer:")
                for c in customers:
                    cid, name, phone, address, active, _ = c
                    with st.container(border=True):
                        col_info, col_action = st.columns([3, 2])
                        col_info.markdown(f"**{name}** &nbsp;|&nbsp; `Ph: {phone or 'N/A'}`")

                        if phone:
                            clean_phone = "".join(filter(str.isdigit, phone))
                            if len(clean_phone) == 10:
                                clean_phone = "91" + clean_phone
                            
                            personalized_custom = f"Dear {name},\n{bulk_custom_text}"
                            encoded_custom = urllib.parse.quote(personalized_custom)
                            col_action.link_button(f"💬 Send to {name}", f"https://wa.me/{clean_phone}?text={encoded_custom}", use_container_width=True)
                        else:
                            col_action.warning("No phone number")

        with tab_print:
            st.markdown("### 🖨️️ Printable A4 Bill Slips (10 Slips per Page: 2 Columns × 5 Rows)")
            st.info("💡 **Instructions for Printing:** Press **`Ctrl + P`** (or `Cmd + P` on Mac) in your browser. Set margins to **None** or **Minimum** and ensure headers/footers are unchecked. These bills now render natively in standard page flow so they align perfectly without side-scrolling.")
            
            st.markdown("---")

            # Render 10 slips per page using native Streamlit columns (2 columns x 5 rows)
            customer_batches = [customers[i:i + 10] for i in range(0, len(customers), 10)]

            for batch_idx, batch in enumerate(customer_batches):
                st.markdown(f"#### Page {batch_idx + 1}")
                
                # Chunk batch into rows of 2 customers (5 rows total)
                rows_data = [batch[i:i + 2] for i in range(0, len(batch), 2)]
                
                for row in rows_data:
                    cols = st.columns(2)
                    for col_idx, c in enumerate(row):
                        cid, name, phone, address, active, _ = c
                        summary = get_monthly_summary(cid, month_key)
                        payments = get_payments(cid, month_key)
                        paid = sum(float(p[3]) for p in payments)
                        total = summary["total"]
                        balance = total - paid
                        balance_color = 'red' if balance > 0 else 'green'

                        with cols[col_idx]:
                            slip_html = f"""
                            <div class="printable-slip">
                                <div class="slip-title">🥛 MILK & CURD BILL ({selected_month.strftime('%b %Y')})</div>
                                <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
                                    <tr>
                                        <td style="font-weight: bold; width: 22%; padding: 2px 0;">Cust:</td>
                                        <td style="font-weight: bold; width: 78%; padding: 2px 0;">{name}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: bold; padding: 2px 0;">Qty:</td>
                                        <td style="padding: 2px 0;">{summary['litres']:.2f} units</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: bold; padding: 2px 0;">Bill:</td>
                                        <td style="padding: 2px 0;">₹{total:,.2f}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: bold; padding: 2px 0;">Paid:</td>
                                        <td style="padding: 2px 0;">₹{paid:,.2f}</td>
                                    </tr>
                                    <tr style="border-top: 1.5px solid #333; font-weight: bold;">
                                        <td style="padding-top: 4px;">Due:</td>
                                        <td style="padding-top: 4px; color: {balance_color};">₹{balance:,.2f}</td>
                                    </tr>
                                </table>
                            </div>
                            """
                            st.markdown(slip_html, unsafe_allow_html=True)
                    
                    # If a row has only 1 customer, render an empty column space
                    if len(row) == 1:
                        with cols[1]:
                            st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

                if batch_idx < len(customer_batches) - 1:
                    st.markdown("<hr style='border: 2px dashed #bbb; margin: 30px 0;'>", unsafe_allow_html=True)

# ---------------- Payments ----------------
elif menu == "💵 Payments":
    st.subheader("Payments")
    customers = get_customers(include_inactive=True)
    if not customers:
        st.info("No customers available.")
    else:
        selected_month = st.date_input("Billing month", value=date.today())
        month_key = selected_month.strftime("%Y-%m")
        options = {f"{c[1]}": c[0] for c in customers}
        selected = st.selectbox("Customer", list(options.keys()))
        cid = options[selected]
        summary = get_monthly_summary(cid, month_key)
        payments = get_payments(cid, month_key)
        paid = sum(float(p[3]) for p in payments)
        balance = summary["total"] - paid

        st.metric("Outstanding Balance", f"₹{balance:,.2f}")
        with st.form("payment_form"):
            amount = st.number_input("Payment amount (₹)", min_value=0.0, value=max(balance, 0.0), step=10.0)
            payment_date = st.date_input("Payment date", value=date.today())
            method = st.selectbox("Payment method", ["Cash", "UPI", "Bank Transfer", "Other"])
            note = st.text_input("Note")
            submit = st.form_submit_button("Record Payment")
            if submit:
                if amount <= 0:
                    st.error("Enter a payment amount greater than zero.")
                else:
                    add_payment(cid, month_key, payment_date.isoformat(), amount, method, note)
                    st.toast("✅ Payment recorded successfully!", icon="💵")
                    st.success("Payment recorded.")
                    st.rerun()

        if payments:
            st.markdown("### Payment history")
            st.dataframe(
                [{"Date": p[2], "Amount": f"₹{p[3]:,.2f}", "Method": p[4], "Note": p[5] or ""} for p in payments],
                use_container_width=True, hide_index=True
            )

# ---------------- Reports ----------------
elif menu == "📊 Reports":
    st.subheader("Reports & Export")
    report_date = st.date_input("Report Date", value=date.today())
    stats = get_dashboard_stats(report_date.isoformat())
    c1, c2, c3 = st.columns(3)
    c1.metric("Delivered Customers", stats["delivered"])
    c2.metric("No Milk/Curd", stats["no_milk"])
    c3.metric("Total Quantity", f'{stats["litres"]:.2f}')

    st.markdown("### Daily delivery report")
    rows = get_deliveries(None, report_date.isoformat())
    if rows:
        cust_grouped = {}
        for r in rows:
            c_name = r[1]
            if c_name not in cust_grouped:
                cust_grouped[c_name] = []
            cust_grouped[c_name].append(r)

        report_display = []
        for c_name, items in cust_grouped.items():
            item_summary = " + ".join([f"{i[4]:g}x {i[3]}" for i in items])
            tot_amt = sum([i[4] * i[5] for i in items])
            stat = items[0][6]
            nt = ", ".join([i[7] for i in items if i[7]])
            report_display.append({"Customer": c_name, "Date": report_date.strftime("%Y-%m-%d"), "Items Delivered (+)": item_summary, "Total Amount": f"₹{tot_amt:,.2f}", "Status": stat, "Note": nt})

        st.dataframe(report_display, use_container_width=True, hide_index=True)
    else:
        st.info("No records for this date.")

    st.markdown("### Export")
    col1, col2 = st.columns(2)
    if col1.download_button("⬇️ Export Customers CSV", export_customers_csv(), "customers.csv", "text/csv"):
        pass
    if col2.download_button("⬇️ Export Deliveries CSV", export_deliveries_csv(), "deliveries.csv", "text/csv"):
        pass