from mcp.server.fastmcp import FastMCP

# Cria o servidor MCP
mcp = FastMCP("DarwinLoop")

@mcp.tool()
def get_feedback_summary(project_id: str) -> str:
    """Retorna um resumo de feedbacks de um projeto."""
    return f"Resumo de feedback para {project_id}: O modelo performa bem em tarefas simples, mas alucina em tarefas complexas."

@mcp.tool()
def propose_prompt_update(project_id: str, suggestion: str) -> str:
    """Propõe uma atualização de system prompt."""
    return f"Sugestão de prompt para {project_id} registrada: {suggestion}"

if __name__ == "__main__":
    mcp.run()
