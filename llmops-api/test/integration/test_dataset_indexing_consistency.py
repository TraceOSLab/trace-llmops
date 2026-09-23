from unittest.mock import MagicMock
from uuid import uuid4

import pytest


pytestmark = pytest.mark.integration


def test_duplicate_build_task_claims_a_document_only_once(
    app, db_session, account
):
    """同一 Celery 消息被投递两次时，只有第一个任务进入索引调用链。"""
    from internal.entity.dataset_entity import DocumentStatus
    from internal.extension.database_extension import db
    from internal.model import Dataset, Document, ProcessRule, UploadFile
    from internal.service.indexing_service import IndexingService

    dataset = Dataset(id=uuid4(), account_id=account.id, name="claim-dataset", icon="", description="")
    upload = UploadFile(
        id=uuid4(), account_id=account.id, name="claim.txt", key="claim.txt", size=1,
        extension="txt", mime_type="text/plain", hash="claim",
    )
    rule = ProcessRule(id=uuid4(), account_id=account.id, dataset_id=dataset.id, mode="automatic", rule={})
    document = Document(
        id=uuid4(), account_id=account.id, dataset_id=dataset.id, upload_file_id=upload.id,
        process_rule_id=rule.id, batch="claim", name="claim.txt", position=1,
        status=DocumentStatus.WAITING,
    )
    db_session.add_all([dataset, upload, rule, document])
    db_session.flush()

    # 本用例只验证任务认领，索引外部依赖均不进入。
    service = IndexingService(
        db=db, redis_client=MagicMock(),
        file_extractor=MagicMock(), process_rule_service=MagicMock(),
        embeddings_service=MagicMock(), jieba_service=MagicMock(),
        keyword_table_service=MagicMock(), vector_database_service=MagicMock(),
    )
    calls = []
    service._parsing = lambda _: calls.append("parse") or []
    service._splitting = lambda _, __: calls.append("split") or []
    service._indexing = lambda _, __: calls.append("index")
    service._completed = lambda _, __: calls.append("complete")

    service.build_documents([document.id])
    service.build_documents([document.id])
    assert calls == ["parse", "split", "index", "complete"]
    db_session.expire_all()
    assert db_session.get(Document, document.id).status == DocumentStatus.PARSING


def test_dataset_delete_failure_keeps_primary_record_for_retry(
    client, db_session, account, handler_for, monkeypatch
):
    """向量库清理失败时，不能先删主知识库使残留数据失去管理入口。"""
    from internal.model import Dataset

    dataset = Dataset(id=uuid4(), account_id=account.id, name="retry-delete", icon="", description="")
    db_session.add(dataset)
    db_session.flush()
    handler = handler_for("delete_dataset")
    monkeypatch.setattr(
        handler.dataset_service.indexing_service, "delete_dataset",
        MagicMock(side_effect=RuntimeError("vector database unavailable")),
    )

    response = client.post(f"/datasets/{dataset.id}/delete")
    assert response.status_code == 200
    assert response.get_json()["code"] == "fail"
    db_session.expire_all()
    assert db_session.get(Dataset, dataset.id) is not None


def test_late_keyword_task_does_not_create_orphan_table(app, db_session):
    """被删除知识库的滞后索引任务不能创建孤立 KeywordTable。"""
    from internal.model import KeywordTable
    from internal.extension.database_extension import db
    from internal.service.keyword_table_service import KeywordTableService

    dataset_id = uuid4()
    redis = MagicMock()
    redis.lock.return_value.__enter__.return_value = None
    service = KeywordTableService(db=db, redis_client=redis)

    service.add_keyword_table_from_ids(dataset_id, [uuid4()])
    service.delete_keyword_table_from_ids(dataset_id, [uuid4()])

    assert db_session.query(KeywordTable).filter_by(dataset_id=dataset_id).one_or_none() is None
