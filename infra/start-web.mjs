import { cp, access } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const next = path.join(root, "apps/web/.next");
const server = path.join(next, "standalone/apps/web/server.js");
await access(server);
await cp(
  path.join(next, "static"),
  path.join(next, "standalone/apps/web/.next/static"),
  { recursive: true },
);
process.env.HOSTNAME = "0.0.0.0";
await import(pathToFileURL(server).href);
