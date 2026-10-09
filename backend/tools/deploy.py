"""OWNER: Person C. Publish a landing page and return its live URL."""

async def deploy_html(html: str, site_name: str) -> str:
    """Deploy a single self-contained HTML string. Return the live public URL."""
    # TODO(C): Netlify deploy API (zip upload) or Vercel API. Must return an https URL.
    return f"https://{site_name}.example.com"
