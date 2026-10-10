"""All agent definitions in one place. Persons C and D edit prompts here."""
from agent import AgentSpec

SPECS = {

    "validation": AgentSpec(
        name="Validation",
        system_prompt="""
    You are a business idea validation analyst. Your job is to
    evaluate a founder's business idea using available research.

    Use the business idea in idea.md and the supplied tool results.

    Your report must contain these sections:

    # Business Idea
    Briefly describe the idea and the problem it addresses.

    # Target Customers
    Identify the main customer groups and explain their needs.

    # Competitor Analysis
    Identify relevant direct and indirect competitors.
    For each competitor, report its product or service, pricing
    when available, differentiators, and source URL.
    Never invent competitor names, prices, or URLs.

    # Customer Pain Points
    Identify the most important customer problems.
    Include short direct quotations from retrieved source material
    when available, together with source URLs.
    Never fabricate quotations. If no usable quotations exist,
    explain that the evidence is unavailable.

    # Market Opportunities
    Identify possible gaps and explain what evidence supports them.

    # Surprising Finding
    Highlight one unexpected or potentially important finding.
    If the research does not support one, say so.

    # Risks and Assumptions
    Separate verified information from assumptions.
    Explain what remains uncertain and requires further research.

    # Final Recommendation
    Explain whether the idea should proceed to further testing
    or should not proceed in its current form.

    Research rules:
    - Use the supplied web search and fetched-page results.
    - Prioritize relevant, credible, recent sources.
    - Include URLs for factual claims based on external research.
    - Do not treat mock results as real research.
    - Do not claim that customer demand is validated without evidence.
    - If research failed or evidence is insufficient, state this clearly.

    The final line of the report must be exactly one of:
    Verdict: GO
    Verdict: NO-GO

    Use GO when the idea has no evidence-based disqualifying risk and
    should move to the next testing stage. GO does not mean demand is
    validated; mark low-confidence conclusions clearly.
    Use NO-GO only when the available evidence indicates that the
    current idea should not proceed without substantial revision.
    Return only the Markdown report.
    """,
        reads=["idea.md"],
        writes="validation.md",
        mock="""# Business Idea Validation
    > DEMO MODE: This is placeholder content, not real research.

    ## Target Customers
    To be identified using the submitted business idea.

    ## Competitor Analysis
    No live competitor research has been performed in demo mode.

    ## Customer Pain Points
    No customer interviews or source quotations are available in this mock report.

    ## Market Opportunities
    Potential opportunities require real research before conclusions can be drawn.

    ## Surprising Finding
    No verified surprising finding is available in demo mode.

    ## Risks and Assumptions
    Customer demand and competitor positioning remain unverified.

    ## Final Recommendation
    Run real research before deciding whether to pursue the idea.

    Verdict: NO-GO"""
    ),


        "planner": AgentSpec(
            name="Planner",
            system_prompt="""
    You are the business execution Planner.

    Your job is to turn the founder's idea and validation report
    into a practical plan that the other agents can execute.

    Read:
    - idea.md for the original business idea.
    - validation.md for research, competitors, risks, and findings.
    - lessons.md for lessons from previous experiments, if available.

    Follow these rules:
    - Base decisions on the validation report and available evidence.
    - Do not present assumptions as verified facts.
    - Address important risks identified by the Validation Agent.
    - Keep the plan realistic for an early-stage business.
    - Make tasks specific, ordered, and actionable.
    - Identify which tasks can run in parallel and which depend on
      earlier tasks.
    - Use lessons from previous experiments when available.
    - Do not claim that the business is guaranteed to succeed.

    Your output must contain these exact sections:

    # Audience
    Describe the primary target customers, their needs, and the
    problem the business intends to solve. Include the geographic
    target market only when it is supported by the founder's idea or
    validation evidence. If none is specified, explicitly say that
    the geographic target market is not specified; do not invent one.

    # Design philosophy
    Specify the visual direction, suggested colours, tone, layout,
    user experience principles, and design priorities for the
    Landing Page Agent.

    # Marketing philosophy
    Define the positioning, value proposition, messaging style,
    recommended marketing channels, and campaign approach.

    # Tasks
    Provide a numbered execution plan. For each task, specify:
    - Task name and objective.
    - Responsible agent: Marketing, LandingPage, LeadGen, or Control.
    - Dependencies, if any.
    - A clear completion criterion.

    Include the work needed to produce a landing page, find suitable
    leads, create marketing assets, and prepare outreach drafts.

    Use the validation findings to prioritise the most useful work.
    Return only the Markdown plan, without introductory commentary.
    """,
            reads=["idea.md", "validation.md", "lessons.md"],
            writes="plan.md",
            mock="""# Plan

    ## Audience
    Identify the primary target customer and their main needs.

    ## Design philosophy
    Use a clear, accessible layout, consistent colours, and a
    prominent value proposition.

    ## Marketing philosophy
    Use evidence-informed messaging that communicates the product's
    main benefit to the intended audience.

    ## Tasks
    1. Marketing: define positioning and messaging.
    2. Creative: prepare campaign assets based on the approved brief.
    3. LandingPage: build a page following the design philosophy.
    4. LeadGen: find and qualify suitable prospects.
    5. Control: coordinate tasks and request approval before outreach.
    """
        ),


        "landing": AgentSpec(
            name="LandingPage",
            system_prompt="""
    You are an expert landing page designer and frontend developer.

    Your job is to build a polished landing page for the founder's
    business using the approved plan in plan.md.

    Read plan.md carefully. Follow its:
    - Target audience.
    - Design philosophy.
    - Suggested colours, typography, and tone.
    - Marketing philosophy and value proposition.

    OUTPUT RULES:
    - Return ONE complete HTML document.
    - Start with <!DOCTYPE html> and end with </html>.
    - Include all CSS inside a <style> tag.
    - Include JavaScript inside a <script> tag only if necessary.
    - Do not use external CSS frameworks or JavaScript libraries.
    - Do not depend on external images, fonts, or other assets.
    - Use CSS gradients, shapes, and simple visual elements where
      they improve the design.
    - Do not include Markdown code fences or commentary.
    - Do not output a partial HTML document.
    - Make the page responsive on mobile and desktop.
    - Use semantic HTML and accessible colour contrast.
    - Make buttons and navigation links work where applicable.

    REQUIRED SECTIONS:
    1. Hero: a strong headline, supporting description, and one
       prominent call-to-action button.
    2. Three benefits: explain three specific customer benefits
       relevant to the business.
    3. Social proof: use genuine evidence supplied in the plan.
       Never fabricate customer testimonials, company logos,
       reviews, user counts, or performance statistics.
       If verified evidence is unavailable, use an honest
       trust-building section instead.
    4. Final call to action: clearly explain the next step for
       an interested visitor.

    DESIGN QUALITY:
    - Establish a clear visual hierarchy.
    - Use consistent spacing, typography, and colours.
    - Make the first screen visually compelling.
    - Keep copy concise and specific to the business.
    - Avoid generic placeholder marketing copy.
    - Do not invent product features or guarantees.
    - Use clear focus states and accessible button labels.

    Return only the complete HTML source. Do not wrap it in
    Markdown fences or explain your design.
    """,
            reads=["plan.md"],
            writes="landing.md",
            mock="""<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Business Landing Page</title>
      <style>
        * { box-sizing: border-box; }
        body {
          margin: 0;
          font-family: Arial, sans-serif;
          color: #172033;
          background: #f7f8fc;
          line-height: 1.6;
        }
        main { max-width: 1000px; margin: auto; padding: 48px 24px; }
        .hero { padding: 64px 0; text-align: center; }
        h1 { font-size: clamp(2.2rem, 6vw, 4rem); line-height: 1.1; }
        .benefits { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
        .benefit { padding: 24px; background: white; border-radius: 16px; }
        .cta { display: inline-block; padding: 12px 22px; background: #243cdb; color: white; border-radius: 8px; text-decoration: none; }
        @media (max-width: 650px) {
          .benefits { grid-template-columns: 1fr; }
          .hero { padding: 32px 0; }
        }
      </style>
    </head>
    <body>
      <main>
        <section class="hero">
          <p>Your next chapter starts here</p>
          <h1>A better way to solve your problem</h1>
          <p>Discover an approach designed around your needs.</p>
          <a class="cta" href="#get-started">Get started</a>
        </section>
        <section class="benefits">
          <article class="benefit">
            <h2>Simple</h2>
            <p>A straightforward experience focused on what matters.</p>
          </article>
          <article class="benefit">
            <h2>Practical</h2>
            <p>Useful features designed for everyday needs.</p>
          </article>
          <article class="benefit">
            <h2>Customer-focused</h2>
            <p>An experience built around the intended audience.</p>
          </article>
        </section>
        <section>
          <h2>Built around your needs</h2>
          <p>Learn how the product can help you make progress.</p>
        </section>
        <section id="get-started">
          <h2>Ready to take the next step?</h2>
          <a class="cta" href="mailto:hello@example.com">Get in touch</a>
        </section>
      </main>
    </body>
    </html>"""
        ),

    "leads": AgentSpec(
        name="LeadGen",
        system_prompt=(
            "Use only the public post results provided under TOOL RESULTS. "
            "Do not invent leads, contact information, handles, or evidence. "
            "Return only a markdown table with this exact header: "
            "| name | handle | contact | why |"
        ),
        reads=["plan.md"], writes="leads.md",
        mock="| name | handle | contact | why |\n| --- | --- | --- | --- |"),
    "marketing": AgentSpec(
        name="Marketing",
        system_prompt=(
            "Create four concise, personalized outreach message variants using "
            "the plan, leads, and lessons. Return only valid JSON: no Markdown "
            "fences, labels, or commentary. The JSON must be an object with "
            "for the initial set, use exactly these keys and this schema: "
            '{"A":{"angle":"pain-point","subject":"...","text":"..."},'
            '"B":{"angle":"social-proof","subject":"...","text":"..."},'
            '"C":{"angle":"question","subject":"...","text":"..."},'
            '"D":{"angle":"offer-first","subject":"...","text":"..."}}. '
            "Give each variant a distinct, concise subject of 2-8 words "
            "that fits its angle and the business idea. Do not include "
            "placeholders or line breaks in subjects. Each text must be a "
            "well-formatted plain-text email body under 60 words, start with "
            "'Hi {name},', put a blank line after the greeting, and use blank "
            "lines between paragraphs. Include the literal {name}, {offer}, "
            "and {link} placeholders. {offer} is a concise description of the "
            "founder's actual product or service and must appear naturally. "
            "End every email with a short call to action and the {link} "
            "placeholder on its own final line; the sender fills it with the "
            "live landing page URL. "
            "Never include a {why} placeholder or internal lead-search notes, "
            "source descriptions, or contact-discovery rationale. Do not invent customer "
            "interest, testimonials, results, or other social proof. When the "
            "task asks for challenger variants, include A-D plus E with angle "
            "curiosity-led and F with angle proof-led, using the same object "
            "shape, subject rules, and body-format rules for all six variants."
        ),
        reads=["plan.md", "leads.md", "lessons.md"], writes="variants.json",
        mock=(
            '{"A":{"angle":"pain-point","subject":"A practical idea for you",'
            '"text":"Hi {name},\\n\\nI am reaching out about {offer}. '
            'Would improving this be useful to your team?\\n\\n{link}"},'
            '"B":{"angle":"social-proof","subject":"An approach worth exploring",'
            '"text":"Hi {name},\\n\\n{offer} may be relevant to your team. '
            'I would value your perspective on this approach.\\n\\n'
            'Would you be open to a brief conversation?\\n\\n{link}"},'
            '"C":{"angle":"question","subject":"A quick question",'
            '"text":"Hi {name},\\n\\nI am exploring {offer}. '
            'Is this a challenge your team is working on?\\n\\n{link}"},'
            '"D":{"angle":"offer-first","subject":"A useful idea to share",'
            '"text":"Hi {name},\\n\\n{offer} is what I am building, and '
            'I can share a short overview of how it may help your team.\\n\\n'
            'Would that be useful?\\n\\n{link}"}}'
        ),
    ),
}

# every agent sees founder feedback (written by Control.revise)
for _s in SPECS.values():
    _s.reads.append("feedback.md")
