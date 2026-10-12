// End-to-end smoke run of the web client against a live API (used by tests/web):
//   node smoke.mjs http://127.0.0.1:8000 t_us
// Signs in anonymously, opens the stream, sends one message and prints every view state as one JSON line
// until a reply arrives (or 10 s pass).
import { ChatClient } from "./src/client.js";
import { addUserMessage, initialState, reduce } from "./src/view.js";

const [baseUrl, tenantId] = process.argv.slice(2);
const client = new ChatClient({ baseUrl });
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 10_000);
let state = initialState();
const show = (next) => {
  state = next;
  console.log(JSON.stringify({ status: state.status, messages: state.messages }));
};

await client.signInAnonymous(tenantId);
const conversationId = crypto.randomUUID();
const listening = client.listen(conversationId, (event) => {
  show(reduce(state, event));
  if (event.event === "final") controller.abort();
}, { signal: controller.signal, retryMs: 100 });
await new Promise((resolve) => setTimeout(resolve, 300)); // let the stream connect first
show(addUserMessage(state, "My invoice is wrong"));
await client.send(conversationId, "My invoice is wrong");
await listening;
clearTimeout(timeout);
