// API client for the web chat: sign-in, idempotent turn submission and the resumable event stream.
// The stream is read with fetch (not EventSource) because it must carry the Bearer token.
import { createParser } from "./sse.js";

export class HttpError extends Error {
  constructor(status, detail) {
    super(`HTTP ${status}: ${detail}`);
    this.status = status;
  }
}

export class ChatClient {
  constructor({
    baseUrl = "",
    fetch = globalThis.fetch.bind(globalThis),
    uuid = () => globalThis.crypto.randomUUID(),
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  } = {}) {
    Object.assign(this, { baseUrl, fetch, uuid, sleep, token: null, lastEventId: null });
  }

  async signInAnonymous(tenantId) {
    const reply = await this.#post("/v1/identity/anonymous", { tenant_id: tenantId });
    this.token = reply.access_token;
    return reply;
  }

  // One Idempotency-Key for every retry of the same message, so the server creates one turn.
  async send(conversationId, content, { attempts = 3 } = {}) {
    const key = this.uuid();
    for (let attempt = 1; ; attempt += 1) {
      try {
        return await this.#post(`/v1/conversations/${encodeURIComponent(conversationId)}/turns`,
          { content }, { "Idempotency-Key": key });
      } catch (error) {
        const retryable = !(error instanceof HttpError) || error.status >= 500;
        if (!retryable || attempt >= attempts) throw error;
        await this.sleep(250 * 2 ** attempt);
      }
    }
  }

  // Calls onEvent({id, event, data}) for every event; when the stream drops it reconnects with Last-Event-ID
  // so missed events are replayed. Stops when `signal` aborts or the server refuses (4xx).
  async listen(conversationId, onEvent, { signal, retryMs = 1000 } = {}) {
    const url = `${this.baseUrl}/v1/conversations/${encodeURIComponent(conversationId)}/events`;
    while (!signal?.aborted) {
      try {
        const headers = { ...this.#auth() };
        if (this.lastEventId) headers["Last-Event-ID"] = this.lastEventId;
        const reply = await this.fetch(url, { headers, signal });
        if (!reply.ok) throw new HttpError(reply.status, await reply.text());
        const feed = createParser();
        const decoder = new TextDecoder();
        const reader = reply.body.getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          for (const event of feed(decoder.decode(value, { stream: true }))) {
            if (event.id) this.lastEventId = event.id;
            onEvent({ ...event, data: JSON.parse(event.data) });
          }
        }
      } catch (error) {
        if (signal?.aborted) return;
        if (error instanceof HttpError && error.status < 500) throw error;
      }
      await this.sleep(retryMs);
    }
  }

  #auth() {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  async #post(path, body, headers = {}) {
    const reply = await this.fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.#auth(), ...headers },
      body: JSON.stringify(body),
    });
    if (!reply.ok) throw new HttpError(reply.status, await reply.text());
    return reply.json();
  }
}
