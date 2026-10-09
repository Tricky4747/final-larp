import { Experiments, Message } from "./types";
import { MOCK_AGENTS, MOCK_CONTENT, MOCK_EXPERIMENTS, MOCK_FILES } from "./mockMessages";
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
const post = (path: string, body: unknown) =>
  j<{ ok: boolean }>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getAgents = () => MOCK ? Promise.resolve(MOCK_AGENTS) : j<{ name: string }[]>("/agents");
export const getFiles = () => MOCK ? Promise.resolve(MOCK_FILES) : j<string[]>("/files");
export const getFile = (n: string) => MOCK
  ? Promise.resolve({ name: n, content: MOCK_CONTENT[n] ?? "" })
  : j<{ name: string; content: string }>("/files/" + encodeURIComponent(n));
export const getExperiments = () => MOCK ? Promise.resolve(MOCK_EXPERIMENTS) : j<Experiments>("/experiments");
export const postIdea = (idea: string) => MOCK ? Promise.resolve({ ok: true }) : post("/idea", { idea });
export const postApprove = (id: string, ok: boolean) => MOCK ? Promise.resolve({ ok: true }) : post("/approve/" + id, { ok });
export type { Message };
