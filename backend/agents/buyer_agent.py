import os
import re
import json
import uuid
from typing import Optional
from datetime import datetime, timezone
from agents.communication import comm_service


class BuyerAgent:
    def parse_request(self, query: str, location: str) -> dict:
        # Try Gemini API
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"""Extract purchase requirements from this query. Return ONLY valid JSON.
Query: "{query}"
Location hint: "{location}"
Return JSON with keys: product (string), quantity (number), unit (string), budget_sats (integer or null), location (string), preferences (list of strings)
Example: {{"product":"rice","quantity":10,"unit":"kg","budget_sats":250000,"location":"Dakar, Senegal","preferences":[]}}"""
                response = model.generate_content(prompt)
                text = response.text.strip()
                # Strip markdown code fences if present
                text = re.sub(r'^```json\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
                result = json.loads(text)
                result["raw_query"] = query
                result["parsed_by"] = "gemini"
                return result
            except Exception:
                pass

        # Deterministic fallback
        result = {
            "product": "rice",
            "quantity": "1 unit",
            "quantity_value": 1,
            "unit": "unit",
            "budget_sats": None,
            "location": location,
            "preferences": [],
            "raw_query": query,
            "parsed_by": "fallback"
        }

        # Extract product (common products list)
        products = ["rice", "tomato", "millet", "sugar", "flour", "oil", "beans", "corn", "yam"]
        q_lower = query.lower()
        for p in products:
            if p in q_lower:
                result["product"] = p
                break
        else:
            # First noun-like word after "need" or "want" or "buy"
            m = re.search(r'(?:need|want|buy|looking for)\s+(?:\d+\s*\w+\s+of\s+)?(\w+)', q_lower)
            if m:
                result["product"] = m.group(1)

        # Extract quantity
        m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|lbs|lb|ton|piece|unit|bag|sack|pack)?', q_lower)
        if m:
            qty = m.group(1)
            unit = m.group(2) or "unit"
            result["quantity"] = f"{qty} {unit}"
            result["quantity_value"] = float(qty) if "." in qty else int(qty)
            result["unit"] = unit

        # Extract budget in sats
        m = re.search(r'(\d+(?:,\d+)?)\s*(?:sats?|satoshi)', q_lower)
        if m:
            result["budget_sats"] = int(m.group(1).replace(",", ""))
        else:
            # Try to find numeric budget
            m = re.search(r'(?:under|less than|below|budget|max)\s*(\d+(?:,\d+)?)', q_lower)
            if m:
                result["budget_sats"] = int(m.group(1).replace(",", ""))

        if isinstance(result.get("quantity"), (int, float)):
            result["quantity_value"] = result["quantity"]
            result["quantity"] = f"{result['quantity']} {result.get('unit', 'unit')}"
        elif isinstance(result.get("quantity"), str):
            q_match = re.search(r"(\d+(?:\.\d+)?)\s*([a-z]+)?", result["quantity"].lower())
            if q_match:
                result["quantity_value"] = float(q_match.group(1)) if "." in q_match.group(1) else int(q_match.group(1))
                result["unit"] = q_match.group(2) or result.get("unit", "unit")
        result.setdefault("quantity_value", 1)
        result.setdefault("unit", "unit")
        return result

    def run(self, query: str, location: str, db, conversation_id: str):
        result = self.parse_request(query, location)
        msg = comm_service.create_message(
            sender="buyer_agent",
            recipient="discovery_agent",
            message_type="purchase_request",
            payload=result,
            conversation_id=conversation_id
        )
        comm_service.save_message(db, msg)
        return result, [msg]


buyer_agent = BuyerAgent()
