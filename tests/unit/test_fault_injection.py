"""Unit tests for fault injection system."""

import asyncio
import pytest
from localostack.core.fault_injection import FaultRule, FaultRegistry, make_fault_middleware


class TestFaultRule:
    def test_default_id_is_uuid(self):
        rule = FaultRule()
        assert len(rule.id) == 36  # UUID format

    def test_defaults(self):
        rule = FaultRule()
        assert rule.service == "*"
        assert rule.method == "*"
        assert rule.path_pattern == "*"
        assert rule.action == "error"
        assert rule.count == 0
        assert rule.probability == 1.0


class TestFaultRegistry:
    def setup_method(self):
        self.registry = FaultRegistry()

    def test_add_and_list(self):
        rule = FaultRule(service="nova", path_pattern="/v2.1/servers")
        self.registry.add_rule(rule)
        rules = self.registry.get_rules()
        assert len(rules) == 1
        assert rules[0].id == rule.id

    def test_match_wildcard(self):
        rule = FaultRule(service="*", method="*", path_pattern="*")
        self.registry.add_rule(rule)
        matched = self.registry.match("nova", "GET", "/v2.1/servers")
        assert matched is not None
        assert matched.id == rule.id

    def test_match_service_filter(self):
        self.registry.add_rule(FaultRule(service="neutron"))
        assert self.registry.match("nova", "GET", "/v2.1/servers") is None
        assert self.registry.match("neutron", "GET", "/v2.0/networks") is not None

    def test_match_method_filter(self):
        self.registry.add_rule(FaultRule(service="*", method="POST"))
        assert self.registry.match("nova", "GET", "/v2.1/servers") is None
        assert self.registry.match("nova", "POST", "/v2.1/servers") is not None

    def test_match_path_glob(self):
        self.registry.add_rule(FaultRule(path_pattern="/v2.1/servers/*"))
        assert self.registry.match("nova", "GET", "/v2.1/servers/abc-123") is not None
        assert self.registry.match("nova", "GET", "/v2.1/servers") is None

    def test_match_path_regex(self):
        self.registry.add_rule(FaultRule(path_pattern="regex:/v2\\.1/servers/[^/]+"))
        assert self.registry.match("nova", "GET", "/v2.1/servers/abc") is not None
        assert self.registry.match("nova", "GET", "/v2.1/servers") is None

    def test_count_exhaustion(self):
        rule = FaultRule(count=2)
        self.registry.add_rule(rule)
        # Simulate 2 hits already
        rule._hit_count = 2
        assert self.registry.match("nova", "GET", "/") is None

    def test_probability_zero(self):
        self.registry.add_rule(FaultRule(probability=0.0))
        # With probability 0.0, random() > 0.0 is always True so match returns None
        results = [self.registry.match("nova", "GET", "/") for _ in range(20)]
        assert all(r is None for r in results)

    def test_remove_rule(self):
        rule = self.registry.add_rule(FaultRule())
        assert self.registry.remove_rule(rule.id) is True
        assert self.registry.get_rules() == []

    def test_clear(self):
        self.registry.add_rule(FaultRule())
        self.registry.add_rule(FaultRule())
        self.registry.clear()
        assert self.registry.get_rules() == []


class TestFaultMiddleware:
    def setup_method(self):
        self.registry = FaultRegistry()

    def _make_mock_request(self, method="GET", path="/test"):
        """Create a minimal mock request."""
        class MockURL:
            def __init__(self, p): self.path = p
        class MockRequest:
            def __init__(self, m, p):
                self.method = m
                self.url = MockURL(p)
        return MockRequest(method, path)

    @pytest.mark.asyncio
    async def test_no_rule_passes_through(self):
        middleware = make_fault_middleware(self.registry, "nova")
        request = self._make_mock_request()

        async def call_next(req):
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": True})

        response = await middleware(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_error_action_returns_status_code(self):
        self.registry.add_rule(FaultRule(action="error", status_code=503))
        middleware = make_fault_middleware(self.registry, "nova")
        request = self._make_mock_request()

        response = await middleware(request, lambda r: None)
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_delay_action_still_calls_next(self):
        self.registry.add_rule(FaultRule(action="delay", delay_ms=10))
        middleware = make_fault_middleware(self.registry, "nova")
        request = self._make_mock_request()
        called = []

        async def call_next(req):
            called.append(True)
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": True})

        response = await middleware(request, call_next)
        assert called == [True]
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_hit_count_increments(self):
        rule = self.registry.add_rule(FaultRule(action="error", status_code=500))
        middleware = make_fault_middleware(self.registry, "nova")
        request = self._make_mock_request()

        await middleware(request, lambda r: None)
        await middleware(request, lambda r: None)

        assert rule._hit_count == 2

    @pytest.mark.asyncio
    async def test_count_one_then_passthrough(self):
        """count=1: first call fails, second call passes through."""
        self.registry.add_rule(FaultRule(action="error", status_code=503, count=1))
        middleware = make_fault_middleware(self.registry, "nova")
        request = self._make_mock_request()

        # First call: fault injected
        r1 = await middleware(request, lambda r: None)
        assert r1.status_code == 503

        # Second call: passes through
        async def ok_next(req):
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": True})

        r2 = await middleware(request, ok_next)
        assert r2.status_code == 200
