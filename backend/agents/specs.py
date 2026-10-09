"""All agent definitions in one place. Persons C and D edit prompts here."""
from agent import AgentSpec

SPECS = {
    "validation": AgentSpec(
        name="Validation",
        system_prompt="You validate business ideas: competitors, pain points, market risks. Output markdown with a verdict.",
        reads=["idea.md"], writes="validation.md",
        mock="# Validation\n- Competitors: 3 found\n- Top pain point: slow turnaround\n- Verdict: GO"),
    "planner": AgentSpec(
        name="Planner",
        system_prompt="Turn the validation into a plan: audience, design philosophy, marketing philosophy, task list.",
        reads=["idea.md", "validation.md", "lessons.md"], writes="plan.md",
        mock="# Plan\n## Design: minimal, trust-first\n## Marketing: curiosity-led\n## Tasks: landing, leads, outreach"),
    "landing": AgentSpec(
        name="LandingPage",
        system_prompt="Output ONE self-contained HTML landing page following the plan. No commentary.",
        reads=["plan.md"], writes="landing.md",
        mock="<html><body><h1>Demo landing page</h1></body></html>"),
    "leads": AgentSpec(
        name="LeadGen",
        system_prompt="Given the plan, output a markdown table of target leads (name, handle, why they fit).",
        reads=["plan.md"], writes="leads.md",
        mock="| name | handle | fit |\n|---|---|---|\n| Acme Bakery | @acme | local, no site |"),
    "marketing": AgentSpec(
        name="Marketing",
        system_prompt=(
            "Create four concise outreach message variants from the plan, leads, "
            "and lessons. Return only valid JSON, with no markdown fences or "
            "commentary, using exactly this schema: "
            '{"A":{"angle":"pain-point","text":"..."}'
            ',"B":{"angle":"social-proof","text":"..."}'
            ',"C":{"angle":"question","text":"..."}'
            ',"D":{"angle":"offer-first","text":"..."}}. '
            "Each text must be under 60 words and contain the literal "
            "{name} and {why} placeholders for later personalization. "
            "Do not claim social proof or outcomes not supported by the supplied context."
        ),
        reads=["plan.md", "leads.md", "lessons.md"],
        writes="variants.json",
        mock=(
            '{"A":{"angle":"pain-point","text":"Hi {name}, I noticed {why}. '
            'Would it help to explore a practical way to address this?"},'
            '"B":{"angle":"social-proof","text":"Hi {name}, {why}. '
            'We are exploring a helpful approach and would value your perspective. '
            'Would you be open to hearing more?"},'
            '"C":{"angle":"question","text":"Hi {name}, {why}. '
            'What is your biggest challenge with this right now?"},'
            '"D":{"angle":"offer-first","text":"Hi {name}, based on {why}, '
            'I can share a brief overview of our idea. Would that be useful?"}}'
        ),
    ),
}

# every agent sees founder feedback (written by Control.revise)
for _s in SPECS.values():
    _s.reads.append("feedback.md")
