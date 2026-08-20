import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const componentPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/ui/ActionDock.tsx");

test("action dock notification panel can clear accumulated notifications", async () => {
  const source = await readFile(componentPath, "utf8");

  assert.match(source, /const \[notificationDismissed, setNotificationDismissed\] = useState\(false\)/);
  assert.match(source, /const visibleNotificationActive = notificationActive && !notificationDismissed/);
  assert.match(source, /if \(!notificationActive\) \{[\s\S]*?setNotificationDismissed\(false\)/);
  assert.match(source, /notificationResetKey = null/);
  assert.match(source, /notificationDismissible = true/);
  assert.match(source, /if \(notificationActive\) \{[\s\S]*?setNotificationDismissed\(false\)/);
  assert.match(source, /\}, \[notificationActive, notificationResetKey, notificationTone\]\)/);
  assert.match(source, /isNotificationPanel && visibleNotificationActive && notificationDismissible/);
  assert.match(source, /onClick=\{\(\) => setNotificationDismissed\(true\)\}/);
  assert.match(source, />\s*지우기\s*</);
  assert.match(source, /title="누적 알림 지우기"/);
  assert.match(source, /isNotificationPanel && notificationDismissed[\s\S]*?알림 없음/);
  assert.match(source, /notificationTone = "warning"/);
  assert.match(source, /const resolveTone = \(active: boolean, tone: ActionDockNotificationTone\)/);
  assert.match(source, /return tone === "neutral" \? "warning" : tone/);
  assert.match(source, /const activityTone = resolveTone\(activityActive, "warning"\)/);
  assert.match(source, /const visibleNotificationTone = resolveTone\(visibleNotificationActive, notificationTone\)/);
  assert.match(source, /iconStyle\(visibleNotificationTone, openPanel === "notification"\)/);
  assert.match(source, /iconStyle\(activityTone, openPanel === "activity"\)/);
  assert.match(source, /tone === "error"[\s\S]*?tv-down[\s\S]*?tone === "warning"[\s\S]*?tv-warning[\s\S]*?tv-up/);
  assert.match(source, /if \(tone === "neutral"\) return undefined/);
  assert.doesNotMatch(source, /--tv-info/);
  assert.doesNotMatch(source, /bg-\[var\(--tv-muted\)\]/);
  assert.match(source, /outline: selected \? `2px solid var\(\$\{tokens\[0\]\}\)` : undefined/);
  assert.match(source, /\{activityTone !== "neutral" && <span/);
  assert.match(source, /\{visibleNotificationTone !== "neutral" && <span/);
});
