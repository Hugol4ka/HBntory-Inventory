import os

# --- Ollama (LLM local) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:latest")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

# --- Product MCP Server ---
MCP_SERVER_URL = os.getenv("HBN_AI_MCP_URL", "http://localhost:5003/mcp")

# --- Agent ---
MAX_TOOL_CALL_ROUNDS = int(os.getenv("MAX_TOOL_CALL_ROUNDS", "5"))
AI_PORT = int(os.getenv("HBN_AI_PORT", "8000"))
EXPOSE_TOOL_CALLS = os.getenv("EXPOSE_TOOL_CALLS", "false").lower() == "true"
