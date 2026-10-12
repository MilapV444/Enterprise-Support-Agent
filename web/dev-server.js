// Local development: serves the static files and proxies /v1 to the API, like the Vercel rewrite does.
//   API_ORIGIN=http://127.0.0.1:8000 PORT=3000 node dev-server.js
import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const api = new URL(process.env.API_ORIGIN ?? "http://127.0.0.1:8000");
const port = Number(process.env.PORT ?? 3000);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" };

http.createServer((request, response) => {
  if (request.url.startsWith("/v1/")) {
    const upstream = http.request(
      { host: api.hostname, port: api.port, path: request.url, method: request.method,
        headers: { ...request.headers, host: api.host } },
      (reply) => {
        response.writeHead(reply.statusCode, reply.headers);
        reply.pipe(response);
      });
    upstream.on("error", () => response.writeHead(502).end("API unreachable"));
    request.pipe(upstream);
    return;
  }
  const path = normalize(join(root, decodeURIComponent(new URL(request.url, "http://x").pathname)));
  const file = path.startsWith(root) && existsSync(path) && statSync(path).isFile() ? path : join(root, "index.html");
  response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(response);
}).listen(port, "127.0.0.1", () => console.log(`chat on http://127.0.0.1:${port} (API ${api.origin})`));
