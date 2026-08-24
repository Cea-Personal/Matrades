from pathlib import Path

PROHIBITED = (
    "order_send(",
    "place_order(",
    "modify_position(",
    "close_position(",
    "/orders/create",
    "/positions/modify",
)


def test_repository_contains_no_v1_broker_write_interface():
    roots = (Path("apps"), Path("modules"), Path("adapters"), Path("bridges"), Path("packages"))
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix in {".py", ".ts", ".tsx"}:
                text = path.read_text().lower()
                if any(token in text for token in PROHIBITED):
                    offenders.append(str(path))
    assert offenders == []
