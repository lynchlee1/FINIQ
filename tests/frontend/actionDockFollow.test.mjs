import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const hookPath = path.resolve(
  "frontend/finiq_GUI/packages/web-app/src/components/ui/useActionDockFollow.ts",
);

test("action dock spring clamps every rendered position to its host", async () => {
  const source = await readFile(hookPath, "utf8");

  assert.match(source, /let maxTravel = 0;/);
  assert.match(
    source,
    /const clampCurrent = \(\) => \{\s*const boundedCurrent = Math\.min\(maxTravel, Math\.max\(0, current\)\);\s*if \(boundedCurrent === current\) return false;\s*current = boundedCurrent;\s*velocity = 0;\s*return true;/,
  );
  assert.match(source, /current \+= velocity;\s*clampCurrent\(\);/);
  assert.match(source, /target = Math\.min[\s\S]*?if \(clampCurrent\(\)\) render\(\);/);
  assert.match(
    source,
    /maxTravel = Math\.max\(0, host\.scrollHeight - dock\.offsetHeight\);/,
  );
});

test("action dock recomputes bounds when its host or own size changes", async () => {
  const source = await readFile(hookPath, "utf8");

  assert.match(source, /const resizeObserver = new ResizeObserver\(updateTarget\);/);
  assert.match(source, /resizeObserver\.observe\(host\);/);
  assert.match(source, /resizeObserver\.observe\(dock\);/);
  assert.match(source, /resizeObserver\.disconnect\(\);/);
});
