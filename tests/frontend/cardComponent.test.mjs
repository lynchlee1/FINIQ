import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const cardPath = new URL("../../frontend/finiq_GUI/packages/ui/src/components/ui/card.tsx", import.meta.url);

test("card header only reserves description row when a description exists", async () => {
  const source = await readFile(cardPath, "utf8");
  const headerClass = source.match(/data-slot="card-header"[\s\S]*?className=\{cn\(\s*"([^"]+)"/)?.[1] ?? "";
  const actionClass = source.match(/data-slot="card-action"[\s\S]*?className=\{cn\(\s*"([^"]+)"/)?.[1] ?? "";

  assert.doesNotMatch(headerClass, /(?:^|\s)grid-rows-\[auto_auto\](?:\s|$)/);
  assert.match(headerClass, /has-data-\[slot=card-description\]:grid-rows-\[auto_auto\]/);
  assert.doesNotMatch(actionClass, /row-span-2/);
});
