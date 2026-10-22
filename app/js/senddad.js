// "Send to Dad" (static website copy only, docs/away-from-home.md §1): the Home button, the full-screen prompt after a
// session, and the download of the export file Mom emails to Dad. All child-facing words are small caps (kid).
import { h } from "./ui.js";
import { offlineNow } from "./offline.js";
import { grownUp } from "./family.js";

/** Save `text` as a JSON file named `filename` through the browser's normal download. */
function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = h("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** Home line: "N new things to send" or "All sent ✓ (last sent <time>)". */
export function statusText(b = offlineNow()) {
  const n = b.unsentCount();
  if (n > 0) return `${n} new thing${n === 1 ? "" : "s"} to send`;
  const last = b.lastExport();
  return last ? `All sent ✓ (last sent ${new Date(last.at).toLocaleString()})` : "Nothing new to send yet";
}

/** The big instruction screen shown after the file was downloaded. */
function instructions(host, filename, onDone) {
  host.replaceChildren(h("div", { class: "send-dad send-dad-done" },
    h("h1", { kid: "Your file is ready!" }),
    h("p", { class: "send-dad-big", id: "send-dad-instructions", kid: `Attach this file (in your Downloads folder) to an email to ${grownUp()}.` }),
    h("p", { class: "send-dad-file", id: "send-dad-file", text: filename }),
    h("button", { class: "btn big", id: "send-dad-ok", kid: "OK", onclick: onDone })));
}

/** Build the export, download it, then show the instructions. A failure is shown loudly, never as "sent". */
function sendAndShow(host, onDone) {
  const { filename, text } = offlineNow().makeExport();
  download(filename, text);
  instructions(host, filename, onDone);
}

/** The big Home button. Re-renders the Home screen's status line after sending via `onChange` (home()). */
export function sendToDadButton(onChange = null) {
  const status = h("div", { class: "send-dad-status", id: "send-dad-status", kid: statusText() });
  const btn = h("button", { class: "btn huge send-dad-btn", id: "send-dad-btn", kid: `📨 Send to ${grownUp()}`, onclick: () => {
    const app = document.getElementById("app");
    sendAndShow(app, () => (onChange ? onChange() : location.reload()));
  } });
  return h("div", { class: "send-dad-box" }, btn, status);
}

/** Full-screen prompt after Finish / adventure; resolves when the child or a grown-up moves on. */
export function sendToDadPrompt(root) {
  return new Promise((resolve) => {
    const b = offlineNow();
    if (b.unsentCount() === 0) return resolve("nothing");
    root.replaceChildren(h("div", { class: "send-dad" },
      h("h1", { kid: `Send your adventure to ${grownUp()}!` }),
      h("p", { class: "send-dad-big", kid: statusText(b) }),
      h("button", { class: "btn huge send-dad-btn", id: "send-dad-prompt-btn", kid: `📨 Send to ${grownUp()}`, onclick: () => sendAndShow(root, () => resolve("sent")) }),
      h("button", { class: "btn small", id: "send-dad-later", kid: "Not now", onclick: () => resolve("later") })));
  });
}
