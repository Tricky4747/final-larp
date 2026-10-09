# Gmail API personalized email sender

A Python 3.11+ command-line sender that validates a JSON batch and sends one
plain-text email per recipient through the official Gmail API. The reusable
`load_records()`, `send_email()`, and `send_batch()` functions are also
available from `sender.py` (or as package exports from the repository root).

## Google Cloud and OAuth setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. In **APIs & Services → Library**, enable the **Gmail API** for that project.
3. Configure the **OAuth consent screen**. Choose the appropriate user type,
   complete the required app details, and add your Google account as a test
   user if the app remains in testing.
4. In **APIs & Services → Credentials**, create an OAuth client ID with
   application type **Desktop app**.
5. Download the client JSON and save it at the repository root as
   `credentials.json`. Do not commit it or share it.
6. Install the Python dependencies:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r sender\requirements.txt
   ```

The first live send opens Google's installed-application authorization flow in
your browser. Sign into the Gmail account you intend to send from and grant the
requested `gmail.send` permission. The resulting local `token.json` is used on
subsequent runs and refreshed when possible. Both OAuth files are ignored by
Git. The program never asks for your Google password.

If authorization must be repeated, remove the local `token.json` and run a
live command again to start a new browser authorization. To revoke access,
open your Google Account's **Security → Third-party apps & services** (or
**Connections to third-party apps and services**), select this application,
and remove its access.

## Input, opt-outs, and compliance

`sender/emails.json` is the sample input. The JSON root must be a list, and
each item must contain exactly a valid `email` and a non-empty `message`. The
entire file is validated before OAuth or any send request begins.

`sender/opt-outs.json` contains addresses that must not be contacted. Keep it
current; matching recipients are recorded as `skipped`. Only contact people
when permitted by applicable law and provider policies. Obtain consent where
required, honor opt-outs promptly, and include appropriate unsubscribe or
opt-out instructions in outreach. Live sending requires an explicit operator
confirmation; the application cannot determine a recipient's consent or other
legal basis.

## Preview and first test email

From the repository root, preview input and opt-outs without starting OAuth or
making a Gmail API request:

```powershell
python sender\sender.py --file sender\emails.json --results sender\results.json --dry-run
```

For the first live test, edit `sender/emails.json` to contain only one message
addressed to an inbox you control. Make sure the recipient is eligible to
receive it, then run:

```powershell
python sender\sender.py --file sender\emails.json --results sender\results.json --compliance-confirmed
```

The browser authorization flow will run if needed. The subject defaults to
`A quick introduction`; customize it with `--subject`. The sender MIME message
does not accept a user-supplied `From` address: Gmail sends as the account
authorized in the OAuth flow.

Once the one-recipient test is satisfactory, replace the JSON input with the
intended eligible batch and run the same live command. `--file`, `--results`,
and `--opt-outs` accept custom paths; if omitted, they resolve to files in
`sender/`.

## Results and failure handling

`sender/results.json` is atomically rewritten after each recipient. Each
record contains:

- `recipient`
- `status`: `accepted`, `failed`, `unknown`, or `skipped`
- `timestamp` (UTC)
- `provider_message_id`: Gmail API message ID when present, otherwise `null`
- `error`: useful API/authorization/network details, or `null`

`accepted` means Gmail's API accepted the send request; it does **not** confirm
inbox delivery. Check the recipient inbox (including spam) separately.
Definitive Gmail API errors such as authorization and quota responses are
recorded as `failed`. A network or timeout error during submission is
`unknown`; the tool will not automatically retry because Gmail may already
have accepted the message.

## Use from Python

```python
from sender import load_records, send_batch

records = load_records("sender/emails.json")
results = send_batch(
    records,
    results_path="sender/results.json",
    suppressed_emails={"opted-out@example.com"},
    compliance_confirmed=True,
)
```

When no `gmail_service` is passed, `send_batch()` performs or refreshes the
installed-app OAuth authorization and builds the Gmail API client itself.

For a FastAPI backend, initialize and refresh OAuth credentials in an
appropriate lifecycle, authorize sending for the caller, apply current opt-out
and consent checks, and run blocking Google client operations in a worker
thread.

## Tests

The `unittest` suite uses mocked Gmail API services and synthetic OAuth
credentials. It never sends real emails and does not require actual Google
credentials:

```powershell
python -m unittest discover -s sender\tests -v
```
