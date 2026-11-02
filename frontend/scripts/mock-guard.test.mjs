// npm test: mock mode (NEXT_PUBLIC_CI_MOCK) can't reach a production build, `next start` or demo mode.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { PHASE_DEVELOPMENT_SERVER, PHASE_EXPORT, PHASE_PRODUCTION_BUILD, PHASE_PRODUCTION_SERVER } from "next/constants.js";
import { assertNoMock } from "../next.config.ts";

test("production build, next start and export refuse mock mode", () => {
  for (const phase of [PHASE_PRODUCTION_BUILD, PHASE_PRODUCTION_SERVER, PHASE_EXPORT]) {
    for (const v of ["1", "0", "true"]) assert.throws(() => assertNoMock(phase, { NEXT_PUBLIC_CI_MOCK: v }), /local `next dev` only/);
    assert.doesNotThrow(() => assertNoMock(phase, {}));
  }
});

test("demo mode refuses mock mode, even under next dev", () => {
  assert.throws(() => assertNoMock(PHASE_DEVELOPMENT_SERVER, { NEXT_PUBLIC_CI_MOCK: "1", CI_MODE: "demo" }), /demo mode/);
  assert.doesNotThrow(() => assertNoMock(PHASE_DEVELOPMENT_SERVER, { CI_MODE: "demo" }));
});

test("local next dev may use mock mode", () => {
  assert.doesNotThrow(() => assertNoMock(PHASE_DEVELOPMENT_SERVER, { NEXT_PUBLIC_CI_MOCK: "1" }));
});

test("mock code is gated on NODE_ENV development and on a live API", () => {
  const src = readFileSync(new URL("../src/lib/mock.ts", import.meta.url), "utf8");
  assert.match(src, /process\.env\.NODE_ENV === "development"/);
  assert.match(src, /mode === "live"/);
});

test("no env file in frontend/ turns mock mode on", () => {
  for (const f of [".env", ".env.production", ".env.local", ".env.production.local"]) {
    let text = "";
    try { text = readFileSync(new URL(`../${f}`, import.meta.url), "utf8"); } catch { continue; }
    assert.doesNotMatch(text, /^\s*NEXT_PUBLIC_CI_MOCK\s*=\s*\S/m, `${f} sets NEXT_PUBLIC_CI_MOCK`);
  }
});
