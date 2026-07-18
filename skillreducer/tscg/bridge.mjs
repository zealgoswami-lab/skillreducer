/**
 * SkillReducer ↔ @tscg/core bridge.
 * Stdin: JSON { tools, model?, profile? }
 * Stdout: JSON CompressedResult-compatible payload
 *
 * Setup (once):
 *   cd skillreducer/tscg && npm install
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

function loadCompress() {
  const candidates = [
    join(__dirname, "node_modules", "@tscg", "core"),
    "@tscg/core",
  ];
  for (const id of candidates) {
    try {
      const mod = require(id);
      if (typeof mod.compress === "function") return mod.compress;
      if (mod.default && typeof mod.default.compress === "function") {
        return mod.default.compress;
      }
    } catch {
      /* try next */
    }
  }
  throw new Error(
    "Cannot load @tscg/core. Run: cd skillreducer/tscg && npm install"
  );
}

function readInput() {
  const raw = readFileSync(0, "utf8");
  if (!raw.trim()) {
    throw new Error("Empty stdin; expected JSON { tools, model?, profile? }");
  }
  return JSON.parse(raw);
}

const compress = loadCompress();
const input = readInput();
const tools = input.tools;
if (!Array.isArray(tools) || tools.length === 0) {
  throw new Error("'tools' must be a non-empty array");
}

const result = compress(tools, {
  model: input.model || "claude-sonnet",
  profile: input.profile || "balanced",
});

process.stdout.write(
  JSON.stringify({
    compressed: result.compressed,
    metrics: result.metrics,
    appliedPrinciples: result.appliedPrinciples || [],
  })
);
