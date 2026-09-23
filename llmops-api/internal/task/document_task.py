#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   document_task
@Time   :   2025/12/22 22:20
@Author :   s.qiu@foxmail.com
"""
from uuid import UUID

from celery import shared_task
from celery.exceptions import Retry


@shared_task
def build_documents(document_ids: list[str]) -> None:
    """根据传递额文档id列表 构建文档"""
    from app.http.module import injector
    from internal.service import IndexingService

    indexing_service = injector.get(IndexingService)
    try:
        indexing_service.build_documents([UUID(document_id) for document_id in document_ids])
    finally:
        indexing_service.vector_database_service.close()


@shared_task
def update_document_enabled(document_id: str) -> None:
    """根据传递的文档id修改文档的状态"""
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    indexing_service = injector.get(IndexingService)
    try:
        indexing_service.update_document_enabled(UUID(document_id))
    finally:
        indexing_service.vector_database_service.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=1)
def delete_document(self, dataset_id: str, document_id: str) -> None:
    """根据传递的文档id+知识库id清除文档记录"""
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    indexing_service = injector.get(IndexingService)
    try:
        # 发布消息与删除主记录之间没有 outbox。若 Worker 先拿到消息，
        # 短暂重试直到主记录已提交删除，避免提前删掉仍存在文档的片段。
        from internal.model import Document
        if indexing_service.get(Document, UUID(document_id)) is not None:
            raise self.retry()
        indexing_service.delete_document(UUID(dataset_id), UUID(document_id))
    except Retry:
        raise
    except Exception as exc:
        # 向量库暂不可用时，删除是幂等的，可以由 Celery 有限重试完成清理。
        raise self.retry(exc=exc) from exc
    finally:
        indexing_service.vector_database_service.close()
