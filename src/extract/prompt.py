"""What we tell the model to do with the order image.

The one rule worth defending: it transcribes, it does not calculate. If we let the
model compute the line totals or the VAT, then checking its arithmetic afterwards only
proves it can multiply. We want the printed figures, so validate.py compares two
independent things: what the document claims, and what the numbers actually come to.
"""

EXTRACTION_PROMPT = """\
You are reading a sales order document. Transcribe what is printed on it into the \
required JSON structure.

Rules:

1. Transcribe only. Never calculate, correct, or complete a value. If a total looks \
wrong to you, report it as printed anyway.
2. Numbers carry digits and an optional decimal point, nothing else. No currency \
symbols, no thousands separators. Write 1234.50, not EUR 1,234.50.
3. Percentages are plain numbers. Write 19, not 19%.
4. Dates are YYYY-MM-DD.
5. Copy identifiers, names, streets and descriptions exactly, including case, hyphens \
and spelling. Do not tidy them up.
6. The billing and delivery address blocks are separate and may hold different names \
and different streets. Read each block on its own rather than assuming they match.
7. Read every item row in printed order. Ignore empty rows in the table.
8. A discount cell that is blank, or shows 0%, is "0".
9. When a field is genuinely not on the document, return an empty string. Do not guess \
and do not carry a value over from a different field.
10. Set is_paid true only if the document states it is paid. If it is not paid, \
paid_on is an empty string.

This document is low resolution. Where a digit is ambiguous, prefer the reading that is \
consistent with the rest of the row, but still report what you see rather than what \
would make the totals balance.
"""
