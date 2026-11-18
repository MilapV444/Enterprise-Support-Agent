// The History drop-down in the rail, with /v1 stubbed: it lists past conversations by their first message,
// reopens one with its transcript (Last-Event-ID 0), and stays open until it is clicked again.
import { expect, test, type Page } from "@playwright/test";

const token = `h.${Buffer.from(JSON.stringify({ sub: "sam@acme.test", tid: "t_us", tier: "T1_VERIFIED", exp: 4e9 }))
  .toString("base64url")}.s`;
const PAST = [
  { id: "past-1", title: "How do refunds work for annual plans?", updated_at: "2026-11-17T10:00:00+00:00" },
  { id: "past-2", title: "Reset my password", updated_at: "2026-11-16T10:00:00+00:00" },
];
const TRANSCRIPT = [
  ["status", { code: "stream_expired" }],
  ["final", { history: true, role: "user", text: "How do refunds work for annual plans?" }],
  ["final", { history: true, role: "assistant", text: "Annual plans are refunded pro rata." }],
].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");

async function stub(page: Page, resumed: string[]) {
  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = request.url();
    if (url.endsWith("/identity/anonymous")) return route.fulfill({ json: { access_token: token } });
    if (url.endsWith("/events")) {
      const replay = request.headers()["last-event-id"] === "0" && url.includes("/past-1/");
      if (replay) resumed.push("past-1");
      return route.fulfill({ body: replay ? TRANSCRIPT : "", contentType: "text/event-stream" });
    }
    if (url.endsWith("/v1/conversations")) return route.fulfill({ json: { conversations: PAST } });
    return route.fulfill({ status: 202, json: { turn_id: "turn-2", status: "QUEUED" } });
  });
}

test("History lists past conversations, reopens one, and stays open until clicked again", async ({ page }) => {
  const resumed: string[] = [];
  await page.setViewportSize({ width: 1440, height: 900 });
  await stub(page, resumed);
  await page.goto("/");

  const toggle = page.getByRole("button", { name: "History" });
  const list = page.getByRole("list", { name: "Past conversations" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(list).toHaveCount(0);
  await toggle.click();
  await expect(list.getByRole("button")).toHaveText(["How do refunds work for annual plans?", "Reset my password"]);

  await list.getByRole("button", { name: "How do refunds work" }).click();
  await expect(page.getByText("Annual plans are refunded pro rata.")).toBeVisible();
  await expect(page.locator("main").getByText("How do refunds work for annual plans?")).toBeVisible();
  await expect(list.getByRole("button", { name: "How do refunds work" })).toHaveAttribute("aria-current", "true");
  expect(resumed).toEqual(["past-1"]);
  if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/history.png` });

  await page.reload(); // still open, and the reopened chat comes back
  await expect(list.getByRole("button")).toHaveCount(2);
  await expect(page.getByText("Annual plans are refunded pro rata.")).toBeVisible();

  await toggle.click();
  await expect(list).toHaveCount(0);
});
