"""在 llmops-api 目录运行；真实图/HTTP/工具运行时，替换数据库绑定、检索和模型。"""

import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlsplit

from flask import Flask
from requests.sessions import Session

from fixture_server import Handler, ThreadingHTTPServer
from internal.core.language_model import LanguageModelManager
from internal.core.tools.api_tools.entities import OpenAPISchema, ToolEntity
from internal.core.tools.api_tools.providers.api_provider_manager import ApiProviderManager
from internal.core.tools.builtin_tools.providers.time.current_time import current_time
from internal.core.workflow.entities.workflow_entity import WorkflowConfig
from internal.core.workflow.nodes import BaseNode, DatasetRetrievalNode, ToolNode
from internal.core.workflow.workflow import Workflow


ROOT = Path(__file__).resolve().parent


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    schema = OpenAPISchema(**json.loads((ROOT / "api-tool.schema.json").read_text()))
    operation = schema.paths["/policy"]["get"]
    tool = ApiProviderManager().get_tool(ToolEntity(
        id=str(uuid4()), name=operation["operationId"], description=operation["description"],
        url=base_url + "/policy", method="get", parameters=operation["parameters"],
    ))
    retrieval = {"text": "测试知识库补充：提交申请后由人工核验商品状态。"}
    model = {"invalid": False}

    def init_tool(self, *args, **kwargs):
        BaseNode.__init__(self, *args, **kwargs)
        self._tool = current_time() if self.node_data.tool_type == "builtin_tool" else tool

    def init_retrieval(self, *args, flask_app, account_id, **kwargs):
        BaseNode.__init__(self, *args, **kwargs)
        self._retrieval_tool = SimpleNamespace(invoke=lambda inputs: retrieval["text"])

    def stream(prompt):
        assert len(prompt) < 3500
        if model["invalid"]:
            return iter([SimpleNamespace(content="not JSON")])
        order_id = prompt.split("订单：", 1)[1].split("；", 1)[0]
        decision = prompt.split("确定性结论：", 1)[1].split("\n", 1)[0]
        result = json.dumps({"order_id": order_id, "decision": decision, "reply": "这是测试答复，请按测试规则处理。"}, ensure_ascii=False)
        return iter([SimpleNamespace(content=result[:20]), SimpleNamespace(content=result[20:])])

    request = Session.request

    def local_only(self, method, url, *args, **kwargs):
        parsed = urlsplit(url)
        assert parsed.hostname == "127.0.0.1" and parsed.port == server.server_port, "禁止访问外部服务"
        return request(self, method, url, *args, **kwargs)

    count = 0
    try:
        with (
            patch.object(ToolNode, "__init__", init_tool),
            patch.object(DatasetRetrievalNode, "__init__", init_retrieval),
            patch("internal.core.workflow.nodes.llm.llm_node.get_language_model_manager",
                  return_value=SimpleNamespace(create_language_model=lambda config: SimpleNamespace(stream=stream))),
            patch.object(Session, "request", local_only),
            Flask("workflow-example-verification").app_context(),
        ):
            for mode in ["baseline", "full"]:
                graph = json.loads((ROOT / f"{mode}.graph.json").read_text())
                for node in graph["nodes"]:
                    if node["node_type"] == "http_request":
                        node["url"] = base_url + "/order"
                    if node["node_type"] == "llm":
                        LanguageModelManager().validate_model_config(node["language_model_config"])
                config = WorkflowConfig(account_id=uuid4(), name="after_sales_test", description="离线验证", **graph)
                workflow = Workflow(workflow_config=config)
                for case in json.loads((ROOT / "cases.json").read_text()):
                    seen = []
                    try:
                        for chunk in workflow.stream(case["inputs"]):
                            seen.extend(next(iter(chunk.values()))["node_results"])
                    except Exception:
                        if "expected_failure" not in case:
                            raise
                        # 失败节点没有成功结果，且不得出现结束节点。
                        assert not any(r.node_data.node_type == "end" for r in seen)
                        assert not any(r.node_data.title == case["expected_failure"] for r in seen)
                        titles = {r.node_data.title for r in seen}
                        if case["name"] == "失效API响应":
                            assert {"校验并规范输入", "API工具：查询售后规则"} <= titles
                            response = next(r.outputs["text"] for r in seen if r.node_data.title == "API工具：查询售后规则")
                            assert json.loads(response)["error"] == "policy_not_found"
                        elif case["name"] == "空白问题":
                            assert titles == {"开始：售后测试输入"}
                        else:
                            assert not seen
                    else:
                        assert "expected_failure" not in case, case["name"]
                        assert len(seen) == len(graph["nodes"])
                        assert len({r.node_data.id for r in seen}) == len(seen)
                        outputs = seen[-1].outputs
                        assert seen[-1].node_data.node_type == "end"
                        for key, value in case["expected"].items():
                            assert outputs[key] == value, (case["name"], key, outputs)
                        if mode == "full":
                            assert outputs["llm_valid"] is True
                        assert outputs["run_time"]
                        assert len(outputs["report"]) < 800
                        http_result = next(r for r in seen if r.node_data.node_type == "http_request")
                        assert len(http_result.outputs["text"].encode()) < 512
                    count += 1

                if mode == "full":
                    inputs = {"query": "可以退货吗？", "order_id": "TEST-1001"}
                    for text in ["", "测试资料" * 1000]:
                        retrieval["text"] = text
                        outputs = workflow.invoke(inputs)
                        assert outputs["has_context"] == bool(text)
                        assert outputs["context_chars"] == len(text)
                        assert outputs["context_truncated"] == (len(text) > 1200)
                        assert outputs["llm_valid"] is True
                        count += 1
                    model["invalid"] = True
                    outputs = workflow.invoke(inputs)
                    assert outputs["llm_valid"] is False and outputs["validation_error"]
                    count += 1
        print(f"PASS: {count} 个场景；真实图执行、本地 HTTP 和工具；检索/模型使用替身；未连接数据库或公网。")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
