from app.ratelimit import RateLimiter


def test_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter(limit=3, window_s=60)
    assert [limiter.check("ip1")[0] for _ in range(3)] == [True, True, True]

    allowed, retry_after = limiter.check("ip1")
    assert allowed is False
    assert 0 < retry_after <= 60


def test_blocked_request_reports_how_long_to_wait():
    clock = {"now": 100.0}
    limiter = RateLimiter(limit=1, window_s=60, clock=lambda: clock["now"])
    limiter.check("ip1")

    clock["now"] = 140.0  # the hit is 40 s old, 20 s left in the window
    allowed, retry_after = limiter.check("ip1")
    assert allowed is False
    assert 19 <= retry_after <= 20


def test_window_slides_so_old_hits_stop_counting():
    clock = {"now": 0.0}
    limiter = RateLimiter(limit=2, window_s=60, clock=lambda: clock["now"])
    limiter.check("ip1")          # t = 0
    clock["now"] = 59.0
    limiter.check("ip1")          # t = 59 -> window full

    clock["now"] = 60.5           # the t=0 hit has aged out of the window
    allowed, _ = limiter.check("ip1")
    assert allowed is True
    assert limiter.check("ip1")[0] is False   # refilled again


def test_clients_do_not_share_each_others_windows():
    limiter = RateLimiter(limit=1, window_s=60)
    assert limiter.check("ip1")[0] is True
    assert limiter.check("ip1")[0] is False
    # A different client is untouched by ip1 exhausting its quota.
    assert limiter.check("ip2")[0] is True


def test_recommend_route_is_wired_to_the_limiter():
    # The limit is worthless if it is not attached to the endpoint.
    from fastapi.routing import APIRoute
    from app.main import app

    route = next(r for r in app.routes
                 if isinstance(r, APIRoute) and r.path == "/recommend")
    assert len(route.dependencies) >= 1


def test_health_is_not_rate_limited():
    # /health must stay reachable even when /recommend is throttled.
    from fastapi.routing import APIRoute
    from app.main import app

    route = next(r for r in app.routes
                 if isinstance(r, APIRoute) and r.path == "/health")
    assert len(route.dependencies) == 0
