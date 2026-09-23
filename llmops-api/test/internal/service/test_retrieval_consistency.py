from types import SimpleNamespace
from uuid import uuid4

from langchain_core.documents import Document as LCDocument

from internal.core.retrievers.full_text_retriever import FullTextRetriever
from internal.entity.dataset_entity import DocumentStatus, SegmentStatus


def test_full_text_retriever_queries_only_enabled_completed_segments(monkeypatch):
    """关键词表可能滞后，数据库查询必须是最终可见性边界。"""
    dataset_id = uuid4()
    segment_id = uuid4()
    captured = []

    class Query:
        def with_entities(self, *_):
            return self

        def filter(self, *criteria):
            captured.extend(criteria)
            return self

        def all(self):
            return [({"keyword": [str(segment_id)]},)]

    class SegmentQuery(Query):
        def join(self, *_):
            return self

        def all(self):
            return [SimpleNamespace(
                id=segment_id, account_id=uuid4(), dataset_id=dataset_id,
                document_id=uuid4(), node_id=uuid4(), content="visible",
            )]

    db = SimpleNamespace(session=SimpleNamespace(query=lambda model: SegmentQuery() if model.__name__ == "Segment" else Query()))
    retriever = FullTextRetriever.model_construct(
        db=db, dataset_ids=[dataset_id], jieba_services=SimpleNamespace(extract_keywords=lambda *_: ["keyword"]),
        search_kwargs={"k": 4},
    )
    assert [item.page_content for item in retriever.invoke("keyword")] == ["visible"]
    values = [getattr(getattr(criteria, "right", None), "value", None) for criteria in captured]
    assert DocumentStatus.COMPLETED in values
    assert SegmentStatus.COMPLETED in values


def test_retrieval_discards_stale_vector_results_before_counting_hits(monkeypatch):
    from internal.service.retrieval_service import RetrievalService

    dataset_id, stale_id, live_id, account_id = uuid4(), uuid4(), uuid4(), uuid4()
    stale = LCDocument(page_content="stale", metadata={"segment_id": str(stale_id), "dataset_id": str(dataset_id)})
    live = LCDocument(page_content="live", metadata={"segment_id": str(live_id), "dataset_id": str(dataset_id)})

    class Semantic:
        def __init__(self, **_):
            pass

        def invoke(self, _):
            return [stale, live]

    class FullText:
        def __init__(self, **_):
            pass

    class Ensemble:
        def __init__(self, **_):
            pass

        def invoke(self, _):
            return [stale, live]

    monkeypatch.setattr("internal.core.retrievers.SemanticRetriever", Semantic)
    monkeypatch.setattr("internal.core.retrievers.FullTextRetriever", FullText)
    monkeypatch.setattr("internal.service.retrieval_service.EnsembleRetriever", Ensemble)
    session = SimpleNamespace(query=lambda *_: None)
    service = RetrievalService(db=SimpleNamespace(session=session), jieba_service=SimpleNamespace(), vector_database_service=SimpleNamespace(vector_store=object()))
    # 细节查询由该服务方法封装，避免让过期向量进入查询记录和 hit_count。
    monkeypatch.setattr(service, "_get_visible_segments", lambda *_: {str(live_id): live_id})
    monkeypatch.setattr(service, "create", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_increment_hits", lambda ids: setattr(service, "hit_ids", ids))
    monkeypatch.setattr(session, "query", lambda *_: SimpleNamespace(filter=lambda *_: SimpleNamespace(all=lambda: [SimpleNamespace(id=dataset_id)])))
    result = service.search_in_datasets([dataset_id], "query", account_id)
    assert [item.page_content for item in result] == ["live"]
    assert service.hit_ids == [live_id]
