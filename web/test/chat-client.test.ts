import { expect, test } from "vitest";

import { ChatClient, HttpError, readClaims } from "../lib/chat-client.ts";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const stream = (text: string) => new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } });
const quick = { sleep: async () => {} };

test("a retried message keeps its Idempotency-Key", async () => {
  const keys: string[] = [];
  let calls = 0;
  const client = new ChatClient({
    ...quick,
    uuid: () => "key-1",
    fetch: (async (_url: string, init: RequestInit) => {
      keys.push((init.headers as Record<string, string>)["Idempotency-Key"]);
      calls += 1;
      return calls === 1 ? json(503, {}) : json(202, { turn_id: "t1", status: "QUEUED" });
    }) as typeof fetch,
  });
  expect(await client.send("c1", "hi")).toEqual({ turn_id: "t1", status: "QUEUED" });
  expect(keys).toEqual(["key-1", "key-1"]);
});

test("client errors are not retried", async () => {
  let calls = 0;
  const client = new ChatClient({ ...quick, fetch: (async () => { calls += 1; return json(422, {}); }) as typeof fetch });
  await expect(client.send("c1", "")).rejects.toBeInstanceOf(HttpError);
  expect(calls).toBe(1);
});

test("a dropped stream reconnects with Last-Event-ID and sends the Bearer token", async () => {
  const seen: unknown[] = [];
  const requests: Record<string, string>[] = [];
  const controller = new AbortController();
  const replies = [
    stream('id: 4\nevent: status\ndata: {"text":"Checking"}\n\n'),
    stream('id: 5\nevent: final\ndata: {"text":"Done"}\n\n'),
  ];
  const client = new ChatClient({
    ...quick,
    fetch: (async (_url: string, init: RequestInit) => {
      requests.push(init.headers as Record<string, string>);
      if (!replies.length) controller.abort();
      return replies.shift() ?? stream("");
    }) as typeof fetch,
  });
  client.token = "tok";
  await client.listen("c1", (event) => seen.push([event.id, event.event, event.data.text]), { signal: controller.signal });
  expect(seen).toEqual([["4", "status", "Checking"], ["5", "final", "Done"]]);
  expect(requests[0]["Last-Event-ID"]).toBeUndefined();
  expect(requests[1]["Last-Event-ID"]).toBe("4");
  expect(requests.every((headers) => headers.Authorization === "Bearer tok")).toBe(true);
});

test("a refused stream stops instead of retrying forever", async () => {
  const client = new ChatClient({ ...quick, fetch: (async () => json(403, { detail: "no" })) as typeof fetch });
  await expect(client.listen("c1", () => {})).rejects.toMatchObject({ status: 403 });
});

test("the one-time code steps up the current session and the trace is fetched per turn", async () => {
  const seen: [string, string | undefined, string | undefined][] = [];
  const client = new ChatClient({
    fetch: (async (url: string, init: RequestInit) => {
      const headers = init.headers as Record<string, string>;
      seen.push([`${init.method} ${url}`, headers.Authorization, init.body as string | undefined]);
      return url.includes("verify") ? json(200, { access_token: "t1" }) : json(200, { agents: [] });
    }) as typeof fetch,
  });
  client.token = "t0";
  await client.verifyOtp("t_us", "ch-1", "123456");
  await client.trace("c 1", "turn/1");
  expect(seen[0][1]).toBe("Bearer t0"); // the anonymous session is stepped up, not replaced
  expect(seen[1]).toEqual(["GET /v1/conversations/c%201/turns/turn%2F1/trace", "Bearer t1", undefined]);
});

test("claims are read for display and a malformed token reads as none", () => {
  const body = btoa(JSON.stringify({ sub: "anon:1", tid: "t_us", tier: "T1_VERIFIED", exp: 9 })).replace(/=+$/, "");
  expect(readClaims(`h.${body}.s`)?.tier).toBe("T1_VERIFIED");
  expect(readClaims("not-a-token")).toBeNull();
  expect(readClaims(null)).toBeNull();
});
