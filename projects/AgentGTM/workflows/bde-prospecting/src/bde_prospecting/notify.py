"""Deliver messages to BDEs and founders.

Every message is written to the outbox folder first, so there is always a record of what
was sent. With send=True it is also delivered on the person's channel:

- file:  outbox only
- slack: POST to the incoming-webhook URL held in the env var named by `contact`
- email: SMTP using SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Messages only go to people listed in the config (BDEs and founders), never to prospects.
"""

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from pathlib import Path


def deliver(outbox, day, recipient_id, subject, body, channel, contact, send):
    folder = Path(outbox) / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{recipient_id}.md"
    path.write_text(f"# {subject}\n\n{body}\n", encoding="utf-8")
    if not send or channel == "file":
        return f"written to {path}"
    if channel == "slack":
        url = os.environ.get(contact or "")
        if not url:
            raise RuntimeError(f"{recipient_id}: env var {contact!r} with the Slack webhook URL is not set")
        req = urllib.request.Request(url, data=json.dumps({"text": f"*{subject}*\n{body}"}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return "sent to Slack"
    if channel == "email":
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, os.environ["SMTP_FROM"], contact
        msg.set_content(body)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return f"emailed {contact}"
    raise ValueError(f"unknown channel {channel!r}")
