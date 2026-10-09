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
        system_prompt="Write 4 DM variants (pain-point, social-proof, question, offer-first), labelled A-D, using the plan and lessons.",
        reads=["plan.md", "leads.md", "lessons.md"], writes="variants.md",
        mock="A: pain-point...\nB: social-proof...\nC: question...\nD: offer-first..."),
}
