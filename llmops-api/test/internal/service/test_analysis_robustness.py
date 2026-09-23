import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from internal.service.analysis_service import AnalysisService


class FailingWriteCache:
    def __init__(self, cached_value=None):
        self.cached_value = cached_value
        self.setex_calls = []

    def exists(self, _key):
        return self.cached_value is not None

    def get(self, _key):
        return self.cached_value

    def setex(self, *args):
        self.setex_calls.append(args)
        raise ConnectionError("redis unavailable")


def _message(created_at: datetime):
    return SimpleNamespace(
        conversation_id=uuid4(),
        created_by=uuid4(),
        latency=2.0,
        total_token_count=10,
        total_price=Decimal("0.00125"),
        created_at=created_at,
    )


def test_analysis_returns_calculated_data_when_cache_is_corrupt_or_write_fails(monkeypatch):
    app = SimpleNamespace(id=uuid4())
    cache = FailingWriteCache(cached_value=b"not-json")
    service = AnalysisService(
        db=None,
        redis_client=cache,
        app_service=SimpleNamespace(get_app=lambda *_: app),
    )
    message = _message(datetime.now() - timedelta(days=1))
    monkeypatch.setattr(service, "get_messages_by_time_range", lambda *_: [message])

    result = service.get_app_analysis(app.id, SimpleNamespace())

    assert result["total_messages"]["data"] == 1
    assert result["cost_consumption"]["data"] == 0.00125
    assert result["cost_consumption_trend"]["y_axis"].count(0.00125) == 1
    assert cache.setex_calls
    json.dumps(result)


def test_analysis_empty_metrics_and_pop_are_zero_and_json_serializable():
    overview = AnalysisService.calculate_overview_indicators_by_messages([])
    pop = AnalysisService.calculate_pop_by_overview_indicators(overview, overview)
    trend = AnalysisService.calculate_trend_by_messages(datetime.now(), 7, [])

    assert overview == {
        "total_messages": 0,
        "active_accounts": 0,
        "avg_of_conversation_messages": 0.0,
        "token_output_rate": 0.0,
        "cost_consumption": 0.0,
    }
    assert set(pop.values()) == {0}
    assert trend["cost_consumption_trend"]["y_axis"] == [0.0] * 7
    json.dumps({**overview, **pop, **trend})
