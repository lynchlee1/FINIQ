import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const componentPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/KindNetworkRouteSettings.tsx";
const htmlDownloadPath = "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx";
const automationPath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";

test("KIND network routes expose provider-neutral editing, checking, and saving", async () => {
  const component = await readFile(componentPath, "utf8");

  assert.match(component, /KIND 네트워크 경로/);
  assert.match(component, /직접 연결/);
  assert.match(component, /경로 추가/);
  assert.match(component, /연결 검사/);
  assert.match(component, /변경사항 저장/);
  assert.match(component, /검사 필요/);
  assert.match(component, /공인 IP: 정상\(\$\{result\.public_ip\}\)/);
  assert.match(component, /공인 IP: 중복\(\$\{result\.public_ip\}\)/);
  assert.match(component, /공인 IP: 연결 실패/);
  assert.doesNotMatch(component, /state\?\.label/);
  assert.match(component, /parallelWorkerCount = useSettingsStore/);
  assert.match(component, /maxProxyRoutes = parallelWorkerCount - 1/);
  assert.match(component, /CPU 개수\(\{parallelWorkerCount\}개\)만큼 경로/);
  assert.match(component, />\{index\}<\/span>/);
  assert.match(component, /h-8 items-center text-body font-medium[^>]*>직접 연결/);
  assert.match(component, /\/api\/kind-network-routes\/check/);
  assert.match(component, /saveSetting\("kind_proxy_urls"/);
  assert.match(component, /const hasChanges =/);
  assert.match(component, /disabled=\{!hasChanges \|\| checking \|\| saving\}/);
  assert.match(component, /setCheckResult\(null\)/);
  assert.match(component, /routeVersionRef\.current \+= 1/);
  assert.match(component, /routeVersion !== routeVersionRef\.current/);
  assert.match(component, /disabled=\{checking \|\| saving\}/);
  assert.match(component, /divide-y divide-\[color:var\(--tv-border\)\]/);
  assert.doesNotMatch(component, /className="w-full"[\s\S]{0,160}>\s*<Plus/);
  assert.match(component, /className="h-8 min-w-0 font-mono text-body"/);
  assert.doesNotMatch(component, /text-\[11px\]|text-xs|text-sm/);
  assert.doesNotMatch(component, /Proton|VPN 계정|WireGuard/);
});

test("KIND network routes appear only in HTML save and automation settings", async () => {
  const [htmlDownload, automation] = await Promise.all([
    readFile(htmlDownloadPath, "utf8"),
    readFile(automationPath, "utf8"),
  ]);

  assert.match(htmlDownload, /<KindNetworkRouteSettings \/>/);
  assert.match(automation, /<KindNetworkRouteSettings \/>/);
});
