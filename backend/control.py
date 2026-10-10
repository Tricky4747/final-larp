import asyncio, json, os, re, uuid
from pathlib import Path
from agent import Agent
from agents.specs import SPECS
from bus import Bus, Message
from workspace import Workspace
from experiments import Experiments
from llm import complete, parse_json

class Control:
    def __init__(self, ws: Workspace, bus: Bus, auto_approve: bool = True):
        self.ws, self.bus, self.auto_approve = ws, bus, auto_approve
        self.agents = {k: Agent(s, ws, bus) for k, s in SPECS.items()}
        from agents.custom import CUSTOM          # C & D's agents with real tools override the generic ones
        for k, cls in CUSTOM.items():
            self.agents[k] = cls(SPECS[k], ws, bus)
        self.exp = Experiments()
        self.approvals: dict[str, asyncio.Future] = {}
        self.round = 0

    async def say(self, text, **kw):
        await self.bus.post(Message(sender="Control", text=text, **kw))

    async def approve(self, approval_id: str, ok: bool, feedback: str = ""):
        f = self.approvals.get(approval_id)
        if f and not f.done():
            f.set_result({"ok": ok, "feedback": feedback})

    async def ask_founder(self, question: str, file: str | None = None, stage: str | None = None) -> dict:
        """Post an approval card and wait. Returns {"ok": bool, "feedback": str}."""
        aid = uuid.uuid4().hex[:6]
        fut = self.approvals[aid] = asyncio.get_running_loop().create_future()
        await self.bus.post(Message(sender="Control", text=question, kind="approval_request",
                                    meta={"id": aid, "stage": stage, "file": file}))
        if self.auto_approve:                      # CLI mode; API mode waits for POST /approve/{id}
            fut.set_result({"ok": True, "feedback": ""})
        return await fut

    async def revise(self, agent_key: str, feedback: str):
        agent = self.agents[agent_key]
        await self.ws.append("feedback.md", f"- [{agent.name}] {feedback}", "founder")
        await self.say(f'Got it. Sending your feedback to {agent.name}: "{feedback}"')
        await agent.run(f"Revise your previous output according to this founder feedback: {feedback}")

    async def gate(self, stage: str, question: str, agent_key: str, file: str | None = None,
                   max_revisions: int = 5) -> bool:
        """Approve -> True. Request changes (with text) -> revise that agent, ask again.
        Reject with empty text -> stop the pipeline (False)."""
        for i in range(max_revisions + 1):
            r = await self.ask_founder(question, file=file, stage=stage)
            if r["ok"]:
                return True
            fb = r["feedback"].strip()
            if not fb:
                await self.say("Okay, stopping here. Tell me what to change, or send a new idea.")
                return False
            if i == max_revisions:
                await self.say("Revision limit reached, continuing with the current version.")
                return True
            await self.revise(agent_key, fb)
        return True

    async def choose_tasks(self) -> list[dict[str, str]]:
        """Ask Control to select the post-plan tasks, with a safe default."""
        default = [
            {"agent": "landing", "task": "Build the landing page."},
            {"agent": "leads", "task": "Find target leads."},
        ]
        prompt = (
            "Choose the tasks to run after the approved plan. Return only JSON in this "
            "shape: {\"tasks\": [{\"agent\": \"landing\", \"task\": \"...\"}, "
            "{\"agent\": \"leads\", \"task\": \"...\"}]}. "
            "Use exactly one landing task and one leads task; they can run in parallel. "
            f"\n\nAPPROVED PLAN:\n{self.ws.read('plan.md')}"
        )
        try:
            decision = parse_json(await complete(
                "You are Control, the task orchestrator.",
                prompt,
                mock=json.dumps({"tasks": default}),
                max_tokens=500,
            ))
            tasks = decision.get("tasks")
            if not isinstance(tasks, list):
                raise ValueError("tasks must be a list")
            normalized = []
            for item in tasks:
                if not isinstance(item, dict):
                    raise ValueError("each task must be an object")
                agent_key = item.get("agent")
                task = item.get("task")
                if agent_key not in self.agents or not isinstance(task, str) or not task.strip():
                    raise ValueError("task contains an unknown agent or empty instruction")
                normalized.append({"agent": agent_key, "task": task.strip()})
            if {item["agent"] for item in normalized} != {"landing", "leads"}:
                raise ValueError("Control must select landing and leads")
            return normalized
        except (Exception, json.JSONDecodeError) as exc:
            await self.say(f"Control task plan unavailable ({exc}); using the default sequence.", kind="status")
            return default

    @staticmethod
    def _validation_summary(report: str) -> str:
        sections = []
        lines = report.splitlines()
        wanted = {"Final Recommendation", "Surprising Finding", "Risks and Assumptions"}
        for index, line in enumerate(lines):
            title = line.lstrip("# ").strip()
            if title not in wanted:
                continue
            content = []
            for following in lines[index + 1:]:
                if following.lstrip().startswith("#"):
                    break
                if following.strip():
                    content.append(following.strip(" -*"))
            if content:
                sections.append(" ".join(content))
        if not sections:
            sections = [line.strip(" -*") for line in lines if line.strip() and not line.startswith("#")][:3]
        return " ".join(sections)[:700] or "The validation report did not include a summary."

    async def run_pipeline(self, idea: str):
        await self.ws.write("idea.md", f"# Idea\n{idea}", "founder")
        await self.say("Idea received. Starting validation.")
        await self.agents["validation"].run("Validate this idea.")
        validation_report = self.ws.read("validation.md")
        verdict = "NO-GO" if "NO-GO" in validation_report.upper() else "GO"
        await self.say(f"Validation said {verdict}. Here's a summary: {self._validation_summary(validation_report)}")
        if verdict == "NO-GO":
            if not await self.gate("verdict", "Validation says NO-GO. Continue anyway?", "validation", file="validation.md"):
                return
        await self.agents["planner"].run("Create the plan.")
        if not await self.gate("plan", "Here's the plan. Proceed to build?", "planner", file="plan.md"):
            return

        tasks = await self.choose_tasks()
        await self.say("Plan approved. Control dispatching " + ", ".join(
            f"{task['agent']}" for task in tasks
        ) + " in parallel.")
        await asyncio.gather(*(
            self.agents[task["agent"]].run(task["task"])
            for task in tasks
        ))
        landing_content = self.ws.read("landing.md")

        if "<!-- live: UNDEPLOYED -->" in landing_content:
            landing_prompt = (
                "Landing page HTML was generated, but it is not deployed. "
                "Continue anyway?"
            )
        else:
            landing_prompt = "Landing page is live. Keep it as is?"

        if not await self.gate(
            "landing",
            landing_prompt,
            "landing",
            file="landing.md",
        ):
            return
        await self.agents["marketing"].run("Write DM variants.")
        for v in "ABCD": self.exp.register(v)
        if not await self.gate("variants", "Approve these DM variants?", "marketing", file="variants.json"):
            return
        await self.run_round(10)

    def _load_leads_for_outreach(self) -> list[dict[str, str]]:
        content = self.ws.read("leads.md")
        leads: list[dict[str, str]] = []
        if content:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            data_lines = [l for l in lines if l.startswith("|") and not l.startswith("| ---") and not l.startswith("| name")]
            for line in data_lines:
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 4:
                    name, handle, contact, why = parts[0], parts[1], parts[2], parts[3]
                    why_clean = re.sub(r"\[.*?\]\(.*?\)", "", why).strip()
                    first_email = contact.split(",")[0].strip() if contact else ""
                    leads.append({
                        "name": name,
                        "handle": handle,
                        "contact": contact,
                        "email": first_email,
                        "why": why_clean,
                    })
        if not leads:
            leads_json_path = Path(__file__).resolve().parent / "tools" / "leads.json"
            if leads_json_path.is_file():
                try:
                    raw = json.loads(leads_json_path.read_text(encoding="utf-8"))
                    if isinstance(raw, list):
                        leads = raw
                except Exception:
                    pass
        return leads

    async def next_round(self, n: int = 10) -> bool:
        """Start one founder-approved outreach round from an API request."""
        return await self.run_round(n)

    async def run_round(self, n: int) -> bool:
        self.round += 1
        plan = self.exp.allocate(n)
        split = ", ".join(f"{v}: {plan.count(v)}" for v in sorted(set(plan)))
        stats = self.exp.stats()
        winner = self.exp.winner()
        if winner:
            explored = len(plan) - plan.count(winner)
            tested = len({v for v in plan if v != winner})
            rate = stats[winner]["rate"] * 100
            narrative = (f"Variant {winner} leads at {rate:.0f}%. Sending "
                         f"{plan.count(winner) / n:.0%} of this batch as {winner}, "
                         f"testing {tested} new angles with the rest.")
        else:
            narrative = f"No variant has enough data yet. Current split: {split}."
        question = f"Send round {self.round} to {n} leads? {narrative}"
        if not await self.gate(f"round{self.round}", question,
                               "marketing", file="variants.json"):
            return False

        # Load discovered leads and send real outreach via outreach.py
        leads = self._load_leads_for_outreach()
        target_email = os.getenv("OUTREACH_TEST_EMAIL", "").strip()
        dispatched_count = 0
        outreach_log: list[str] = []

        for i, v in enumerate(plan):
            lead = leads[i % len(leads)] if leads else {"name": "Valued Partner", "why": "your online presence", "contact": ""}
            lead_name = re.sub(r"[\r\n]+", " ", lead.get("name", "Prospect")).strip()[:40]
            clean_why = re.sub(r"[\r\n|]+", " ", lead.get("why", "")).strip()[:150]

            if target_email:
                try:
                    from tools.outreach import send_dm
                    send_payload = {
                        "name": "there",  # use generic greeting since page titles make bad salutations
                        "email": target_email,
                        "why": clean_why or "your website presence",
                        "contact": target_email,
                    }
                    subject = "Regarding your website growth"
                    res = await send_dm(
                        send_payload,
                        variant=v,
                        subject=subject,
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                    if res.get("ok"):
                        dispatched_count += 1
                        outreach_log.append(f"- Sent variant **{v}** to **{lead_name}** ({lead.get('contact') or 'N/A'}) -> redirected to sandbox `{target_email}` (Message ID: `{res.get('id')}`)")
                    else:
                        outreach_log.append(f"- Variant **{v}** for **{lead_name}**: status `{res.get('status')}` ({res.get('error')})")
                except Exception as exc:
                    outreach_log.append(f"- Variant **{v}** for **{lead_name}** failed: `{exc}`")

            # Record outcome for multi-armed bandit explore/exploit learning
            self.exp.record(v, replied=await self.simulate_reply(v))

        s = self.exp.stats(); w = self.exp.winner()
        leader = f"Leading variant: {w}." if w else "Not enough data yet to name a winner."
        if dispatched_count > 0:
            await self.say(f"Sent {dispatched_count} personalized outreach emails via Gmail to sandbox inbox ({target_email}).")
        await self.say(f"Round {self.round} done. {leader} Stats: {s}")
        await self.ws.append("experiments.md", f"- {s}", "Control")
        if outreach_log:
            await self.ws.append("outreach.md", f"### Round {self.round} Outreach Log\n" + "\n".join(outreach_log), "Control")
        await self.learn_round(s)
        return True

    async def learn_round(self, stats: dict):
        saved_variants = json.loads(self.ws.read("variants.json"))
        variants = {
            key: value["text"]
            for key, value in saved_variants.items()
            if isinstance(value, dict) and isinstance(value.get("text"), str)
        }
        variant_context = "\n".join(f"{key}: {text}" for key, text in variants.items())
        prompt = ("Analyze this outreach experiment. Compare the variant wording with the "
                  "reply rates and explain the likely reason for the result. Write exactly "
                  "2-3 sentences of durable lessons for the next marketing round.\n\n"
                  f"VARIANTS:\n{variant_context}\n\nSTATS:\n{json.dumps(stats, sort_keys=True)}")
        fallback = self._fallback_lesson(variants, stats)
        try:
            lesson = await complete("You are the learning lead for an outreach experiment.",
                                    prompt, mock=fallback, max_tokens=500)
        except Exception:
            lesson = fallback
        await self.ws.append("lessons.md", lesson.strip(), "Control")
        await self.say(f"Learned from round {self.round}: {lesson.strip()}")

        winner = self.exp.winner()
        if winner:
            candidates = {key: value for key, value in self.exp.active_stats().items()
                          if key != winner and value["sends"]}
            if candidates:
                loser = min(candidates, key=lambda key: (candidates[key]["rate"], -candidates[key]["sends"]))
                self.exp.retire(loser)
                await self.say(f"Retiring variant {loser}; keeping {winner} as the current winner.")

        output = await self.agents["marketing"].run(
            "Use the new lessons to refresh the DM set. Keep A-D, and generate 1-2 new "
            "challenger variants E and F for the explore slice. Return valid JSON "
            "with exactly A-F, each containing angle and text."
        )
        refreshed = json.loads(output)
        challengers = {
            key: refreshed[key]
            for key in ("E", "F")
            if isinstance(refreshed.get(key), dict)
        }
        if set(challengers) != {"E", "F"}:
            refreshed = saved_variants
            refreshed.update({
                "E": {
                    "angle": "curiosity-led",
                    "text": "Hi {name}, I noticed {why}. Would you be open to sharing your perspective?",
                },
                "F": {
                    "angle": "proof-led",
                    "text": "Hi {name}, based on {why}, I can share a brief overview. Would that be useful?",
                },
            })
            await self.ws.write(
                "variants.json",
                json.dumps(refreshed, ensure_ascii=False, indent=2),
                "Control",
            )
            challengers = {key: refreshed[key] for key in ("E", "F")}
        for variant in challengers:
            self.exp.register(variant)
        await self.say(f"Marketing added challenger variants: {', '.join(sorted(challengers))}.")

    @staticmethod
    def _fallback_lesson(variants: dict[str, str], stats: dict) -> str:
        active = {key: value for key, value in stats.items() if value["sends"]}
        if not active:
            return "The first round does not provide enough reply data to identify a reliable pattern. Keep testing distinct angles before shifting the majority of sends."
        best = max(active, key=lambda key: active[key]["rate"])
        worst = min(active, key=lambda key: active[key]["rate"])
        return (f"Variant {best} currently leads at {active[best]['rate']:.0%}, while "
                f"variant {worst} trails at {active[worst]['rate']:.0%}; the wording differences "
                "should guide the next challenger angles. More sends are needed before treating this as a stable preference.")

    async def simulate_reply(self, variant: str) -> bool:
        import random
        return random.random() < {"A": .05, "B": .10, "C": .20, "D": .08,
                                  "E": .14, "F": .11}[variant]  # hidden "true" rates
