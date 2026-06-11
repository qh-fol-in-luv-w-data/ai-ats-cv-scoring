app_name = "ai_ats"
app_title = "AI ATS"
app_publisher = "CT Group"
app_description = "AI Candidate Persona Report System – NoAI-NoHire"
app_email = "dev@ctgroup.vn"
app_license = "mit"

# Expose API
override_whitelisted_methods = {}


# SPA Routing
website_route_rules = [
    {"from_route": "/aicenter/2as-ats/<path:app_path>", "to_route": "ai_ats_spa"},
    {"from_route": "/aicenter/2as-ats", "to_route": "ai_ats_spa"}
]
