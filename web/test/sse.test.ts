import { expect, test } from "vitest";

import { createParser } from "../lib/sse.ts";

test("parses events, skips comments and keeps the last id", () => {
  const feed = createParser();
  const events = feed('id: 7\nevent: status\ndata: {"text":"Checking"}\n\n: keep-alive\n\nevent: final\ndata: {}\n\n');
  expect(events).toEqual([
    { id: "7", event: "status", data: '{"text":"Checking"}' },
    { id: "7", event: "final", data: "{}" },
  ]);
});

test("events split across chunks arrive once complete", () => {
  const feed = createParser();
  expect(feed("id: 1\nevent: fin")).toEqual([]);
  expect(feed('al\ndata: {"a"')).toEqual([]);
  expect(feed(":1}\r\n\r\n")).toEqual([{ id: "1", event: "final", data: '{"a":1}' }]);
});

test("multi-line data is joined and unnamed events default to message", () => {
  expect(createParser()("data: one\ndata: two\n\n")).toEqual([{ id: null, event: "message", data: "one\ntwo" }]);
});
