import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const componentPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/components/ui/ActionDock.tsx");

test("action dock notification panel can clear accumulated notifications", async () => {
  const source = await readFile(componentPath, "utf8");

  assert.match(source, /const \[notificationDismissed, setNotificationDismissed\] = useState\(false\)/);
  assert.match(source, /const visibleNotificationActive = notificationActive && !notificationDismissed/);
  assert.match(source, /if \(!notificationActive\) \{[\s\S]*?setNotificationDismissed\(false\)/);
  assert.match(source, /notificationResetKey = null/);
  assert.match(source, /if \(notificationActive\) \{[\s\S]*?setNotificationDismissed\(false\)/);
  assert.match(source, /\}, \[notificationActive, notificationResetKey\]\)/);
  assert.match(source, /isNotificationPanel && visibleNotificationActive/);
  assert.match(source, /onClick=\{\(\) => setNotificationDismissed\(true\)\}/);
  assert.match(source, />\s*지우기\s*</);
  assert.match(source, /title="누적 알림 지우기"/);
  assert.match(source, /isNotificationPanel && notificationDismissed[\s\S]*?알림 없음/);
  assert.match(source, /iconClass\(visibleNotificationActive, openPanel === "notification", "amber"\)/);
  assert.match(source, /\{visibleNotificationActive && <span/);
});
