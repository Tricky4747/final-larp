import { Message, Experiments } from "./types";
const t0 = Math.floor(Date.now() / 1000) - 120;
let n = 0;
const m = (sender: string, channel: string, text: string, kind: Message["kind"] = "message", meta: Message["meta"] = {}): Message =>
  ({ id: `mock${String(n++).padStart(4, "0")}`, ts: t0 + n * 4, sender, channel, text, kind, meta });
export const MOCK_AGENTS = ["Control", "Validation", "Planner", "LandingPage", "LeadGen", "Marketing"].map((name) => ({ name }));
export const MOCK_FILES = ["idea.md", "validation.md", "plan.md", "landing.md", "leads.md", "variants.json"];
export const MOCK_CONTENT: Record<string, string> = {
  "idea.md": "AI bookkeeping for freelance designers",
  "validation.md": "## Competitors\n| Tool | Price |\n|---|---|\n| Bonsai | $24/mo |\n| Wave | free |\n\nVerdict: GO",
  "plan.md": "## Audience\nFreelance designers\n\n## Design philosophy\nCalm, warm, minimal\n\n## Tasks\n- Ship landing page",
  "landing.md": "<!-- live: UNDEPLOYED -->\n<html><body style=\"font-family:sans-serif;padding:24px\"><h1>Invoices that file themselves</h1><p>Bookkeeping for freelance designers.</p><button>Start free</button></body></html>",
  "leads.md": "| name | handle | contact | why |\n|---|---|---|---|\n| Ana | @ana | ana@x.com | Posts about invoicing pain |\n| Raj | @raj | raj@x.com | Runs a design studio |",
  "variants.json": JSON.stringify({ A: { angle: "pain-point", text: "Hi {name}, tired of chasing invoices? {why}" }, B: { angle: "social-proof", text: "{name}, 400 designers already use us." }, C: { angle: "curiosity", text: "{name}, what if invoices filled themselves?" }, D: { angle: "offer-first", text: "{name}, first 3 months free for you." } }),
};
export const MOCK_EXPERIMENTS: Experiments = {
  A: { sends: 9, replies: 1, rate: 0.11 }, B: { sends: 9, replies: 2, rate: 0.22 },
  C: { sends: 8, replies: 1, rate: 0.13 }, D: { sends: 24, replies: 9, rate: 0.38 },
  E: { sends: 0, replies: 0, rate: 0 }, F: { sends: 0, replies: 0, rate: 0 },
};
export const MOCK_MESSAGES: Message[] = [
  m("Control", "group", "Idea received. Kicking off the pipeline."),
  m("Validation", "Validation", "Searching competitors...", "status"),
  m("Validation", "group", "Validation done. Verdict: GO. Surprise: top rival has no free tier."),
  m("Validation", "group", "Validation updated validation.md", "file_update", { file: "validation.md" }),
  m("Planner", "Planner", "Drafting plan...", "status"),
  m("Planner", "group", "Plan is ready.", "message"),
  m("Planner", "group", "Planner updated plan.md", "file_update", { file: "plan.md" }),
  m("Control", "group", "Approve deploying the landing page?", "approval_request", { id: "ap000001", stage: "plan", file: "plan.md" }),
  m("LandingPage", "group", "Landing page is live.", "message", { url: "https://example.netlify.app" }),
  m("LeadGen", "LeadGen", "Finding leads...", "status"),
  m("LeadGen", "group", "20 leads found.", "message"),
  m("LeadGen", "group", "LeadGen updated leads.md", "file_update", { file: "leads.md" }),
  m("Marketing", "group", "Four DM variants written.", "message"),
  m("Marketing", "group", "Marketing updated variants.json", "file_update", { file: "variants.json" }),
  m("Control", "group", "Round 1 done. Leading variant: D. Stats: {}"),
  m("Control", "group", "Marketing added challenger variants: E, F."),
];
