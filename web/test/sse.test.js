import assert from "node:assert/strict";
import { test } from "node:test";

import { createParser } from "../src/sse.js";

test("parses events, skips comments and keeps the last id", () => {
  const feed = createParser();
  const events = feed('id: 7\nevent: status\ndata: {"text":"Checking"}\n\n: keep-alive\n\nevent: final\ndata: {}\n\n');
  assert.deepEqual(events, [
    { id: "7", event: "status", data: '{"text":"Checking"}' },
    { id: "7", event: "final", data: "{}" },
  ]);
});

test("events split across chunks arrive once complete", () => {
  const feed = createParser();
  assert.deepEqual(feed("id: 1\nevent: fin"), []);
  assert.deepEqual(feed('al\ndata: {"a"'), []);
  assert.deepEqual(feed(":1}\r\n\r\n"), [{ id: "1", event: "final", data: '{"a":1}' }]);
});

test("multi-line data is joined and unnamed events default to message", () => {
  assert.deepEqual(createParser()("data: one\ndata: two\n\n"), [{ id: null, event: "message", data: "one\ntwo" }]);
});
