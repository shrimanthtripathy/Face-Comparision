import re, socket
import launcher

def test_free_port_prefers_the_requested_port_but_falls_back():
    assert 1024 < launcher.free_port() < 65536
    s = socket.socket(); s.bind(("", 0)); s.listen(1); busy = s.getsockname()[1]
    try: assert launcher.free_port(busy) != busy
    finally: s.close()

def test_lan_ip_looks_like_an_address():
    assert re.match(r"^\d{1,3}(\.\d{1,3}){3}$", launcher.lan_ip())
