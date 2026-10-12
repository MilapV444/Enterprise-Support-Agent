// Wires the chat page: anonymous sign-in, one conversation kept across reloads, the live event stream.
import { ChatClient } from "./client.js";
import { addUserMessage, initialState, reduce, render } from "./view.js";

const params = new URLSearchParams(location.search);
const tenantId = params.get("tenant") ?? "t_us";
const storageKey = `support-agent:${tenantId}:conversation`;
const conversationId = localStorage.getItem(storageKey) ?? crypto.randomUUID();
localStorage.setItem(storageKey, conversationId);

const client = new ChatClient();
const log = document.querySelector("#log");
const form = document.querySelector("#composer");
const input = form.querySelector("textarea");
let state = initialState();
const update = (next) => {
  state = next;
  render(state, log);
  log.scrollTop = log.scrollHeight;
};

await client.signInAnonymous(tenantId);
client.listen(conversationId, (event) => update(reduce(state, event))).catch((error) => {
  update({ ...state, error: `Disconnected (${error.message}). Reload to sign in again.` });
});

form.addEventListener("submit", async (submitted) => {
  submitted.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  update(addUserMessage(state, text));
  try {
    await client.send(conversationId, text);
  } catch (error) {
    update({ ...state, error: `Not sent (${error.message}).` });
  }
});
