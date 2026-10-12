import assert from "node:assert/strict";
import { test } from "node:test";

import { ChatClient, HttpError } from "../src/client.js";

const json = (status, body) => new Response(JSON.stringify(body), { status });
const stream = (text) => new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } });

test("a retried message keeps its Idempotency-Key", async () => {
  const keys = [];
  let calls = 0;
  const client = new ChatClient({
    uuid: () => "key-1",
    sleep: async () => {},
    fetch: async (url, init) => {
      keys.push(init.headers["Idempotency-Key"]);
      calls += 1;
      return calls === 1 ? json(503, {}) : json(202, { turn_id: "t1", status: "QUEUED" });
    },
  });
  assert.deepEqual(await client.send("c1", "hi"), { turn_id: "t1", status: "QUEUED" });
  assert.deepEqual(keys, ["key-1", "key-1"]);
});

test("client errors are not retried", async () => {
  let calls = 0;
  const client = new ChatClient({ sleep: async () => {}, fetch: async () => { calls += 1; return json(422, {}); } });
  await assert.rejects(client.send("c1", ""), HttpError);
  assert.equal(calls, 1);
});

test("a dropped stream reconnects with Last-Event-ID and sends the Bearer token", async () => {
  const seen = [];
  const requests = [];
  const controller = new AbortController();
  const replies = [
    stream('id: 4\nevent: status\ndata: {"text":"Checking"}\n\n'),
    stream('id: 5\nevent: final\ndata: {"text":"Done"}\n\n'),
  ];
  const client = new ChatClient({
    sleep: async () => {},
    fetch: async (url, init) => {
      requests.push(init.headers);
      if (!replies.length) controller.abort();
      return replies.shift() ?? stream("");
    },
  });
  client.token = "tok";
  await client.listen("c1", (event) => seen.push([event.id, event.event, event.data.text]),
    { signal: controller.signal });
  assert.deepEqual(seen, [["4", "status", "Checking"], ["5", "final", "Done"]]);
  assert.equal(requests[0]["Last-Event-ID"], undefined);
  assert.equal(requests[1]["Last-Event-ID"], "4");
  assert.ok(requests.every((headers) => headers.Authorization === "Bearer tok"));
});

test("a refused stream stops instead of retrying forever", async () => {
  const client = new ChatClient({ sleep: async () => {}, fetch: async () => json(403, { detail: "no" }) });
  await assert.rejects(client.listen("c1", () => {}), (error) => error.status === 403);
});
