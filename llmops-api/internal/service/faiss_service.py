from injector import inject
from langchain_classic.vectorstores import FAISS
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
from internal.core.agent.entities.agent_entity import DATASET_RETRIEVAL_TOOL_NAME

from internal.lib.helper import combine_documents
from internal.service import EmbeddingsService
import os


@inject
class FaissService:
    """Faiss向量服务"""

    faiss: FAISS
    embeddings_service: EmbeddingsService

    def _init_(self, embeddings_service: EmbeddingsService):
        """初始化Faiss"""
        self.embeddings_service = embeddings_service

        # 加载本地向量数据库
        internal_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        faiss_vector_store_path = os.path.join(internal_path, "core", "vector_store")

        # 初始化faiss向量数据库
        self.faiss = FAISS.load_local(
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
