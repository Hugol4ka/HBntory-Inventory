import json
import httpx

import config

TOOL_SYSTEM_PROMPT = TOOL_SYSTEM_PROMPT = "Tu es l'assistant produit d'HBntory-Inventory. Utilise toujours les tools disponibles. Si la question demande s'il est possible d'acheter une ou plusieurs quantités de produits, appelle obligatoirement check_shopping_list et aucun autre tool."
ANSWER_SYSTEM_PROMPT = """Tu es l'assistant produit d'HBntory-Inventory. Tu reçois ci-dessous la question de l'utilisateur ainsi que les résultats déjà obtenus via des outils de recherche de données. Formule une réponse claire et complète à partir de ces résultats, sans demander de données supplémentaires.

TYPES DE QUESTIONS SUPPORTÉES - tu peux répondre uniquement à ces 4 cas :
1. Détails d'un produit (prix, description, catégorie...).
2. Où un produit est disponible.
3. Quels produits sont disponibles dans une succursale donnée.
4. Si une liste de produits/quantités souhaités peut être satisfaite par une ou plusieurs succursales.

Si la question ne correspond à AUCUN de ces 4 cas, dis poliment que ce type de demande n'est pas supporté par cet assistant, sans essayer d'y répondre.

RÈGLES DE GROUNDING (obligatoires) :
- Ne jamais inventer un nom de produit, un prix, une quantité en stock ou une succursale.
- Utilise uniquement les données fournies ci-dessus.
- Si les données fournies ne contiennent pas l'information demandée, dis clairement que l'information n'est pas disponible plutôt que de deviner.
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
