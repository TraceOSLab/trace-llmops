from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from test.integration.conftest import assert_success


pytestmark = pytest.mark.integration


@pytest.fixture()
def dataset_and_upload(account, db_session):
    from internal.model import Dataset, UploadFile

    dataset = Dataset(
        id=uuid4(),
        account_id=account.id,
        name="document-dataset",
        icon="https://example.com/dataset.png",
        description="integration",
    )
    upload = UploadFile(
        id=uuid4(),
        account_id=account.id,
        name="document.txt",
        key="integration/document.txt",
        size=100,
        extension="txt",
        mime_type="text/plain",
        hash="hash",
    )
    db_session.add_all([dataset, upload])
    db_session.flush()
    return dataset, upload


def test_document_routes_persist_and_query(
    client, db_session, dataset_and_upload, handler_for, monkeypatch
):
    from internal.entity.dataset_entity import DocumentStatus
    from internal.model import Document
    import internal.service.document_service as document_service_module

    dataset, upload = dataset_and_upload
    document_handler = handler_for("create_documents")
    document_service = document_handler.document_service
    document_service.redis_client = MagicMock()
    document_service.redis_client.get.return_value = None
    monkeypatch.setattr(document_service_module.build_documents, "delay", MagicMock())
    monkeypatch.setattr(document_service_module.update_document_enabled, "delay", MagicMock())
    monkeypatch.setattr(document_service_module.delete_document, "delay", MagicMock())

    created = assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents",
            json={
                "upload_file_ids": [str(upload.id)],
                "process_type": "automatic",
                "rule": {},
            },
        )
    )
    document_id = created["data"]["documents"][0]["id"]
    document = db_session.get(Document, document_id)
    assert document is not None and document.upload_file_id == upload.id

    assert_success(client.get(f"/datasets/{dataset.id}/documents/{document.id}"))
    listing = assert_success(
        client.get(
            f"/datasets/{dataset.id}/documents",
            query_string={"search_word": "document"},
        )
    )
    assert any(item["id"] == str(document.id) for item in listing["data"]["list"])

    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/name",
            json={"name": "renamed.txt"},
        )
    )
    db_session.expire_all()
    document = db_session.get(Document, document.id)
    assert document.name == "renamed.txt"

    document.status = DocumentStatus.COMPLETED
    document.enabled = True
    db_session.flush()
    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/enabled",
            json={"enabled": False},
        )
    )
    db_session.expire_all()
    document = db_session.get(Document, document.id)
    assert document.enabled is False

    status = assert_success(
        client.get(f"/datasets/{dataset.id}/documents/batch/{document.batch}")
    )
    assert status["data"][0]["id"] == str(document.id)

    assert_success(
        client.post(f"/datasets/{dataset.id}/documents/{document.id}/delete")
    )
    db_session.expire_all()
    assert db_session.get(Document, document.id) is None


def test_segment_routes_persist_and_query(
    client, db_session, dataset_and_upload, handler_for
):
    from internal.entity.dataset_entity import DocumentStatus, SegmentStatus
    from internal.model import Document, ProcessRule, Segment

    dataset, upload = dataset_and_upload
    rule = ProcessRule(
        id=uuid4(), account_id=dataset.account_id, dataset_id=dataset.id, mode="automatic", rule={}
    )
    document = Document(
        id=uuid4(),
        account_id=dataset.account_id,
        dataset_id=dataset.id,
        upload_file_id=upload.id,
        process_rule_id=rule.id,
        batch="segment-batch",
        name="segment.txt",
        position=1,
        enabled=True,
        status=DocumentStatus.COMPLETED,
    )
    db_session.add_all([rule, document])
    db_session.flush()

    segment_service = handler_for("create_segment").segment_service
    segment_service.embeddings_service = MagicMock()
    segment_service.embeddings_service.calculate_token_count.side_effect = lambda value: len(value)
    segment_service.embeddings_service.embeddings.embed_query.return_value = [0.1]
    segment_service.jieba_service = MagicMock()
    segment_service.jieba_service.extract_keywords.return_value = ["keyword"]
    segment_service.vector_database_service = MagicMock()
    segment_service.keyword_table_service = MagicMock()
    segment_service.redis_client = MagicMock()
    segment_service.redis_client.get.return_value = None

    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/segments",
            json={"content": "first segment", "keywords": ["first"]},
        )
    )
    segment = (
        db_session.query(Segment)
        .filter_by(document_id=document.id, content="first segment")
        .one()
    )
    assert segment.status == SegmentStatus.COMPLETED

    assert_success(
        client.get(
            f"/datasets/{dataset.id}/documents/{document.id}/segments/{segment.id}"
        )
    )
    listing = assert_success(
        client.get(
            f"/datasets/{dataset.id}/documents/{document.id}/segments",
            query_string={"search_word": "first"},
        )
    )
    assert any(item["id"] == str(segment.id) for item in listing["data"]["list"])

    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/segments/{segment.id}",
            json={"content": "updated segment", "keywords": ["updated"]},
        )
    )
    db_session.expire_all()
    segment = db_session.get(Segment, segment.id)
    assert segment.content == "updated segment"

    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/segments/{segment.id}/enabled",
            json={"enabled": False},
        )
    )
    db_session.expire_all()
    segment = db_session.get(Segment, segment.id)
    assert segment.enabled is False

    assert_success(
        client.post(
            f"/datasets/{dataset.id}/documents/{document.id}/segments/{segment.id}/delete"
        )
    )
    db_session.expire_all()
    assert db_session.get(Segment, segment.id) is None
