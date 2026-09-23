"""生成 API 请求文件和绑定当前账号 API 工具的工作流；不请求后端。"""

import argparse
import json
from pathlib import Path
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-id", type=UUID, help="新建的测试 API 工具提供者 ID")
    parser.add_argument("--icon-url", help="你已有的有效图片 URL，用于创建工作流和 API 工具")
    parser.add_argument("--output", type=Path, default=Path("/tmp/after-sales-workflow"))
    args = parser.parse_args()
    if not args.provider_id and not args.icon_url:
        parser.error("至少提供 --icon-url 或 --provider-id")
    if args.provider_id and args.provider_id.int == 0:
        parser.error("不能使用占位的全零 provider ID")
    source = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)

    def write(name, data):
        path = args.output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)

    if args.icon_url:
        write("api-tool.create.json", {
            "name": "售后固定规则测试",
            "icon": args.icon_url,
            "headers": [],
            "openapi_schema": (source / "api-tool.schema.json").read_text(encoding="utf-8"),
        })
        for mode, label in [("baseline", "基础"), ("full", "完整")]:
            write(f"{mode}.create.json", {
                "name": f"售后工单综合测试-{label}版",
                "tool_call_name": f"after_sales_test_{mode}",
                "icon": args.icon_url,
                "description": "使用虚构订单验证工作流节点、并行汇合和结果校验，仅用于测试。",
            })

    if args.provider_id:
        for mode in ["baseline", "full"]:
            graph = json.loads((source / f"{mode}.graph.json").read_text(encoding="utf-8"))
            for node in graph["nodes"]:
                if node.get("tool_type") == "api_tool":
                    node["provider_id"] = str(args.provider_id)
            write(f"{mode}.graph.json", graph)


if __name__ == "__main__":
    main()
