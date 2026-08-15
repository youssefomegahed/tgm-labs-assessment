"""The JSON shape we force the model to return.

Every number is a string. Asking for a JSON number would hand us a float, and floats
lose cents. The strings get parsed into Decimal in normalize.py, so nothing downstream
ever sees binary floating point.
"""


def _string(description: str) -> dict:
    return {"type": "string", "description": description}


_ADDRESS = {
    "type": "object",
    "properties": {
        "name": _string("Name heading the address block. Often the company, but the "
                        "delivery block may name a different site such as a warehouse."),
        "street": _string("Street and number on one line."),
        "zip_code": _string("Postal code only, no city."),
        "city": _string("City only."),
        "country": _string("Country as printed."),
    },
    "required": ["name", "street", "zip_code", "city", "country"],
}

_ITEM = {
    "type": "object",
    "properties": {
        "position": {"type": "integer", "description": "Row number as printed."},
        "sku": _string("Item number exactly as printed, including hyphens and case."),
        "description": _string("Item description exactly as printed."),
        "quantity": _string("Quantity as a plain number, no unit."),
        "unit": _string("Unit of measure, such as pcs. Empty string if absent."),
        "unit_net": _string("Unit net price, digits and decimal point only."),
        "discount_percent": _string("Line discount as a plain number. '10' not '10%'. "
                                    "'0' when the cell is blank or shows 0%."),
        "vat_percent": _string("VAT rate as a plain number. '19' not '19%'."),
        "line_net": _string("Line total exactly as printed. Do not recompute it."),
    },
    "required": ["position", "sku", "description", "quantity", "unit", "unit_net",
                 "discount_percent", "vat_percent", "line_net"],
}

ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "external_reference": _string("The order's external reference number."),
        "order_date": _string("Order date as YYYY-MM-DD."),
        "currency": _string("Currency code, such as EUR."),
        "debtor": {
            "type": "object",
            "properties": {
                "company": _string("Customer company name."),
                "alias": _string("Customer alias or short code. Empty string if absent."),
                "customer_id": _string("Customer reference printed on the document."),
                "contact": {
                    "type": "object",
                    "properties": {
                        "first_name": _string("Contact given name."),
                        "last_name": _string("Contact family name."),
                        "email": _string("Contact e-mail."),
                        "phone": _string("Contact telephone as printed."),
                    },
                    "required": ["first_name", "last_name", "email", "phone"],
                },
                "billing": _ADDRESS,
                "delivery": _ADDRESS,
            },
            "required": ["company", "alias", "customer_id", "contact", "billing",
                         "delivery"],
        },
        "payment": {
            "type": "object",
            "properties": {
                "method": _string("Payment method as printed, such as Bank Transfer."),
                "is_paid": {"type": "boolean",
                            "description": "True only when the document says PAID."},
                "paid_on": _string("Payment date as YYYY-MM-DD. Empty string when the "
                                   "document is not paid. Never invent this."),
            },
            "required": ["method", "is_paid", "paid_on"],
        },
        "items": {"type": "array", "items": _ITEM},
        "net_total": _string("Net total as printed."),
        "vat_total": _string("VAT total as printed."),
        "gross_total": _string("Gross or order total as printed."),
    },
    "required": ["external_reference", "order_date", "currency", "debtor", "payment",
                 "items", "net_total", "vat_total", "gross_total"],
}
