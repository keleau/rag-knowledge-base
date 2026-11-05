from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

import mcp_assessment
import tools

mcp = FastMCP("zhiwen")


@mcp.tool()
def search_knowledge(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """Search the local knowledge base and return the most relevant chunks."""
    return tools.search_knowledge(query, top_k)


@mcp.tool()
def list_documents() -> list[dict[str, Any]]:
    """List documents currently indexed in the knowledge base."""
    return tools.list_documents()


@mcp.tool()
def get_document_chunks(document_id: str) -> dict[str, Any]:
    """Read all chunks of a document by its id."""
    try:
        return tools.get_document_chunks(document_id)
    except ValueError as exc:
        return {"error": str(exc), "document_id": document_id}


# 项目定向测评工具（简历 → 出题 → 考试 → 面试 → 报告 → 复练）
mcp_assessment.register(mcp)
mcp_assessment.register_resources(mcp)


if __name__ == "__main__":
    mcp.run()
