export default function LinkCard({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className="mt-2 block rounded-lg border-2 border-amber bg-ink p-4 hover:bg-panel">
      <span className="block text-xs text-mute">Your live landing page</span>
      <span className="block break-all text-base font-semibold text-amber underline">{url}</span>
      <span className="mt-1 block text-xs text-mute">Open in a new tab</span>
    </a>
  );
}
