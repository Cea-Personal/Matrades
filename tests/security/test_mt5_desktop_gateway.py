from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_gateway_requires_authentication_for_assets_and_websocket() -> None:
    config = (ROOT / "bridges/mt5/nginx.conf.template").read_text(encoding="utf-8")

    assert "return 302 /desktop/vnc.html?autoconnect=1&path=websockify;" in config
    assert config.count('auth_basic "Matrades MT5 desktop";') == 2
    assert config.count("auth_basic_user_file /tmp/matrades-mt5-desktop.htpasswd;") == 2
    assert "location = /desktop/websockify" in config
    assert "proxy_set_header Upgrade $http_upgrade;" in config
    assert "proxy_pass http://127.0.0.1:6080;" in config
    assert "location = /status" in config
    assert "proxy_pass http://127.0.0.1:18765;" in config


def test_vnc_and_bridge_listen_only_on_loopback() -> None:
    startup = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "--host 127.0.0.1 --port \"$BRIDGE_PORT\"" in startup
    assert "x11vnc -display \"$DISPLAY\" -rfbport 5900 -localhost" in startup
    assert "websockify 127.0.0.1:6080 127.0.0.1:5900" in startup
    assert "MATRADES_MT5_DESKTOP_PASSWORD" in startup
    assert "htpasswd -i -c -5" in startup
