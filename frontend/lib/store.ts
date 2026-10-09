import { create } from "zustand";
import { Message, Experiments } from "./types";

type S = {
  messages: Message[]; seen: Record<string, true>;
  active: string; unread: Record<string, boolean>;
  agents: string[]; files: string[]; fileContents: Record<string, string>;
  flashing: Record<string, number>; openFile: string | null; tab: "files" | "experiments";
  approvals: Record<string, "approved" | "rejected" | "changes">; ideaSent: boolean; experiments: Experiments; connected: boolean;
  addMessage: (m: Message) => boolean;
  setActive: (c: string) => void;
  set: (p: Partial<S>) => void;
  flash: (f: string) => void;
  setFile: (name: string, content: string) => void;
  setApproval: (id: string, v: "approved" | "rejected" | "changes") => void;
};

export const useStore = create<S>((set, get) => ({
  messages: [], seen: {}, active: "group", unread: {}, agents: [], files: [], fileContents: {},
  flashing: {}, openFile: null, tab: "files", approvals: {}, ideaSent: false, experiments: {}, connected: false,
  addMessage: (m) => {
    if (get().seen[m.id]) return false;           // history replays on reconnect: dedupe by id
    set((s) => ({
      seen: { ...s.seen, [m.id]: true },
      ideaSent: s.ideaSent || m.sender === "founder" || m.text.startsWith("Idea received"),
      messages: [...s.messages, m].sort((a, b) => a.ts - b.ts),
      unread: m.channel !== s.active && m.sender !== "founder" ? { ...s.unread, [m.channel]: true } : s.unread,
    }));
    return true;
  },
  setActive: (c) => set((s) => ({ active: c, unread: { ...s.unread, [c]: false } })),
  set: (p) => set(p),
  flash: (f) => {
    set((s) => ({ flashing: { ...s.flashing, [f]: Date.now() } }));
    setTimeout(() => set((s) => { const x = { ...s.flashing }; delete x[f]; return { flashing: x }; }), 1800);
  },
  setFile: (name, content) => set((s) => ({ fileContents: { ...s.fileContents, [name]: content } })),
  setApproval: (id, v) => set((s) => ({ approvals: { ...s.approvals, [id]: v } })),
}));

export const selectChannels = (s: S) => {
  const set = new Set<string>(["group", ...s.agents]);
  s.messages.forEach((m) => set.add(m.channel));   // unseen channels get a chat on the fly
  return Array.from(set);
};

/** Only the newest approval card can still be answered; older ones were resolved or lost on a backend restart. */
export const selectLatestApprovalId = (s: S) => {
  for (let i = s.messages.length - 1; i >= 0; i--) if (s.messages[i].kind === "approval_request") return s.messages[i].meta.id;
  return undefined;
};
