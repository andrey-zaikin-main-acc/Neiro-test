REQUIRED_BOM_FIELDS = ("designator", "part_number", "quantity")


def validate_bom(rows: list[dict]) -> dict:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        for field in REQUIRED_BOM_FIELDS:
            if row.get(field) in (None, ""):
                errors.append(f"row {index}: missing {field}")
        quantity = row.get("quantity")
        if quantity is not None:
            try:
                if int(quantity) <= 0:
                    errors.append(f"row {index}: quantity must be positive")
            except (TypeError, ValueError):
                errors.append(f"row {index}: quantity is not an integer")
    return {"is_valid": not errors, "critical_errors": len(errors), "errors": errors}
