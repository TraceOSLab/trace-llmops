#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   vector_database_service
@Time   :   2025/12/19 
@Author :   s.qiu@foxmail.com
"""
import logging
import os
from threading import RLock

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

    def __init__(self, embeddings_service: EmbeddingsService):
        self.embeddings_service = embeddings_service
        self._client: WeaviateClient | None = None
        self._vector_store: WeaviateVectorStore | None = None
        self._lock = RLock()

    @property
    def client(self) -> WeaviateClient:
        with self._lock:
            if self._client is None:
                import weaviate

                self._client = weaviate.connect_to_local(
                    host=os.getenv("WEAVIATE_HOST"),
                    grpc_port=os.getenv("WEAVIATE_PORT"),
                )
            return self._client

    @property
    def vector_store(self) -> WeaviateVectorStore:
        with self._lock:
            if self._vector_store is None:
                self._vector_store = WeaviateVectorStore(
                    client=self.client,
                    index_name=COLLECTION_NAME,
                    text_key="text",
                    embedding=self.embeddings_service.embeddings,
                )
            return self._vector_store

    def close(self) -> None:
        """关闭当前服务实例持有的 Weaviate 连接。"""
        with self._lock:
            client = self._client
            self._vector_store = None
            self._client = None

            if client is None:
                return

            try:
                client.close()
            except Exception:
                logging.exception("关闭 Weaviate 连接失败")

    def get_retriever(self) -> VectorStoreRetriever:
        """获取检索器"""
        return self.vector_store.as_retriever()

    @classmethod
    def combine_documents(cls, documents: list[Document]) -> str:
        return "\n\n".join([document.page_content for document in documents])

    @property
    def collection(self) -> Collection:
        return self.client.collections.get(COLLECTION_NAME)
