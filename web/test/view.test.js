import assert from "node:assert/strict";
import { test } from "node:test";

import { addUserMessage, initialState, reduce, render } from "../src/view.js";

const run = (events, state = initialState()) => events.reduce(reduce, state);

test("status shows while the reply is held, then the checked reply replaces it", () => {
  let state = addUserMessage(initialState(), "My invoice is wrong");
  state = reduce(state, { event: "status", data: { state: "queued", text: "Message received" } });
  state = reduce(state, { event: "status", data: { text: "Checking invoice history" } });
  assert.equal(state.status, "Checking invoice history");
  assert.equal(state.messages.length, 1);
  state = reduce(state, { event: "final", data: { text: "Your invoice was corrected." } });
  assert.equal(state.status, null);
  assert.deepEqual(state.messages.at(-1), { role: "assistant", text: "Your invoice was corrected.", citations: [] });
});

test("citations attach to the reply that follows them", () => {
  const state = run([
    { event: "citation", data: { doc_id: "kb-12", title: "Refund policy" } },
    { event: "final", data: { text: "Refunds take 5 days." } },
  ]);
  assert.deepEqual(state.messages[0].citations, [{ doc_id: "kb-12", title: "Refund policy" }]);
});

test("an expired stream clears the view before the history is replayed", () => {
  const state = run([
    { event: "final", data: { text: "stale" } },
    { event: "status", data: { code: "stream_expired" } },
    { event: "final", data: { history: true, role: "user", content: "Hi" } },
  ]);
  assert.deepEqual(state.messages.map((m) => [m.role, m.text]), [["user", "Hi"]]);
});

test("errors and hand-offs end the status line", () => {
  assert.equal(run([{ event: "status", data: { text: "x" } }, { event: "error", data: {} }]).status, null);
  const handed = run([{ event: "handoff", data: { text: "Alex from support joined" } }]);
  assert.equal(handed.messages[0].text, "Alex from support joined");
});

test("unknown event types change nothing", () => {
  const state = initialState();
  assert.equal(reduce(state, { event: "token", data: {} }), state);
});

test("render sets text only, never HTML", () => {
  const created = [];
  const doc = {
    createElement: (tag) => {
      const node = { tag, children: [], appendChild(child) { this.children.push(child); } };
      created.push(node);
      return node;
    },
  };
  const root = { replaceChildren(...nodes) { this.nodes = nodes; } };
  const state = run([{ event: "final", data: { text: "<img src=x onerror=alert(1)>" } },
    { event: "status", data: { text: "Checking" } }]);
  render(state, root, doc);
  assert.deepEqual(root.nodes.map((n) => [n.className, n.textContent]),
    [["message assistant", "<img src=x onerror=alert(1)>"], ["status", "Checking"]]);
  assert.ok(created.every((node) => !("innerHTML" in node)));
});
