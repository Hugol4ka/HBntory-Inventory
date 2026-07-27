import json
import httpx

import config

TOOL_SYSTEM_PROMPT = "You are the product assistant of HBntory-Inventory. Always use the available tools to answer questions about products, stock and branches. If the question asks whether it is possible to buy one or more quantities of products, you must call check_shopping_list and no other tool."

ANSWER_SYSTEM_PROMPT = """You are the product assistant of HBntory-Inventory. Below you receive the user's question along with results already obtained from data retrieval tools. Formulate a clear and complete answer based on these results, without requesting additional data.

SUPPORTED QUESTION TYPES - you may only answer these 4 cases:
1. Details of a product (price, description, category...).
2. Where a product is available.
3. Which products are available in a given branch.
4. Whether a list of desired products and quantities can be satisfied by one or more branches.

If the question does not match ANY of these 4 cases, politely say that this type of request is not supported by this assistant, without attempting to answer it.

GROUNDING RULES (mandatory):
- Never invent a product name, a price, a stock quantity or a branch.
- Use only the data provided above.
- If the provided data does not contain the requested information, state clearly that the information is not available rather than guessing.
"""

class ProductQueryAgent:

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client

    async def answer(self, question):
        # --- Étape 1 : récupération des données via les tools ---
        messages = [
            {"role": "system", "content": TOOL_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        tool_call_trace = []

        async with httpx.AsyncClient(base_url=config.OLLAMA_HOST, timeout=config.OLLAMA_TIMEOUT_SECONDS) as client:
            for round_number in range(config.MAX_TOOL_CALL_ROUNDS):
                response = await client.post(
                    "/api/chat",
                    json={
                        "model": config.OLLAMA_MODEL,
                        "messages": messages,
                        "tools": self.mcp_client.tools,
                        "stream": False,
                    },
                )
                response.raise_for_status()

                data = response.json()
                message = data["message"]

                # Plus aucun tool demandé : la phase de récupération est terminée.
                if not message.get("tool_calls"):
                    break

                messages.append(message)

                for tool_call in message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)

                    tool_result = await self.mcp_client.call_tool(tool_name, tool_args)
                    tool_call_trace.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    })
                    messages.append({"role": "tool", "name": tool_name, "content": tool_result})

            # --- Étape 2 : formulation de la réponse finale, sans tool-calling ---
            if tool_call_trace:
                collected_data = json.dumps(tool_call_trace, indent=2, ensure_ascii=False)
            else:
                collected_data = "Aucune donnée n'a été récupérée."

            answer_messages = [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question de l'utilisateur : {question}\n\n"
                        f"Données récupérées :\n{collected_data}"
                    ),
                },
            ]

            answer_response = await client.post(
                "/api/chat",
                json={
                    "model": config.OLLAMA_MODEL,
                    "messages": answer_messages,
                    "stream": False,
                },
            )
            answer_response.raise_for_status()

        final_message = answer_response.json()["message"]
        return {
            "answer": final_message["content"].strip(),
            "tool_calls": tool_call_trace,
        }
