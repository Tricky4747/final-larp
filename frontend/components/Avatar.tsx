"use client";
import { useState } from "react";
import { agentColor } from "@/lib/agentColors";

const BUNDLED = ["Control", "Validation", "Planner", "LandingPage", "LeadGen", "Marketing", "group", "founder"];

/** Profile picture for a chat or sender. Pictures live in public/avatars/<Name>.svg (replace a file to change one).
 *  Unknown channels, or a missing file, fall back to a colored initial. */
export default function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const label = name === "group" ? "Group" : name === "founder" ? "Founder" : name;
  const style = { width: size, height: size };
  if (failed || !BUNDLED.includes(name)) {
    return <span aria-hidden className="grid shrink-0 place-items-center rounded-full font-bold text-ink" style={{ ...style, background: agentColor(name), fontSize: size * 0.4 }}>{label[0]?.toUpperCase()}</span>;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={`/avatars/${name}.svg`} alt="" aria-hidden width={size} height={size} style={style} className="shrink-0 rounded-full object-cover" onError={() => setFailed(true)} />;
}
