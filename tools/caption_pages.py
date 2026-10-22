#!/usr/bin/env python3
"""Caption each rendered page PNG with a local vision model, WITHOUT ever showing it the story sentence.

    python3 tools/caption_pages.py DIR STORY_ID

Reads DIR/<story>_pages.json (from render_pages.py), sends each PNG to Ollama
(http://localhost:11434/api/generate, model qwen3-vl:8b-instruct-q4_K_M, stream false) with a fixed prompt,
and writes DIR/<story>_captions.json: [{"page", "text", "caption"}]. `text` is copied from pages.json for the
reviewer only; it is never sent to the model. One retry per image; then a FAILED banner naming the page and a
non-zero exit (no skipping, nothing partial is written).
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:8b-instruct-q4_K_M"
PROMPT = ("Describe what is happening in this pixel-art picture in one or two sentences. "
          "Name the characters and animals you see and what they are doing.")


def fail(msg):
    print(f"\n*** FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def ask(png):
    """One Ollama call: image + the fixed prompt only. Raises on any problem."""
    body = json.dumps({"model": MODEL, "prompt": PROMPT, "stream": False,
                       "images": [base64.b64encode(Path(png).read_bytes()).decode()]}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    caption = data.get("response")
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError(f"empty or missing 'response' in Ollama reply: {str(data)[:300]}")
    return caption.strip()


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: caption_pages.py DIR STORY_ID")
    d, story = Path(sys.argv[1]), sys.argv[2]
    src = d / f"{story}_pages.json"
    if not src.exists():
        fail(f"{src} not found (run tools/render_pages.py {story} --out {d} first)")
    pages = json.loads(src.read_text())
    out = []
    for p in pages:
        last = None
        for attempt in (1, 2):  # one retry, then stop
            try:
                caption = ask(p["png"])
                break
            except Exception as e:  # noqa: BLE001 - reported loudly below
                last = e
                print(f"page {p['page']}: attempt {attempt} failed: {e}", file=sys.stderr)
        else:
            fail(f"page {p['page']} ({p['png']}) could not be captioned after a retry: {last}")
        out.append({"page": p["page"], "text": p["text"], "caption": caption})
        print(f"page {p['page']:02d}: {caption}", flush=True)
    dest = d / f"{story}_captions.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"OK: {len(out)} captions written to {dest}")


if __name__ == "__main__":
    main()
