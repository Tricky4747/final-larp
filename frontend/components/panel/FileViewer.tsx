"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "@/lib/store";

type Variant = { angle?: string; text: string };

function parseVariants(name: string, content: string): [string, Variant][] {
  if (name === "variants.json") {
    try {
      const o = JSON.parse(content);
      return Object.entries(o).filter(([, v]) => v && typeof (v as Variant).text === "string") as [string, Variant][];
    } catch { return []; }
  }
  if (name === "variants.md") {   // legacy format: "A: text" lines
    return content.split("\n").map((l) => l.match(/^([A-F]):\s*(.*)$/)).filter(Boolean).map((m) => [m![1], { text: m![2] }] as [string, Variant]);
  }
  return [];
}

export default function FileViewer({ name }: { name: string }) {
  const content = useStore((s) => s.fileContents[name]);
  if (content === undefined) return <p className="p-4 text-sm text-mute">Loading {name}...</p>;
  if (!content.trim()) return <p className="p-4 text-sm text-mute">{name} is empty. It has not been written yet.</p>;

  if (name === "landing.md") {
    const first = content.split("\n", 1)[0];
    const url = first.match(/<!--\s*live:\s*(\S+?)\s*-->/)?.[1];
    const deployed = !!url && url !== "UNDEPLOYED";
    const html = content.replace(/^<!--.*?-->\s*/, "");
    return (
      <div className="p-4">
        {deployed
          ? <a href={url} target="_blank" rel="noopener noreferrer" className="mb-3 block break-all text-sm text-amber underline">{url}</a>
          : <p className="mb-3 rounded bg-ink p-2 text-xs text-mute">Not deployed yet. This is a local preview of the generated HTML.</p>}
        {/* sandbox="" blocks scripts and navigation: generated HTML is untrusted */}
        <iframe title="Landing page preview" sandbox="" srcDoc={html} className="h-80 w-full rounded border border-line bg-white" />
        <details className="mt-2"><summary className="cursor-pointer text-xs text-mute">View HTML source</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded bg-ink p-3 text-xs">{content}</pre></details>
      </div>
    );
  }

  const variants = parseVariants(name, content);
  if (variants.length > 0) {
    return (
      <div className="space-y-2 p-4">
        {variants.map(([k, v]) => (
          <div key={k} className="rounded-lg bg-raise p-3">
            <div className="flex items-center justify-between text-xs font-semibold text-amber"><span>Variant {k}</span>{v.angle && <span className="font-normal text-mute">{v.angle}</span>}</div>
            <p className="mt-1 whitespace-pre-wrap text-sm">{v.text}</p>
          </div>
        ))}
      </div>
    );
  }
  if (name.endsWith(".json")) {
    let pretty = content; try { pretty = JSON.stringify(JSON.parse(content), null, 2); } catch {}
    return <pre className="max-h-[28rem] overflow-auto p-4 text-xs">{pretty}</pre>;
  }
  return <div className="md overflow-x-auto p-4"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>;
}
