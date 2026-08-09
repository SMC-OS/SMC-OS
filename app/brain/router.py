class BrainRouter:

    def think(self, text: str):

        text = text.lower()

        routes = {

            # Sales
            "price": "sales",
            "cost": "sales",
            "quote": "sales",
            "quotation": "sales",
            "how much": "sales",
            "calacatta": "sales",
            "oro": "sales",
            "gold": "sales",
            "borghini": "sales",
            "marquina": "sales",
            "quartz": "sales",
            "granite": "sales",
            "marble": "sales",
            "show": "search",
            "find": "search",
            "search": "search",
            "compare": "search",
            "all": "search",
            "available": "search",
            "cheapest": "search",
            "20mm": "search",
            "30mm": "search",
            
            # Customer Service
            "customer": "customer_service",

            # Finance
            "invoice": "finance",
            "payment": "finance",

            # Marketing
            "instagram": "marketing",
            "facebook": "marketing",
            "tiktok": "marketing",

            # SEO
            "seo": "seo",
            "website": "seo",

            # Construction
            "kitchen": "construction",
            "worktop": "construction",

            # Projects
            "templating": "projects",
            "installation": "projects",

            # Scheduling
            "calendar": "scheduling",
            "meeting": "scheduling"
        }

        for keyword, agent in routes.items():
            if keyword in text:
                return agent

        return "executive"