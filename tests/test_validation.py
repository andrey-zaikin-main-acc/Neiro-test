from app.services.validation import validate_bom


def test_validate_bom_detects_missing_and_bad_quantity():
    result = validate_bom([{"designator": "R1", "part_number": "", "quantity": 0}])
    assert not result["is_valid"]
    assert result["critical_errors"] == 2
