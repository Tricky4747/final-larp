
"""Publish a self-contained HTML landing page using Netlify."""

import io
import logging
import os
import re
import uuid
import zipfile

import httpx

logger = logging.getLogger(__name__)

NETLIFY_API = "https://api.netlify.com/api/v1"


async def deploy_html(html: str, site_name: str) -> str:
    """Deploy HTML to Netlify and return its HTTPS URL.

    Returns an empty string when deployment is unavailable or fails.
    This allows the rest of the pipeline to continue in mock mode.
    """
    token = os.getenv("NETLIFY_AUTH_TOKEN")

    # No token means the project is running without live deployment.
    if not token:
        logger.info(
            "Mock mode: deployment skipped because NETLIFY_AUTH_TOKEN "
            "is not configured."
        )
        return ""

    if not html or not html.strip():
        logger.warning("Deployment skipped: HTML content is empty.")
        return ""

    # Create a safe, unique site name.
    slug = re.sub(r"[^a-z0-9-]+", "-", site_name.lower())
    slug = slug.strip("-")[:30] or "crewdesk-demo"
    slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # Netlify accepts a ZIP containing the website files.
    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(
        archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("index.html", html)

    archive_bytes = archive_buffer.getvalue()

    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # 1. Create a new Netlify site.
            site_response = await client.post(
                f"{NETLIFY_API}/sites",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": slug},
            )
            site_response.raise_for_status()

            site = site_response.json()
            site_id = site.get("id")

            if not site_id:
                logger.warning("Netlify did not return a site ID.")
                return ""

            # 2. Upload the ZIP and start deployment.
            deploy_response = await client.post(
                f"{NETLIFY_API}/sites/{site_id}/deploys",
                headers={
                    **headers,
                    "Content-Type": "application/zip",
                },
                content=archive_bytes,
            )
            deploy_response.raise_for_status()

            deployment = deploy_response.json()

            # Prefer HTTPS URLs supplied by Netlify.
            url = (
                deployment.get("deploy_ssl_url")
                or deployment.get("ssl_url")
                or site.get("ssl_url")
                or deployment.get("deploy_url")
                or site.get("url")
                or ""
            )

            # Never report a missing or non-HTTPS URL as a live URL.
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]

            if not url.startswith("https://"):
                logger.warning("Netlify did not return a usable HTTPS URL.")
                return ""

            logger.info("Netlify deployment submitted: %s", url)
            return url

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Netlify API returned HTTP %s.",
            exc.response.status_code,
        )
        return ""

    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Netlify deployment failed: %s", exc)
        return ""
