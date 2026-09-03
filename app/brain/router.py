class BrainRouter:
    """Keyword-based intent classifier. Deliberately simple/deterministic
    (no LLM) — see docs/SPRINTS/sprint-032.md §1.2 for why the previous
    ordering (material names like "calacatta"/"quartz" routing to "sales"
    before explicit lookup phrasing like "find"/"do we have" was even
    checked) was part of the AI-retrieval root cause. Explicit
    lookup/browse phrasing is checked before generic material-name/pricing
    keywords, so "Find Calacatta Gold 20mm" reaches the search path rather
    than always defaulting to a pricing reply.
    """

    # Ordered by priority — first match wins. A plain list (not a dict)
    # because insertion order is the actual contract here.
    _ROUTES: list[tuple[str, str]] = [
        # Explicit lookup/browse phrasing — checked first.
        ("do we have", "search"),
        ("we have", "search"),
        ("have any", "search"),
        ("got any", "search"),
        ("show", "search"),
        ("find", "search"),
        ("search", "search"),
        ("compare", "search"),
        ("cheapest", "search"),

        # Pricing/quoting phrasing.
        ("price", "sales"),
        ("cost", "sales"),
        ("quote", "sales"),
        ("quotation", "sales"),
        ("how much", "sales"),

        # Generic material name/category/thickness mentions with no other
        # signal default to a pricing reply (today's existing behaviour).
        ("calacatta", "sales"),
        ("oro", "sales"),
        ("gold", "sales"),
        ("borghini", "sales"),
        ("marquina", "sales"),
        ("quartz", "sales"),
        ("granite", "sales"),
        ("marble", "sales"),
        ("all", "search"),
        ("available", "search"),
        ("20mm", "search"),
        ("30mm", "search"),

        # Customer Service
        ("customer", "customer_service"),

        # Finance
        ("invoice", "finance"),
        ("payment", "finance"),

        # Marketing
        ("instagram", "marketing"),
        ("facebook", "marketing"),
        ("tiktok", "marketing"),

        # SEO
        ("seo", "seo"),
        ("website", "seo"),

        # Construction
        ("kitchen", "construction"),
        ("worktop", "construction"),

        # Projects
        ("templating", "projects"),
        ("installation", "projects"),

        # Scheduling
        ("calendar", "scheduling"),
        ("meeting", "scheduling"),
    ]

    def think(self, text: str) -> str:
        text = text.lower()

        for keyword, agent in self._ROUTES:
            if keyword in text:
                return agent

        return "executive"
