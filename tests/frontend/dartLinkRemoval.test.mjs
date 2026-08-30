import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/dart-link/page.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const terminologyPath = "docs/design/terminology/index.md";

test("removed KIND-DART workflow is not exposed in the frontend", async () => {
  const [navigation, terminology] = await Promise.all([
    readFile(navigationPath, "utf8"),
    readFile(terminologyPath, "utf8"),
  ]);

  await assert.rejects(access(pagePath));
  assert.doesNotMatch(navigation, /href: "\/dart-link"/);
  assert.doesNotMatch(terminology, /KIND to DART|KIND-DART 연결/);
});
