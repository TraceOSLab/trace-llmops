import os

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# 1. 路径
BASE_DIR = os.getcwd()

markdown_path = os.path.join(
    BASE_DIR,
    "storage",
    "vector_store",
    "01.项目API文档.md",
)

vector_store_path = os.path.join(
    BASE_DIR,
    "internal",
    "core",
    "vector_store",
)

embedding_cache_path = os.path.join(
    BASE_DIR,
    "internal",
    "core",
    "embeddings",
)


# 2. 加载 Markdown
loader = TextLoader(
    markdown_path,
    encoding="utf-8",
)

documents = loader.load()

print(f"原始文档数量: {len(documents)}")


# 3. 文档切片
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)

chunks = text_splitter.split_documents(documents)

print(f"切片数量: {len(chunks)}")


# 4. 加载 Embedding 模型
embeddings = HuggingFaceEmbeddings(
    model_name="Alibaba-NLP/gte-multilingual-base",
    cache_folder=embedding_cache_path,
    model_kwargs={
        "trust_remote_code": True,
        "device": "mps",
    },
)


# 5. 创建 FAISS
vector_store = FAISS.from_documents(
    documents=chunks,
    embedding=embeddings,
)


# 6. 保存
vector_store.save_local(vector_store_path)

print(f"FAISS 构建完成: {vector_store_path}")
print(f"向量数量: {vector_store.index.ntotal}")
print(f"向量维度: {vector_store.index.d}")
