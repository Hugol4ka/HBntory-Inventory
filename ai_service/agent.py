import json
import logging

import httpx

import config

TOOL_SYSTEM_PROMPT = "You are the product assistant of HBntory-Inventory. Always use the available tools to answer questions about products, stock and branches. Answer in the same language as the question. Stock tools identify products by SKU (like HB-LAP-1001), never by numeric ID: when the user refers to a product by numeric ID, call get_product first to obtain its SKU, then you MUST call the relevant stock tool with that SKU — get_product alone never answers a stock question. If the question asks whether it is possible to buy one or more quantities of products, you must call check_shopping_list and no other tool."

ANSWER_SYSTEM_PROMPT = """You are the product assistant of HBntory-Inventory. Below you receive the user's question along with results already obtained from data retrieval tools. Formulate a clear and complete answer based on these results, without requesting additional data.

SUPPORTED QUESTION TYPES - you may only answer these 4 cases:
1. Details of a product (price, description, category...).
2. Where a product is available.
3. Which products are available in a given branch.
4. Whether a list of desired products and quantities can be satisfied by one or more branches.

If the question does not match ANY of these 4 cases, politely say that this type of request is not supported by this assistant, without attempting to answer it.

Requests for the complete inventory across all branches are also out of scope: stock questions must target either one specific product or one specific branch. In that case, explain that you can report stock for a given product or for a given branch, and invite the user to specify one.

GROUNDING RULES (mandatory):
- Never invent a product name, a price, a stock quantity or a branch.
- Use only the data provided above.
- If the provided data does not contain the requested information, state clearly that the information is not available rather than guessing.
- Products are identified by SKU in stock data (like HB-LAP-1001). When presenting results, use the product name if available rather than the raw SKU.
- If a tool reports an unknown SKU, say explicitly that this product reference does not exist in the inventory, and suggest checking the SKU. Do not describe it as out of stock.
- Never present the product catalog as stock information: the catalog lists what exists, stock data says how many units are held in which branch.
"""


class ProductQueryAgent:

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client

    async def answer(self, question):
        # --- Stage 1: data retrieval through tools ---
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
                        "think": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

                logging.info(
                    "[tool round %s] prompt_eval=%s eval=%s duration_ms=%s",
                    round_number,
                    data.get("prompt_eval_count"),
                    data.get("eval_count"),
                    data.get("total_duration", 0) // 1_000_000,
                )

                message = data["message"]

                # No tool requested: the retrieval phase is over.
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

            # --- Stage 2: final answer formulation, no tool-calling ---
            if tool_call_trace:
                collected_data = json.dumps(tool_call_trace, indent=2, ensure_ascii=False)
            else:
                collected_data = "No data was retrieved."

            answer_messages = [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User question: {question}\n\n"
                        f"Retrieved data:\n{collected_data}"
                    ),
                },
            ]

            answer_response = await client.post(
                "/api/chat",
                json={
                    "model": config.OLLAMA_MODEL,
                    "messages": answer_messages,
                    "stream": False,
                    "think": False,
                },
            )
            answer_response.raise_for_status()
            answer_data = answer_response.json()

            logging.info(
                "[answer] prompt_eval=%s eval=%s duration_ms=%s",
                answer_data.get("prompt_eval_count"),
                answer_data.get("eval_count"),
                answer_data.get("total_duration", 0) // 1_000_000,
            )

        final_message = answer_data["message"]
        return {
            "answer": final_message["content"].strip(),
            "tool_calls": tool_call_trace,
        }