"""
HSBC statement PDF extractor.
Uses pdfplumber word-level x-coordinates to identify which column
(Description / Paid Out / Paid In / Balance) each number belongs to.
"""

import pdfplumber
import pandas as pd
import re

# Column x-boundaries (pixels) — derived from header word positions in HSBC PDFs
DATE_MAX_X     = 100   # day/month/year date tokens
DESC_MAX_X     = 340   # description / payment type
PAID_OUT_MAX_X = 440   # £Paid out column
PAID_IN_MAX_X  = 510   # £Paid in column
# x >= PAID_IN_MAX_X → £Balance column

SKIP_PHRASES = {
    "BALANCEBROUGHTFORWARD", "BALANCECARRIEDFORWARD",
    "Date", "Payment", "type", "and", "details",
    "£Paid", "out", "in", "£Balance",
    "Your", "Student", "Bank", "Account",
    "Contact", "tel", "see", "reverse", "for", "call", "times",
    "Text", "phone", "used", "by", "deaf", "or", "speech",
    "impaired", "customers", "www.hsbc.co.uk",
    "1", "High", "Street", "Doncaster", "South", "Yorkshire",
    "DN1", "1EE", "Sheet", "Number", "Sortcode",
    "Information", "about", "the", "Financial", "Services",
    "Compensation", "Scheme",
}

MONTH_ABBREVS = {
    'Jan','Feb','Mar','Apr','May','Jun',
    'Jul','Aug','Sep','Oct','Nov','Dec'
}


def is_amount(text: str) -> bool:
    """Match numbers like 674.00 or 1,256.66"""
    return bool(re.match(r'^\d{1,3}(?:,\d{3})*(?:\.\d{2})?$', text))


def parse_amount(text: str) -> float:
    return float(text.replace(',', ''))


def is_sheet_number_bleed(paid_in: float, paid_out: float, desc: str) -> bool:
    """
    The account info footer line contains the sheet number (e.g. '280') which
    falls in the £Paid in column x-range. Detect and skip these false rows.
    """
    return (
        paid_out == 0.0
        and paid_in < 1000
        and paid_in == int(paid_in)
        and any(marker in desc for marker in ('Cojocaru', '40-19-20', '24138015'))
    )


def extract_transactions(pdf_path: str) -> pd.DataFrame:
    rows = []
    current_date = None
    pending_desc = []   # description tokens from lines with no amount (continuation lines)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Stop once we've left the transaction section — T&C pages don't have this header
            if 'Student Bank Account' not in (page.extract_text() or ''):
                break
            words = page.extract_words()
            if not words:
                continue

            # Group words by row (y position, rounded to nearest 3px)
            lines: dict = {}
            for w in words:
                y_key = round(w['top'] / 3) * 3
                lines.setdefault(y_key, []).append(w)

            for y_key in sorted(lines.keys()):
                line_words = sorted(lines[y_key], key=lambda w: w['x0'])

                date_tokens = []
                desc_tokens = []
                paid_out_val = None
                paid_in_val  = None
                balance_val  = None

                for w in line_words:
                    text = w['text'].strip()
                    if not text or text in SKIP_PHRASES:
                        continue
                    x = w['x0']

                    if x < DATE_MAX_X:
                        if re.match(r'^\d{1,2}$', text) or text in MONTH_ABBREVS:
                            date_tokens.append(text)
                    elif x < DESC_MAX_X:
                        desc_tokens.append(text)
                    elif x < PAID_OUT_MAX_X:
                        if is_amount(text):
                            paid_out_val = parse_amount(text)
                    elif x < PAID_IN_MAX_X:
                        if is_amount(text):
                            paid_in_val = parse_amount(text)
                    else:  # Balance column
                        if is_amount(text):
                            balance_val = parse_amount(text)

                # Update running date when we see day + month (+ optional 2-digit year)
                if len(date_tokens) >= 2:
                    date_str = ' '.join(date_tokens[:3])
                    try:
                        current_date = pd.to_datetime(date_str, format='%d %b %y')
                    except Exception:
                        pass

                has_amount = paid_out_val is not None or paid_in_val is not None

                if not has_amount:
                    # Buffer description for the next line that carries the amount
                    if desc_tokens:
                        pending_desc.extend(desc_tokens)
                    continue

                # Merge buffered prefix with this line's description
                full_desc = ' '.join(pending_desc + desc_tokens).strip().lstrip('. ')
                pending_desc = []

                po = paid_out_val or 0.0
                pi = paid_in_val  or 0.0

                # Skip account-info footer rows where the sheet number bleeds into Paid In
                if is_sheet_number_bleed(pi, po, full_desc):
                    continue

                if current_date is not None:
                    rows.append({
                        'Date':        current_date,
                        'Description': full_desc,
                        'Paid Out':    po,
                        'Paid In':     pi,
                        'Balance':     balance_val,
                    })

    df = pd.DataFrame(rows)

    # HSBC only prints the balance at end-of-day, not on every line.
    # Back-calculate the opening balance from the first known anchor, then roll forward.
    first_known = df["Balance"].first_valid_index()
    if first_known is not None:
        running = df.loc[first_known, "Balance"]
        for i in range(first_known, -1, -1):
            running = round(running + df.loc[i, "Paid Out"] - df.loc[i, "Paid In"], 2)
        for i in df.index:
            running = round(running - df.loc[i, "Paid Out"] + df.loc[i, "Paid In"], 2)
            df.loc[i, "Balance"] = running

    return df


if __name__ == '__main__':
    import sys
    pdf_path   = sys.argv[1] if len(sys.argv) > 1 else '2026-03-27_Statement-1.pdf'
    output_csv = sys.argv[2] if len(sys.argv) > 2 else 'transactions.csv'

    df = extract_transactions(pdf_path)
    df.to_csv(output_csv, index=False)

    print(df.to_string())
    print(f"\nRows:      {len(df)}")
    print(f"Paid out:  £{df['Paid Out'].sum():.2f}")
    print(f"Paid in:   £{df['Paid In'].sum():.2f}")
    print(f"\nSaved to {output_csv}")