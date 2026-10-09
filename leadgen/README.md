# Lead generation module

Python 3.11+ module that discovers potential business leads through Tavily's
official Search API. It uses search-result titles, content snippets, and source
URLs; it does not crawl result pages, bypass access controls, or invent contact
details or social handles. Results are candidates supported by their cited
source, not proof that a lead is qualified. Verify source facts and terms before
contacting anyone.

## API setup

1. Create an account at [Tavily](https://tavily.com/) and create an API key
   from its dashboard. See the [Search API reference](https://docs.tavily.com/documentation/api-reference/endpoint/search)
   for the current endpoint details.
2. Set the key in your shell environment. Do not place it in source code or
   commit it:

   ```powershell
   $env:TAVILY_API_KEY = "your_tavily_api_key"
   ```

3. Check Tavily's current API terms, rate limits, quota, and pricing before
   using it. The module calls the official Search endpoint, asks for basic
   general web results, uses a 15-second timeout, and does not automatically
   retry. API credentials and errors are never logged.

## Install and configure

The code and tests use Python's standard library; no third-party dependencies
are required. From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r leadgen\requirements.txt
```

Edit `leadgen/lead_search.json` to configure the search:

```json
{
  "business_idea": "AI-powered social media content service",
  "target_customer": "Small marketing agencies",
  "location": "India",
  "limit": 20
}
```

`limit` must be between 1 and 20. The API key is read from
`TAVILY_API_KEY`.

## Run

Run from the project root:

```powershell
python -m leadgen.lead_scraper --config leadgen/lead_search.json --output leadgen/leads.json
```

By default the Markdown export is `leadgen/leads.md`; customize it with
`--markdown`. Defaults are resolved relative to this module, while explicit
paths are resolved from the current directory when the path or its parent
exists. The command reports discovered search results, rejected records
(invalid results and duplicates), and saved leads.

The output JSON contains records with exactly these fields: `name`, `handle`,
`contact`, `why`, and `where`. This search-result-only implementation leaves
`handle` and `contact` empty rather than scraping source pages or guessing
business contact details. Each `why` states the observed search listing and
separately identifies the inferred relevance.

Functions for later application integration:

```python
from leadgen.lead_scraper import (
    search_leads,
    save_leads,
    export_markdown,
)

leads = search_leads(config)
save_leads(leads, "leadgen/leads.json")
export_markdown(leads, "leadgen/leads.md")
```

`validate_lead()` and `deduplicate_leads()` are also available from
`leadgen.lead_scraper`.

Respect source terms and any applicable robots directives when independently
reviewing links. Use public business information only; do not bypass logins,
CAPTCHAs, paywalls, rate limits, or other access controls, and do not collect
private personal information. If no reliable public business contact is
available, leave it empty.

## Tests

Tests mock the API response and make no network requests. No API key is needed:

```powershell
python -m unittest discover -s leadgen\tests -v
```
