from uuid import uuid4

from modules.trading.charts import empty_chart


def test_chart_context_is_explicitly_read_only_when_data_is_unavailable():
    chart = empty_chart(uuid4(), "EURUSD")
    assert chart.read_only is True
    assert chart.freshness == "UNAVAILABLE"
    assert chart.candles == []
