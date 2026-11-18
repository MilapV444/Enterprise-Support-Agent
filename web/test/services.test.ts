import { expect, test } from "vitest";

import { ChatClient, HttpError } from "../lib/chat-client.ts";
import { activityLabel, ago, lastAction, offerOf, servicesPath, statusLabel, tone } from "../lib/services.ts";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const quick = { sleep: async () => {} };
const OFFER = {
  kind: "service_action_proposal", title: "Stop payments-api-01?", action_id: "ACT-00003", action: "stop",
  service: "payments-api-01", service_kind: "server", region: "eu-central-1", status: "running",
  actions: [{ type: "confirm_action", proposal: "ACT-00003", label: "Stop server" }],
} as const;
const ACTIVITY = [
  { action_id: "ACT-00004", service: "checkout-worker", action: "scale", replicas: 4, conversation_id: "c1", at: "2026-11-17T10:05:00Z" },
  { action_id: "ACT-00003", service: "payments-api-01", action: "stop", replicas: null, conversation_id: "c1", at: "2026-11-17T10:00:00Z" },
  { action_id: "ACT-00001", service: "payments-api-01", action: "start", replicas: null, conversation_id: "c0", at: "2026-11-16T09:00:00Z" },
] as const;

test("statuses read as running, in progress or stopped", () => {
  expect([tone("running"), tone("stopping"), tone("scaling"), tone("stopped")]).toEqual(["good", "busy", "busy", "idle"]);
  expect(statusLabel("restarting")).toBe("Restarting");
  expect(servicesPath("t_us")).toBe("/t/t_us/services");
});

test("the activity names what was done, and each service shows only its latest change", () => {
  expect(activityLabel(ACTIVITY[0] as never)).toBe("Scaled checkout-worker to 4 replicas");
  expect(activityLabel(ACTIVITY[1] as never)).toBe("Stopped payments-api-01");
  expect(lastAction(ACTIVITY as never)["payments-api-01"].action_id).toBe("ACT-00003");
  const at = Date.parse("2026-11-17T10:05:00Z");
  expect([ago("2026-11-17T10:05:00Z", at), ago("2026-11-17T10:00:00Z", at)]).toEqual(["just now", "5 min ago"]);
});

test("an offer card names the offer its button carries out; other cards none", () => {
  expect(offerOf(OFFER as never)).toBe("ACT-00003");
  expect(offerOf({ kind: "service", title: "payments-api-01 is stopping" })).toBeNull();
});

test("confirming an action posts once per click with one key across retries, and lists the services", async () => {
  const calls: { url: string; key: string | null }[] = [];
  let failures = 1;
  const client = new ChatClient({
    baseUrl: "http://api.test", ...quick,
    fetch: async (url, init) => {
      calls.push({ url: String(url), key: new Headers(init?.headers).get("Idempotency-Key") });
      if (String(url).endsWith("/v1/services")) return json(200, { services: [], activity: [] });
      if (failures-- > 0) return json(503, {});
      return json(202, { turn_id: "t1", status: "QUEUED" });
    },
  });
  await client.confirmAction("c1", "ACT-00003");
  expect(calls.map((c) => c.url)).toEqual([
    "http://api.test/v1/conversations/c1/actions/ACT-00003/confirm",
    "http://api.test/v1/conversations/c1/actions/ACT-00003/confirm"]);
  expect(calls[0].key).toBe(calls[1].key);
  expect(await client.services()).toEqual({ services: [], activity: [] });
  const refused = new ChatClient({ baseUrl: "http://api.test", ...quick, fetch: async () => json(422, {}) });
  await expect(refused.confirmAction("c1", "TKT-1")).rejects.toBeInstanceOf(HttpError);
});
