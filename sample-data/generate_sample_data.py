#!/usr/bin/env python3
"""
Generate seed data + sample purchase-order PDFs for the Order-to-Invoice demo.

Everything (CSV masters and PDFs) comes from the dictionaries below, so the
master data and the order documents can never drift apart.

    python3 generate_sample_data.py

Writes:
    customers.csv      customer master  -> Google Sheet "Customers"
    price_list.csv     SKU master       -> Google Sheet "Price List"
    orders/*.pdf       10 purchase orders: 4 clean, 6 deliberate edge cases
"""

import csv
import io
import os
import random

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS_DIR = os.path.join(HERE, "orders")

PAGE_W, PAGE_H = A4  # 595.28 x 841.89 pt

# The business issuing the invoices. Placeholder identity - swap for your own
# (or keep) before building the invoice template in Step 5.
VENDOR = {
    "name": "Protea Trade Supplies (Pty) Ltd",
    "address": "Unit 12, Meadowbrook Park, 27 Bekker Road",
    "city": "Midrand, 1685",
    "vat": "4180267391",
    "reg": "2019/438921/07",
    "email": "orders@example.com",
}

VAT_RATE = 0.15

# --------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------

CUSTOMERS = {
    "KPW": dict(name="Kalahari Print Works (Pty) Ltd", vat="4290117845",
                reg="2015/221904/07", contact="Lerato Mokoena",
                email="lerato.mokoena@example.com", phone="+27 51 447 2210",
                address="14 Zastron Street, Westdene", city="Bloemfontein, 9301",
                terms="30 days"),
    "UCT": dict(name="Umhlanga Coastal Traders CC", vat="4310558102",
                reg="2011/094433/23", contact="Riaan Pillay",
                email="riaan.pillay@example.com", phone="+27 31 561 8890",
                address="8 Lagoon Drive, Umhlanga Rocks", city="Durban, 4320",
                terms="30 days"),
    "SMH": dict(name="Sandton Media House (Pty) Ltd", vat="4150903377",
                reg="2018/337712/07", contact="Thandi Nkosi",
                email="thandi.nkosi@example.com", phone="+27 11 883 4471",
                address="5th Floor, Rivonia Grove, 22 Rivonia Road",
                city="Sandton, 2196", terms="14 days"),
    "GLG": dict(name="Gqeberha Logistics Group (Pty) Ltd", vat="4220671399",
                reg="2013/118220/07", contact="Sipho Dlamini",
                email="sipho.dlamini@example.com", phone="+27 41 398 1120",
                address="Harbour View Business Park, Kempston Road",
                city="Gqeberha, 6001", terms="45 days"),
    "TBM": dict(name="Table Bay Marine Services (Pty) Ltd", vat="4270448861",
                reg="2016/551208/07", contact="Elmarie van Wyk",
                email="elmarie.vanwyk@example.com", phone="+27 21 419 7734",
                address="Quay 5, Victoria & Alfred Waterfront",
                city="Cape Town, 8001", terms="30 days"),
    "KAS": dict(name="Karoo Agri Solutions (Pty) Ltd", vat="4300229517",
                reg="2012/406651/07", contact="Pieter Grobler",
                email="pieter.grobler@example.com", phone="+27 23 415 3302",
                address="Plot 6, Nelspoort Road", city="Beaufort West, 6970",
                terms="30 days"),
    "HFM": dict(name="Highveld Facilities Management (Pty) Ltd", vat="4180774623",
                reg="2017/229815/07", contact="Nomsa Radebe",
                email="nomsa.radebe@example.com", phone="+27 12 663 9915",
                address="Block C, Highveld Techno Park, 1 Regency Drive",
                city="Centurion, 0157", terms="30 days"),
    "VSF": dict(name="Vaal Steel Fabricators CC", vat="4240336708",
                reg="2009/077410/23", contact="Johan Meyer",
                email="johan.meyer@example.com", phone="+27 16 421 5567",
                address="18 Barrage Road, Duncanville", city="Vereeniging, 1930",
                terms="30 days"),
    "CGE": dict(name="Cederberg Guest Estates (Pty) Ltd", vat="4260910244",
                reg="2014/662180/07", contact="Anele Booysen",
                email="anele.booysen@example.com", phone="+27 27 482 2140",
                address="R364 Pakhuis Pass Road", city="Clanwilliam, 8135",
                terms="14 days"),
    "MLT": dict(name="Mbombela Light Industrial (Pty) Ltd", vat="4200558931",
                reg="2020/114772/07", contact="Kagiso Sithole",
                email="kagiso.sithole@example.com", phone="+27 13 752 6680",
                address="7 Rothery Street, Riverside Industrial",
                city="Mbombela, 1200", terms="30 days"),
}

# sku -> (description, unit price excl. VAT in ZAR)
PRICES = {
    "PTS-1001": ("A4 Bond Paper 80gsm, box of 5 reams", 389.00),
    "PTS-1002": ("Toner Cartridge, mono high-yield", 1249.00),
    "PTS-1015": ("Branded Notebook A5, pack of 25", 812.50),
    "PTS-2003": ("Safety Boots, steel toe, per pair", 649.00),
    "PTS-2007": ("Hi-Vis Vest, Class 2, pack of 10", 445.00),
    "PTS-3001": ("Corrugated Shipping Box 400x300x300, pack of 20", 528.00),
    "PTS-3010": ("Pallet Wrap 500mm, per roll", 187.50),
    "PTS-4002": ("Site Signage Board 600x900, printed", 1095.00),
    "PTS-4008": ("Vehicle Decal Set, printed and cut", 2340.00),
    "PTS-5001": ("On-site Installation, per hour", 585.00),
    "PTS-5002": ("Delivery - Gauteng Metro", 350.00),
    "PTS-5003": ("Delivery - National Outlying", 875.00),
}

# --------------------------------------------------------------------------
# The orders. One deliberate defect per file so demo routing is unambiguous.
# --------------------------------------------------------------------------

ORDERS = [
    dict(file="01-clean-kalahari.pdf", customer="KPW", po="PO-2026-0417",
         date="2026-08-24", delivery="2026-09-04",
         lines=[("PTS-1001", 6), ("PTS-1002", 2), ("PTS-5002", 1)]),

    dict(file="02-clean-umhlanga.pdf", customer="UCT", po="PO-2026-0418",
         date="2026-08-25", delivery="2026-09-08",
         lines=[("PTS-3001", 15), ("PTS-3010", 24)]),

    dict(file="03-clean-sandton.pdf", customer="SMH", po="PO-2026-0419",
         date="2026-08-26", delivery="2026-09-02",
         lines=[("PTS-1015", 4), ("PTS-4008", 2), ("PTS-4002", 3), ("PTS-5001", 6)]),

    dict(file="04-clean-gqeberha.pdf", customer="GLG", po="PO-2026-0420",
         date="2026-08-27", delivery="2026-09-11",
         lines=[("PTS-2003", 12), ("PTS-2007", 8), ("PTS-5003", 1)]),

    # Edge 1: no PO number anywhere on the document.
    dict(file="05-edge-missing-po-number.pdf", customer="TBM", po=None,
         date="2026-08-27", delivery="2026-09-09",
         lines=[("PTS-2007", 20), ("PTS-3010", 10)]),

    # Edge 2: line totals print correctly but the subtotal is understated by
    # R1 200.00, so VAT and grand total are wrong too.
    dict(file="06-edge-totals-do-not-add-up.pdf", customer="KAS", po="PO-2026-0422",
         date="2026-08-28", delivery="2026-09-15",
         lines=[("PTS-2003", 10), ("PTS-1001", 4), ("PTS-5003", 1)],
         subtotal_error=-1200.00),

    # Edge 3: buyer is not in the customer master.
    dict(file="07-edge-unknown-customer.pdf", customer=None, po="PO-2026-0423",
         date="2026-08-28", delivery="2026-09-10",
         unknown_customer=dict(
             name="Nkosi Brothers Hardware CC", vat="4310992006",
             reg="2010/338811/23", contact="Bongani Nkosi",
             email="bongani.nkosi@example.com", phone="+27 35 789 1140",
             address="42 Commercial Road", city="Richards Bay, 3900",
             terms="30 days"),
         lines=[("PTS-3001", 8), ("PTS-1001", 3)]),

    # Edge 4: byte-different resend of order 01, same PO number.
    dict(file="08-edge-duplicate-of-01.pdf", customer="KPW", po="PO-2026-0417",
         date="2026-08-24", delivery="2026-09-04", resend=True,
         lines=[("PTS-1001", 6), ("PTS-1002", 2), ("PTS-5002", 1)]),

    # Edge 5: scanned/photocopied - no text layer, forces the vision fallback.
    dict(file="09-edge-scanned-no-text-layer.pdf", customer="VSF", po="PO-2026-0425",
         date="2026-08-29", delivery="2026-09-16", scanned=True,
         lines=[("PTS-2003", 6), ("PTS-4002", 2), ("PTS-5001", 4)]),

    # Edge 6: a SKU that is not in the price list.
    dict(file="10-edge-unknown-sku.pdf", customer="HFM", po="PO-2026-0426",
         date="2026-08-31", delivery="2026-09-14",
         lines=[("PTS-1001", 5), ("PTS-9999", 3), ("PTS-5002", 1)],
         extra_skus={"PTS-9999": ("Cleaning Consumables Bundle, monthly", 1480.00)}),
]


# --------------------------------------------------------------------------
# Layout: build a list of draw commands once, render it two ways.
# Commands use top-left origin, points. ("text", x, y, s, size, bold)
# --------------------------------------------------------------------------

def money(v):
    return f"{v:,.2f}".replace(",", " ")


def build_layout(order):
    cust = order.get("unknown_customer") or CUSTOMERS[order["customer"]]
    prices = dict(PRICES, **order.get("extra_skus", {}))

    cmds = []
    def text(x, y, s, size=9, bold=False, align="l"):
        cmds.append(("text", x, y, str(s), size, bold, align))
    def line(x1, y, x2, w=0.6):
        cmds.append(("line", x1, y, x2, w))
    def rect(x, y, w, h):
        cmds.append(("rect", x, y, w, h))

    L, R = 50, PAGE_W - 50

    # Buyer letterhead
    text(L, 60, cust["name"], 15, True)
    text(L, 78, cust["address"], 8.5)
    text(L, 90, cust["city"], 8.5)
    text(L, 102, f"VAT Reg No: {cust['vat']}    Co Reg No: {cust['reg']}", 8.5)
    text(L, 114, f"Tel: {cust['phone']}    {cust['email']}", 8.5)

    text(R, 62, "PURCHASE ORDER", 17, True, align="r")
    if order.get("resend"):
        text(R, 80, "** RESEND - PLEASE DISREGARD EARLIER COPY **", 8, True, align="r")

    line(L, 128, R, 1.2)

    # Order meta block
    y = 150
    if order["po"]:
        text(L, y, "Order Number", 8, True)
        text(L, y + 13, order["po"], 10)
    else:
        text(L, y, "Order Number", 8, True)
        text(L, y + 13, "-", 10)

    text(L + 170, y, "Order Date", 8, True)
    text(L + 170, y + 13, order["date"], 10)

    text(L + 320, y, "Required By", 8, True)
    text(L + 320, y + 13, order["delivery"], 10)

    # Vendor block
    y = 196
    text(L, y, "SUPPLIER", 8, True)
    text(L, y + 14, VENDOR["name"], 10, True)
    text(L, y + 27, VENDOR["address"], 8.5)
    text(L, y + 38, VENDOR["city"], 8.5)
    text(L, y + 49, f"VAT Reg No: {VENDOR['vat']}", 8.5)

    text(L + 320, y, "DELIVER TO", 8, True)
    text(L + 320, y + 14, cust["name"], 10, True)
    text(L + 320, y + 27, cust["address"], 8.5)
    text(L + 320, y + 38, cust["city"], 8.5)
    text(L + 320, y + 49, f"Attention: {cust['contact']}", 8.5)

    # Line item table
    top = 276
    col_sku, col_desc, col_qty, col_unit, col_tot = L, L + 82, L + 330, L + 390, R
    rect(L, top, R - L, 20)
    text(col_sku + 4, top + 14, "SKU", 8.5, True)
    text(col_desc, top + 14, "DESCRIPTION", 8.5, True)
    text(col_qty, top + 14, "QTY", 8.5, True, align="r")
    text(col_unit, top + 14, "UNIT PRICE", 8.5, True, align="r")
    text(col_tot - 4, top + 14, "LINE TOTAL", 8.5, True, align="r")

    y = top + 20
    computed_subtotal = 0.0
    for sku, qty in order["lines"]:
        desc, unit = prices[sku]
        line_total = round(unit * qty, 2)
        computed_subtotal += line_total
        y += 20
        text(col_sku + 4, y, sku, 9)
        text(col_desc, y, desc, 9)
        text(col_qty, y, qty, 9, align="r")
        text(col_unit, y, money(unit), 9, align="r")
        text(col_tot - 4, y, money(line_total), 9, align="r")
        line(L, y + 6, R, 0.3)

    # Totals - the printed subtotal may deliberately disagree with the lines.
    printed_subtotal = round(computed_subtotal + order.get("subtotal_error", 0.0), 2)
    printed_vat = round(printed_subtotal * VAT_RATE, 2)
    printed_total = round(printed_subtotal + printed_vat, 2)

    y += 34
    text(col_unit, y, "Subtotal (excl. VAT)", 9, align="r")
    text(col_tot - 4, y, f"R {money(printed_subtotal)}", 9, align="r")
    y += 16
    text(col_unit, y, "VAT @ 15%", 9, align="r")
    text(col_tot - 4, y, f"R {money(printed_vat)}", 9, align="r")
    y += 8
    line(col_unit - 60, y, R, 0.6)
    y += 16
    text(col_unit, y, "TOTAL DUE (ZAR)", 10, True, align="r")
    text(col_tot - 4, y, f"R {money(printed_total)}", 10, True, align="r")

    # Footer
    y += 60
    text(L, y, f"Payment terms: {cust['terms']} from date of invoice.", 8.5)
    text(L, y + 13, "Please quote the order number on all invoices and delivery notes.", 8.5)
    text(L, y + 38, f"Authorised by: {cust['contact']}", 9)
    line(L, y + 56, L + 200, 0.6)
    text(L, y + 68, "Signature", 7.5)

    return cmds


# --------------------------------------------------------------------------
# Renderer A: real PDF with a text layer (reportlab)
# --------------------------------------------------------------------------

def render_pdf(cmds, path):
    c = pdfcanvas.Canvas(path, pagesize=A4)
    for cmd in cmds:
        if cmd[0] == "text":
            _, x, y, s, size, bold, align = cmd
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            yy = PAGE_H - y
            if align == "r":
                c.drawRightString(x, yy, s)
            else:
                c.drawString(x, yy, s)
        elif cmd[0] == "line":
            _, x1, y, x2, w = cmd
            c.setLineWidth(w)
            c.line(x1, PAGE_H - y, x2, PAGE_H - y)
        elif cmd[0] == "rect":
            _, x, y, w, h = cmd
            c.setLineWidth(0.6)
            c.rect(x, PAGE_H - y - h, w, h, stroke=1, fill=0)
    c.showPage()
    c.save()


# --------------------------------------------------------------------------
# Renderer B: rasterised "scan" - no text layer at all (PIL -> reportlab image)
# --------------------------------------------------------------------------

FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Helvetica.ttc"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _fonts():
    for regular, bold in FONT_CANDIDATES:
        if os.path.exists(regular):
            return regular, bold if os.path.exists(bold) else regular
    return None, None


def render_scan(cmds, path, dpi=150):
    scale = dpi / 72.0
    W, H = int(PAGE_W * scale), int(PAGE_H * scale)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    reg_path, bold_path = _fonts()
    cache = {}

    def font(size, bold):
        key = (round(size * scale), bold)
        if key not in cache:
            if reg_path:
                cache[key] = ImageFont.truetype(bold_path if bold else reg_path, key[0])
            else:
                cache[key] = ImageFont.load_default()
        return cache[key]

    for cmd in cmds:
        if cmd[0] == "text":
            _, x, y, s, size, bold, align = cmd
            f = font(size, bold)
            px, py = x * scale, y * scale - size * scale
            if align == "r":
                px -= d.textlength(s, font=f)
            d.text((px, py), s, fill=(15, 15, 15), font=f)
        elif cmd[0] == "line":
            _, x1, y, x2, w = cmd
            d.line([(x1 * scale, y * scale), (x2 * scale, y * scale)],
                   fill=(40, 40, 40), width=max(1, int(w * scale)))
        elif cmd[0] == "rect":
            _, x, y, w, h = cmd
            d.rectangle([x * scale, y * scale, (x + w) * scale, (y + h) * scale],
                        outline=(40, 40, 40), width=1)

    # Make it look photocopied: slight skew, grain, soft focus, grey cast.
    img = img.rotate(-0.35, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    img = img.convert("L")
    px = img.load()
    rnd = random.Random(7)
    for _ in range((W * H) // 90):
        rx, ry = rnd.randrange(W), rnd.randrange(H)
        px[rx, ry] = max(0, px[rx, ry] - rnd.randrange(25, 90))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    img = img.point(lambda v: min(255, int(v * 0.96) + 6))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=72)
    buf.seek(0)

    c = pdfcanvas.Canvas(path, pagesize=A4)
    c.drawImage(ImageReader(buf), 0, 0, width=PAGE_W, height=PAGE_H)
    c.showPage()
    c.save()


# --------------------------------------------------------------------------
# CSV masters
# --------------------------------------------------------------------------

def write_masters():
    cust_path = os.path.join(HERE, "customers.csv")
    with open(cust_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_code", "company_name", "vat_number",
                    "registration_number", "contact_name", "email", "phone",
                    "address", "city", "payment_terms"])
        for code, c in CUSTOMERS.items():
            w.writerow([code, c["name"], c["vat"], c["reg"], c["contact"],
                        c["email"], c["phone"], c["address"], c["city"], c["terms"]])

    price_path = os.path.join(HERE, "price_list.csv")
    with open(price_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "description", "unit_price_excl_vat", "currency"])
        for sku, (desc, price) in PRICES.items():
            w.writerow([sku, desc, f"{price:.2f}", "ZAR"])

    return cust_path, price_path


def main():
    os.makedirs(ORDERS_DIR, exist_ok=True)
    cust_path, price_path = write_masters()
    print(f"wrote {os.path.basename(cust_path)}  ({len(CUSTOMERS)} customers)")
    print(f"wrote {os.path.basename(price_path)}  ({len(PRICES)} SKUs)")
    print()

    for order in ORDERS:
        cmds = build_layout(order)
        path = os.path.join(ORDERS_DIR, order["file"])
        if order.get("scanned"):
            render_scan(cmds, path)
            note = "rasterised, no text layer"
        else:
            render_pdf(cmds, path)
            note = "text layer"
        print(f"wrote orders/{order['file']:<38} ({note})")


if __name__ == "__main__":
    main()
