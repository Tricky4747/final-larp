
"""Deploy a self-contained HTML landing page to Netlify."""

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid

import httpx

from pathlib import Path
from dotenv import load_dotenv

for _p in (
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent / ".env.local",
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[1] / ".env.local",
    Path(__file__).resolve().parents[2] / ".env",
    Path(__file__).resolve().parents[2] / ".env.local",
):
    if _p.is_file():
        load_dotenv(_p)

logger = logging.getLogger(__name__)

NETLIFY_API = "https://api.netlify.com/api/v1"


async def deploy_html(html: str, site_name: str) -> str:
    """Deploy HTML and return its public HTTPS URL when ready."""

    token = os.getenv("NETLIFY_AUTH_TOKEN", "").strip()

    if not token:
        logger.info("Mock mode: Netlify token is not configured.")
        return ""

    if not html.strip():
        logger.warning("Cannot deploy empty HTML.")
        return ""

    # Create a safe, unique site name.
    slug = re.sub(r"[^a-z0-9-]+", "-", site_name.lower())
    slug = slug.strip("-")[:25] or "crewdesk"
    slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    headers = {"Authorization": f"Bearer {token}"}
    html_bytes = html.encode("utf-8")
    sha1 = hashlib.sha1(html_bytes).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Create a Netlify site.
            response = await client.post(
                f"{NETLIFY_API}/sites",
                headers=headers,
                json={"name": slug},
            )
            response.raise_for_status()
            site = response.json()

            site_id = site.get("id")
            if not site_id:
                logger.warning("Netlify did not return a site ID.")
                return ""

            # 2. Register index.html using its SHA-1 digest.
            response = await client.post(
                f"{NETLIFY_API}/sites/{site_id}/deploys",
                headers=headers,
                json={"files": {"/index.html": sha1}},
            )
            response.raise_for_status()
            deploy = response.json()

            deploy_id = deploy.get("id")
            if not deploy_id:
                logger.warning("Netlify did not return a deploy ID.")
                return ""

            # 3. Upload the HTML if Netlify requests this file.
            required = deploy.get("required", [])

            if sha1 in required:
                response = await client.put(
                    f"{NETLIFY_API}/deploys/{deploy_id}/files/index.html",
                    headers={
                        **headers,
                        "Content-Type": "application/octet-stream",
                    },
                    content=html_bytes,
                )
                response.raise_for_status()

            # 4. Wait for Netlify to finish processing the deploy.
            deadline = time.monotonic() + 60

            while time.monotonic() < deadline:
                response = await client.get(
                    f"{NETLIFY_API}/deploys/{deploy_id}",
                    headers=headers,
                )
                response.raise_for_status()
                deploy = response.json()
                state = deploy.get("state", "")

                if state == "ready":
                    break

                if state == "error":
                    logger.warning("Netlify deployment failed.")
                    return ""

                await asyncio.sleep(2)
            else:
                logger.warning(
                    "Netlify deployment did not become ready in time."
                )
                return ""

            # 5. Return a URL only after the deployment is ready.
            url = (
                deploy.get("ssl_url")
                or deploy.get("deploy_ssl_url")
                or site.get("ssl_url")
                or ""
            )

            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]

            if not url.startswith("https://"):
                logger.warning("No HTTPS deployment URL was returned.")
                return ""

            logger.info("Netlify deployment is ready: %s", url)
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
