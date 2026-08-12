from pathlib import Path


def test_production_source_exposes_no_real_money_order_or_scraping_capability() -> None:
    source = "\n".join(path.read_text() for path in Path("src").rglob("*.py"))
    forbidden = (
        "submit_order",
        "place_order",
        "create_live_order",
        "selenium",
        "playwright.sync_api",
    )
    assert not any(term in source.lower() for term in forbidden)
