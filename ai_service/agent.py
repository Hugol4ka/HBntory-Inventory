import json
import httpx

import config

SYSTEM_PROMPT = """Tu es l'assistant produit d'HBntory-Inventory.

TYPES DE QUESTIONS SUPPORTÉES - tu peux répondre uniquement à ces 4 cas :
1. Détails d'un produit (prix, description, catégorie...) → utilise get_product ou list_products.
2. Où un produit est disponible → utilise get_stock_by_product.
3. Quels produits sont disponibles dans une succursale donnée → utilise get_stock_by_branch,
   puis croise les product_id obtenus avec list_products pour donner leurs noms
   (get_stock_by_branch ne renvoie que des IDs, jamais de noms).
4. Si une liste de produits/quantités souhaités peut être satisfaite par une ou plusieurs
   succursales → utilise check_shopping_list. Ce tool calcule déjà la faisabilité pour toi :
   ne recalcule jamais toi-même une comparaison de quantités, lis directement le champ
   "feasible_branches" et les "issues" dans "details" pour expliquer ta réponse.

Si la question ne correspond à AUCUN de ces 4 cas, dis poliment que ce type de demande
n'est pas supporté par cet assistant, sans essayer d'y répondre.

TOOLS DISPONIBLES :
- list_products() : liste tout le catalogue produits.
- get_product(product_id) : détails d'un produit précis.
- list_branches() : liste toutes les succursales (id + nom).
- get_stock_by_product(product_id) : stock d'un produit dans toutes les succursales.
- get_stock_by_branch(branch_id) : liste des product_id + quantités dans une succursale
  (PAS de noms de produits - à croiser avec list_products si besoin de les afficher).
- check_shopping_list(items) : détermine quelle(s) succursale(s) peuvent satisfaire une
  liste de {product_id, quantity}. Renvoie déjà le verdict calculé, ne recalcule rien toi-même.

RÉSOLUTION DES NOMS DE SUCCURSALES (règle obligatoire) :
- get_stock_by_branch attend un branch_id (nombre entier), jamais un nom.
- Si l'utilisateur mentionne une succursale par son nom (ex: "North Branch") plutôt que
  par son ID, appelle d'abord list_branches() pour retrouver l'id correspondant à ce nom,
  puis utilise cet id dans get_stock_by_branch.
- Si aucune succursale de list_branches() ne correspond au nom donné par l'utilisateur,
  dis-le clairement plutôt que de deviner ou d'utiliser un id au hasard.

RÈGLES DE GROUNDING (obligatoires) :
- Ne jamais inventer un nom de produit, un prix, une quantité en stock ou une succursale.
- Utilise uniquement les données renvoyées par les tools.
- Si un tool renvoie une erreur ou aucune donnée pertinente, dis clairement à l'utilisateur
  que l'information n'est pas disponible plutôt que de deviner.
- Si une information nécessaire manque pour répondre complètement, dis-le explicitement
  plutôt que de compléter par une supposition.
- N'expose jamais de détails techniques internes (ids de session, structure de la base,
  messages d'erreur bruts type stack trace) : reformule toujours en langage clair.
"""

class ProductQueryAgent:

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client

    async def answer(self, question):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

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

                if not message.get("tool_calls"):
                    return {"answer": message["content"].strip(), "tool_calls": []}

                if message.get("tool_calls"):
                    messages.append(message)

                    for tool_call in message["tool_calls"]:
                        tool_name = tool_call["function"]["name"]
                        tool_args = tool_call["function"]["arguments"]
                        if isinstance(tool_args, str):
                            tool_args = json.loads(tool_args)

                        tool_result = await self.mcp_client.call_tool(tool_name, tool_args)
                        messages.append({"role": "tool", "name": tool_name, "content": tool_result})

        return {
            "answer": "Je n'ai pas pu obtenir de réponse satisfaisante après plusieurs tentatives.",
            "tool_calls": [msg for msg in messages if msg["role"] == "tool"],
        }
