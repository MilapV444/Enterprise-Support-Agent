import { expect, test } from "vitest";

import { ChatClient, HttpError } from "../lib/chat-client.ts";
import { initialState, reduce } from "../lib/reduce.ts";
import { money, proposalOf, statusLabel, teamLabel, ticketPath, ticketsPath } from "../lib/tickets.ts";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const quick = { sleep: async () => {} };
const PROPOSAL = {
  kind: "ticket_proposal", title: "Raise ticket TKT-00007?", ticket_id: "TKT-00007", status: "proposed",
  category: "refund", subject: "Refund request: inv-demo-1", invoice_id: "inv-demo-1", amount_cents: 50000,
  currency: "USD", queue: "queue_billing", created_at: "2026-11-17T10:00:00+00:00",
  actions: [{ type: "confirm_ticket", proposal: "TKT-00007", label: "Raise ticket" }],
};

test("amounts, statuses, teams and links read the way the customer expects", () => {
  expect(money(184050, "USD")).toBe("$1,840.50");
  expect(money(null, "USD")).toBeNull();
  expect(statusLabel("proposed")).toBe("Not raised yet");
  expect(statusLabel("in_review")).toBe("In review");
  expect(teamLabel("queue_billing")).toBe("Billing team");
  expect(teamLabel("queue_unknown")).toBe("Support team");
  expect(ticketsPath("t_us")).toBe("/t/t_us/tickets");
  expect(ticketPath("t_us", "TKT-00007")).toBe("/t/t_us/tickets/TKT-00007");
});

test("a proposal card names the proposal its button raises; other cards none", () => {
  expect(proposalOf(PROPOSAL as never)).toBe("TKT-00007");
  expect(proposalOf({ kind: "sign_in", actions: [{ type: "sign_in", label: "Sign in" }] })).toBeNull();
});

test("an action_card event becomes a card message the chat can render", () => {
  const state = reduce(initialState(), { event: "action_card", data: PROPOSAL, at: 1 });
  expect(state.messages).toEqual([{ role: "card", text: "Raise ticket TKT-00007?", card: PROPOSAL, at: 1 }]);
});

test("a turn's reply shows before the card it talks about", () => {
  let state = reduce(initialState(), { event: "action_card", data: { ...PROPOSAL, turn_id: "t1" }, at: 1 });
  state = reduce(state, { event: "final", data: { turn_id: "t1", text: "Use Raise ticket to confirm." }, at: 2 });
  expect(state.messages.map((m) => m.role)).toEqual(["assistant", "card"]);
  state = reduce(state, { event: "final", data: { turn_id: "t2", text: "Something else." }, at: 3 });
  expect(state.messages.map((m) => m.role)).toEqual(["assistant", "card", "assistant"]); // other turns keep order
});

test("raising a ticket keeps one Idempotency-Key across retries and posts to the proposal", async () => {
  const seen: { url: string; key: string; method: string }[] = [];
  let calls = 0;
  const client = new ChatClient({
    ...quick,
    uuid: () => "raise-1",
    fetch: (async (url: string, init: RequestInit) => {
      seen.push({ url, method: init.method!, key: (init.headers as Record<string, string>)["Idempotency-Key"] });
      calls += 1;
      return calls === 1 ? json(503, {}) : json(202, { turn_id: "t9", status: "QUEUED" });
    }) as typeof fetch,
  });
  expect(await client.confirmTicket("c 1", "TKT-00007")).toEqual({ turn_id: "t9", status: "QUEUED" });
  expect(seen).toEqual([
    { url: "/v1/conversations/c%201/tickets/TKT-00007/confirm", method: "POST", key: "raise-1" },
    { url: "/v1/conversations/c%201/tickets/TKT-00007/confirm", method: "POST", key: "raise-1" },
  ]);
});

test("a refused raise (a guest, a bad number) is not retried", async () => {
  let calls = 0;
  const client = new ChatClient({ ...quick, fetch: (async () => { calls += 1; return json(403, {}); }) as typeof fetch });
  await expect(client.confirmTicket("c1", "TKT-00007")).rejects.toBeInstanceOf(HttpError);
  expect(calls).toBe(1);
});

test("the list and one ticket come from the tickets API", async () => {
  const urls: string[] = [];
  const client = new ChatClient({
    ...quick,
    fetch: (async (url: string) => {
      urls.push(url);
      return url.endsWith("/v1/tickets") ? json(200, { tickets: [PROPOSAL] }) : json(200, { ...PROPOSAL, events: [] });
    }) as typeof fetch,
  });
  expect((await client.tickets())[0].ticket_id).toBe("TKT-00007");
  expect((await client.ticket("TKT-00007")).events).toEqual([]);
  expect(urls).toEqual(["/v1/tickets", "/v1/tickets/TKT-00007"]);
});
