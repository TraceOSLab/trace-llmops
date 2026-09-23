from injector import inject
from langchain_community.vectorstores import FAISS
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
from internal.core.agent.entities.agent_entity import DATASET_RETRIEVAL_TOOL_NAME

from internal.lib.helper import combine_documents
from internal.service import EmbeddingsService
import os
from threading import Lock


class FaissService:
    """Faiss向量服务"""

    faiss: FAISS
    embeddings_service: EmbeddingsService

    @inject
    def __init__(self, embeddings_service: EmbeddingsService):
        """初始化Faiss"""
        self.embeddings_service = embeddings_service
        self._faiss = None
        self._lock = Lock()

    @property
    def faiss(self) -> FAISS:
        """第一次检索时加载；失败不缓存，且并发只加载一次。"""
        with self._lock:
            if self._faiss is None:
                self._faiss = self._load_faiss()
            return self._faiss

    def _load_faiss(self) -> FAISS:

        # 加载本地向量数据库
        internal_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        faiss_vector_store_path = os.path.join(internal_path, "core", "vector_store")

        # 初始化faiss向量数据库
        return FAISS.load_local(
            folder_path=faiss_vector_store_path,
            embeddings=self.embeddings_service.embeddings,
            allow_dangerous_deserialization=True,
        )

    def convert_faiss_to_tool(self) -> BaseTool:
        """Faiss 检索器转换为 工具函数"""
        retrieval = self.faiss.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 5, "fetch_k": 20},
        )

        # 2.构建检索链，并将检索的结果合并成字符串
        search_chain = retrieval | combine_documents

        class DatasetRetrievalInput(BaseModel):
            """知识库检索工具输入结构"""

            query: str = Field(description="知识库检索query语句，类型为字符串")

        @tool(DATASET_RETRIEVAL_TOOL_NAME, args_schema=DatasetRetrievalInput)
        def dataset_retrieval(query: str) -> str:
            """如果需要检索扩展的知识库内容，当你觉得用户的提问超过你的知识范围时，可以尝试调用该工具，输入为搜索query语句，返 回数据为检索内容字符串"""
            return search_chain.invoke(query)

        return dataset_retrieval
