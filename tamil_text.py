"""Tamil / English wording for receipts, WhatsApp messages and A4 slips.
No Streamlit here, so it can be tested on its own."""
import re

TA_MONTHS = ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்",
             "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"]
TA_MONTHS_SHORT = ["ஜன", "பிப்", "மார்", "ஏப்", "மே", "ஜூன்",
                   "ஜூலை", "ஆக", "செப்", "அக்", "நவ", "டிச"]


def ta_month_label(year, month):
    return f"{TA_MONTHS[month - 1]} {year}"


def ta_short_date(iso_date):
    """'2026-10-09' -> '09 அக்'"""
    y, m, d = (int(x) for x in iso_date.split("-"))
    return f"{d:02d} {TA_MONTHS_SHORT[m - 1]}"


# ---- item names in Tamil (phrases first, then single words). Unknown words stay as they are. ----
_PHRASES = [
    ("Nanjil Green Milk", "நஞ்சில் பச்சை பால்"),
    ("Nanjil Milk Red", "நஞ்சில் சிவப்பு பால்"),
    ("Nanjil Red Milk", "நஞ்சில் சிவப்பு பால்"),
]
_WORDS = [
    ("Aavin", "ஆவின்"), ("Nanjil", "நஞ்சில்"), ("Milk", "பால்"), ("Curd", "தயிர்"),
    ("Red", "சிவப்பு"), ("Green", "பச்சை"), ("Shop", "கடை"), ("Litre", "லிட்டர்"), ("Liter", "லிட்டர்"),
    ("Ghee", "நெய்"), ("Butter", "வெண்ணெய்"), ("Buttermilk", "மோர்"),
]


def tamil_item(name, overrides=None):
    """'Nanjil Milk Red (130ml)' -> 'நஞ்சில் சிவப்பு பால் (130 மி.லி)'.
    `overrides` = {english item name: tamil name} typed by the owner (wins over the automatic translation)."""
    if overrides and overrides.get(name):
        return overrides[name]
    s = str(name)
    for en, ta in _PHRASES:
        s = s.replace(en, ta)
    s = re.sub(r"(\d+)\s*ml\b", r"\1 மி.லி", s, flags=re.I)
    for en, ta in _WORDS:
        s = re.sub(rf"\b{en}\b", ta, s, flags=re.I)
    return s


def has_untranslated_words(tamil_name):
    """True if a Tamil name still contains English words (so the owner should add a Tamil name)."""
    return bool(re.search(r"[A-Za-z]{3,}", tamil_name))


STR = {
    "en": {
        "bill_for": "Bill for {month}",
        "name": "Name", "phone": "Phone", "customer_name": "Customer Name",
        "monthly_bill": "Monthly Bill / Receipt (Month: {month})",
        "col_product": "Product / Brand", "col_days": "Days & Quantity", "col_rate": "Rate", "col_total": "Total",
        "daywise": "Day-wise Delivery Details", "col_date": "Date", "col_items": "Items", "col_amount": "Amount",
        "total_bill": "Total Bill Amount:", "total_wa": "Total Bill", "paid": "Paid", "balance": "Balance Due",
        "no_milk": "No milk", "extra": "extra", "incl_extra": "incl. {n} extra", "pkts": "pkts",
        "no_deliveries": "No deliveries this month",
        "pay_notice": "Payment Notice",
        "upi_msg": "Please pay by GPay / PhonePe / UPI instead of cash - it is quick, safe and there is no change problem. "
                   "Kindly send us the payment screenshot. Thank you!",
        "upi_line": "UPI / GPay / PhonePe",
        "notes_title": "Announcements",
        "contact": "Contact",
        "footer": "This is a computer-generated bill. For any queries, please contact {num}.",
        "day_by_day": "Day-by-day details:",
        "day_one": "day", "day_many": "days",
        "slip_pay": "Please pay by GPay / UPI, avoid cash &amp; share the screenshot.",
        "slip_footer": "Computer generated bill. Contact: {num}",
    },
    "ta": {
        "bill_for": "{month} மாத பில்",
        "name": "பெயர்", "phone": "தொலைபேசி", "customer_name": "வாடிக்கையாளர் பெயர்",
        "monthly_bill": "மாதாந்திர பில் / ரசீது (மாதம்: {month})",
        "col_product": "பொருள் / பிராண்ட்", "col_days": "நாட்கள் & அளவு", "col_rate": "விலை", "col_total": "மொத்தம்",
        "daywise": "தினசரி விநியோக விவரம்", "col_date": "தேதி", "col_items": "பொருட்கள்", "col_amount": "தொகை",
        "total_bill": "மொத்த பில் தொகை:", "total_wa": "மொத்த பில்", "paid": "செலுத்தியது", "balance": "நிலுவைத் தொகை",
        "no_milk": "பால் இல்லை", "extra": "கூடுதல்", "incl_extra": "{n} கூடுதல் உட்பட", "pkts": "பாக்கெட்",
        "no_deliveries": "இந்த மாதம் விநியோகம் இல்லை",
        "pay_notice": "பணம் செலுத்தும் முறை",
        "upi_msg": "ரொக்கத்திற்கு பதிலாக GPay / PhonePe / UPI மூலம் செலுத்துங்கள் – வேகமானது, பாதுகாப்பானது, "
                   "சில்லறைப் பிரச்சனையே இல்லை! பணம் செலுத்திய ஸ்கிரீன்ஷாட்டை எங்களுக்கு அனுப்பவும். நன்றி 🙏",
        "upi_line": "UPI / GPay / PhonePe",
        "notes_title": "அறிவிப்புகள்",
        "contact": "தொடர்புக்கு",
        "footer": "இது கணினி மூலம் உருவாக்கப்பட்ட பில். சந்தேகங்களுக்கு {num} ஐ தொடர்பு கொள்ளவும்.",
        "day_by_day": "தினசரி விவரங்கள்:",
        "day_one": "நாள்", "day_many": "நாட்கள்",
        "slip_pay": "UPI / GPay மூலம் செலுத்தவும், ரொக்கம் தவிர்க்கவும், ஸ்கிரீன்ஷாட் அனுப்பவும்.",
        "slip_footer": "கணினி பில். தொடர்புக்கு: {num}",
    },
}

# Shown on receipts until the owner saves his own text (Billing -> message panel)
DEFAULT_MSG = {
    "receipt_greeting_ta": "🙏 வணக்கம்! உங்கள் அன்பான ஆதரவிற்கு மனமார்ந்த நன்றி. "
                           "🥛 தினமும் புத்தம் புதிய ஆவின் / நஞ்சில் பால் & தயிர் – உங்கள் வீடு தேடி, சரியான நேரத்தில்!",
    "receipt_notes_ta": "நஞ்சில் சிவப்பு பால் கிடைக்கும்.\n"
                        "ஆவின் தயிர் கிடைக்கும்.\n"
                        "திருமணம் & விசேஷ நிகழ்ச்சிகளுக்கு பால் வீடு தேடி டெலிவரி செய்யப்படும் (24 மணி நேரத்திற்கு முன் முன்பதிவு அவசியம்).",
    "receipt_greeting_en": "🙏 Hello! Thank you for your kind support. "
                           "🥛 Fresh Aavin / Nanjil milk & curd, delivered to your doorstep every day!",
    "receipt_notes_en": "Nanjil Red Milk available.\n"
                        "Aavin Curd available.\n"
                        "Milk door delivery available for marriages & special functions (24-hour booking required).",
}
