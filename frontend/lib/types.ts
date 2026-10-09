export type Kind = "message" | "file_update" | "approval_request" | "status";
export type Message = {
  id: string; ts: number; sender: string; channel: string; text: string; kind: Kind;
  meta: { file?: string; id?: string; url?: string; stage?: string | null; dm?: boolean; type?: string };
};
export type Variant = { sends: number; replies: number; rate: number };
export type Experiments = Record<string, Variant>;
