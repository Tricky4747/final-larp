import { Message } from "@/lib/types";
export default function StatusLine({ m }: { m: Message }) {
  return <div className="pop px-2 text-xs italic text-mute">{m.sender}: {m.text}</div>;
}
