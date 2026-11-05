from __future__ import annotations

"""MCP 工具的离线校验：不需要客户端、不需要 Key、不会调用模型。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/check_mcp.py

它做三件事：
1. import mcp_server，确认所有工具注册成功；
2. 打印工具清单与行为标注（只读 / 幂等 / 是否访问外部模型）；
3. 校验资源与提示模板存在。
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def main() -> int:
    try:
        import mcp_server
    except Exception as exc:  # pragma: no cover
        print(f"✗ 导入 mcp_server 失败：{exc}")
        return 1

    mcp = mcp_server.mcp
    tools = asyncio.run(mcp.list_tools())
    print(f"✓ 工具 {len(tools)} 个：")
    for tool in sorted(tools, key=lambda item: item.name):
        annotations = getattr(tool, "annotations", None)
        flags = []
        if annotations is not None:
            if annotations.readOnlyHint:
                flags.append("只读")
            if annotations.idempotentHint:
                flags.append("幂等")
            if annotations.openWorldHint:
                flags.append("访问外部模型")
        print(f"  - {tool.name:<24} {' '.join(flags)}")

    assessment_tools = {
        "create_assessment", "register_resume", "select_project", "add_project_document",
        "upload_code", "prepare_assessment", "set_capability_target", "get_practice_questions",
        "answer_practice", "start_exam", "get_exam", "submit_exam", "start_interview",
        "answer_interview", "get_interview", "generate_report", "get_report",
        "start_review", "submit_review", "get_assessment_status",
    }
    names = {tool.name for tool in tools}
    missing = sorted(assessment_tools - names)
    if missing:
        print(f"✗ 缺少测评工具：{missing}")
        return 1

    resources = asyncio.run(mcp.list_resources())
    templates = asyncio.run(mcp.list_resource_templates())
    prompts = asyncio.run(mcp.list_prompts())
    print(f"✓ 资源 {len(resources) + len(templates)} 个，提示模板 {len(prompts)} 个")

    ok = {"search_knowledge", "list_documents", "get_document_chunks"} <= names
    if not ok:
        print("✗ 缺少知识库检索工具")
        return 1

    print("\nMCP 注册检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
