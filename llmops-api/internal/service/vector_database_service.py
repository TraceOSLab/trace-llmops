#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   vector_database_service
@Time   :   2025/12/19
@Author :   s.qiu@foxmail.com
"""

from threading import RLock

from flask import g
from flask_weaviate import FlaskWeaviate
from injector import inject
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_weaviate import WeaviateVectorStore
from weaviate import WeaviateClient
from weaviate.collections import Collection

from .embeddings_service import EmbeddingsService

COLLECTION_NAME = "Dataset"


@inject
class VectorDatabaseService:
    """向量数据库服务"""

    embeddings_service: EmbeddingsService

    def __init__(self, embeddings_service: EmbeddingsService, weaviate: FlaskWeaviate):
        self.embeddings_service = embeddings_service
        self.weaviate = weaviate
        self._lock = RLock()

    @property
    def client(self) -> WeaviateClient:
        return self.weaviate.client

    @property
    def vector_store(self) -> WeaviateVectorStore:
        # Service 可被多个索引线程共用；缓存必须和扩展客户端一样属于当前上下文。
        # 保留锁，避免同一索引任务的多个线程同时首次创建 Dataset 集合。
        with self._lock:
            vector_store = g.get("weaviate_vector_store")
            if vector_store is None:
                vector_store = WeaviateVectorStore(
                    client=self.client,
                    index_name=COLLECTION_NAME,
                    text_key="text",
                    embedding=self.embeddings_service.embeddings,
                )
                g.weaviate_vector_store = vector_store
            return vector_store

    def get_retriever(self) -> VectorStoreRetriever:
        """获取检索器"""
        return self.vector_store.as_retriever()

    @classmethod
    def combine_documents(cls, documents: list[Document]) -> str:
        return "\n\n".join([document.page_content for document in documents])

    @property
    def collection(self) -> Collection:
        return self.client.collections.get(COLLECTION_NAME)
