import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const globalsPath = "frontend/finiq_GUI/apps/market-desk/src/app/globals.css";

test("download metadata-ready status uses success tone", async () => {
  const source = await readFile(downloadPagePath, "utf8");

  assert.match(source, /const metadataReady = range\.status === "unverified" && !range\.metadata_missing && range\.metadata_status !== "mismatch";/);
  assert.match(source, /const statusTone = metadataReady \? "metadataOk" : range\.status;/);
  assert.match(source, /metadataOk: "border-\[color:var\(--tv-up\)\] bg-\[var\(--tv-up-soft\)\] text-\[var\(--tv-up-text\)\]"/);
  assert.match(source, /메타데이터 확인됨/);
  assert.doesNotMatch(source, /현재 설정으로 메타데이터 작성/);
  assert.doesNotMatch(source, /handleCreateMetadata/);
});

test("download colored status surfaces use contrast text tokens", async () => {
  const source = await readFile(downloadPagePath, "utf8");
  const globals = await readFile(globalsPath, "utf8");

  for (const token of ["--tv-up-text", "--tv-down-text", "--tv-warning-text"]) {
    assert.match(globals, new RegExp(`${token}: #[0-9a-fA-F]{6};`));
  }

  assert.doesNotMatch(source, /bg-\[var\(--tv-(?:up|down|warning)-soft\)\][^"\n]*text-\[var\(--tv-(?:up|down|warning)\)\]/);
  assert.match(source, /bg-\[var\(--tv-warning-soft\)\] text-\[var\(--tv-warning-text\)\]/);
  assert.match(source, /bg-\[var\(--tv-down-soft\)\] p-3 text-\[var\(--tv-down-text\)\]/);
});
