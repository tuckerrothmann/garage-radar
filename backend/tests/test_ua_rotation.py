from garage_radar.sources.shared.ua_rotation import get_headers


def test_get_headers_avoid_brotli():
    headers = get_headers(referer="https://bringatrailer.com")

    assert headers["Accept-Encoding"] == "gzip, deflate"
