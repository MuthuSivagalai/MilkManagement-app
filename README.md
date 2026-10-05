# 🥛 Milk Delivery Management System — Version 1.0

A simple local milk-delivery management application built with Python, Streamlit and SQLite.

## Features

- Customer management
- Normal/default daily milk quantity
- Actual daily quantity
- Extra milk
- No milk for a day
- Optional daily notes
- Monthly billing
- Payment tracking
- Outstanding balance
- Dashboard
- Daily delivery report
- CSV export
- Local SQLite database

## Requirements

- Windows 10/11
- Python 3.11 or newer
- Internet is needed the first time `run.bat` installs Streamlit.
- After installation, the application runs locally.

## Start the application

1. Extract this ZIP.
2. Double-click `run.bat`.
3. The browser should open automatically.
4. Add customers.
5. Go to **Daily Delivery** every day.
6. Change quantity only when someone takes extra or no milk.
7. Use **Billing** at the end of the month.

## Database

The file `milk_delivery.db` is created automatically in the application folder.

### Important backup

Back up `milk_delivery.db` regularly. It contains your customers, deliveries and payments.

## Example

Customer default:

`Kumar — 1 L/day — ₹50/L`

On a normal day:
`1 L`

Extra day:
`2 L`

No-milk day:
`0 L`

The monthly bill uses the actual saved quantities.

## Next planned versions

Possible Version 2 features:

- PDF monthly bills
- Print bills
- WhatsApp bill sharing
- Customer search
- Outstanding-payment dashboard
- Milk-rate history
- Holiday management
- Automatic monthly bill generation
- Multiple milk types/rates
- Backup/restore button
- Login/password
- Android/mobile-friendly version
