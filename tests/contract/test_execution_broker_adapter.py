from modules.trading.broker_port import BrokerCommandPort


def test_broker_command_port_exposes_only_bounded_actions() -> None:
    names = set(BrokerCommandPort.__dict__)
    assert {
        "submit_order",
        "cancel_order",
        "change_protection",
        "partial_close",
        "full_exit",
    } <= names
    assert "execute_arbitrary" not in names
