"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button, Input } from "@finiq/ui";
import { apiPost } from "@/api/client";
import { useSettingsStore } from "@/store/useSettingsStore";

type RouteCheck = {
  index: number;
  label: string;
  proxy_url: string | null;
  status: "ready" | "error";
  public_ip: string | null;
  unique: boolean | null;
};

type RouteCheckResult = {
  ready: boolean;
  route_count: number;
  unique_ip_count: number;
  routes: RouteCheck[];
};

export function KindNetworkRouteSettings() {
  const kindProxyUrls = useSettingsStore((state) => state.kind_proxy_urls);
  const parallelWorkerCount = useSettingsStore((state) => state.parallel_worker_count);
  const saveSetting = useSettingsStore((state) => state.saveSetting);
  const [routes, setRoutes] = useState<string[]>(kindProxyUrls);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [checkResult, setCheckResult] = useState<RouteCheckResult | null>(null);
  const routeVersionRef = useRef(0);

  useEffect(() => {
    routeVersionRef.current += 1;
    setRoutes(kindProxyUrls);
  }, [kindProxyUrls]);

  const changeRoutes = (nextRoutes: string[]) => {
    routeVersionRef.current += 1;
    setRoutes(nextRoutes);
    setCheckResult(null);
    setMessage("");
  };

  const normalizedRoutes = () => routes.map((route) => route.trim());
  const maxProxyRoutes = parallelWorkerCount - 1;
  const hasChanges = JSON.stringify(normalizedRoutes()) !== JSON.stringify(kindProxyUrls);
  const configuredRouteCount = routes.length + 1;
  const readyRouteCount = checkResult?.routes.filter(
    (route) => route.status === "ready" && route.unique === true,
  ).length ?? 0;
  const summaryLabel = checking
    ? `${configuredRouteCount}개 경로 검사 중`
    : checkResult
      ? `${readyRouteCount}/${checkResult.route_count} 정상`
      : `${configuredRouteCount}개 경로, 검사 필요`;

  const validateRoutes = () => {
    if (routes.some((route) => !route.trim())) {
      setMessage("모든 경로에 로컬 HTTP 프록시 주소를 입력하세요.");
      return false;
    }
    return true;
  };

  const checkRoutes = async () => {
    if (!validateRoutes()) return;
    const routeVersion = routeVersionRef.current;
    setChecking(true);
    setMessage("");
    try {
      const result = await apiPost<RouteCheckResult>("/api/kind-network-routes/check", {
        kind_proxy_urls: normalizedRoutes(),
      });
      if (routeVersion !== routeVersionRef.current) return;
      setCheckResult(result);
      setMessage(result.ready ? "" : "연결 실패 또는 중복 IP가 있는 경로를 확인하세요.");
    } catch (error) {
      if (routeVersion !== routeVersionRef.current) return;
      setCheckResult(null);
      setMessage(error instanceof Error ? error.message : "연결 검사에 실패했습니다.");
    } finally {
      setChecking(false);
    }
  };

  const saveRoutes = async () => {
    if (!validateRoutes()) return;
    setSaving(true);
    setMessage("");
    const nextRoutes = normalizedRoutes();
    const saved = await saveSetting("kind_proxy_urls", nextRoutes);
    if (saved) {
      setRoutes(nextRoutes);
      setMessage("KIND 네트워크 경로 설정을 저장했습니다.");
    } else {
      setMessage("KIND 네트워크 경로 설정을 저장하지 못했습니다.");
    }
    setSaving(false);
  };

  const routeIpState = (index: number) => {
    const result = checkResult?.routes[index];
    if (!result) return { label: "공인 IP: 검사 필요", className: "text-[var(--tv-muted)]" };
    if (result.status === "error") return { label: "공인 IP: 연결 실패", className: "text-red-600 dark:text-red-400" };
    if (result.unique === false) return { label: `공인 IP: 중복(${result.public_ip})`, className: "text-amber-700 dark:text-amber-300" };
    return { label: `공인 IP: 정상(${result.public_ip})`, className: "text-emerald-700 dark:text-emerald-300" };
  };

  return (
    <section className="space-y-2.5" aria-labelledby="kind-network-routes-title">
      <div className="flex items-center justify-between gap-3 border-b border-[color:var(--tv-border)] pb-2">
        <p id="kind-network-routes-title" className="text-caption font-semibold tracking-wide text-slate-500 dark:text-slate-400">
          KIND 네트워크 경로
        </p>
        <span
          role="status"
          aria-live="polite"
          className={`shrink-0 text-caption font-medium ${checkResult?.ready ? "text-emerald-700 dark:text-emerald-300" : "text-[var(--tv-muted)]"}`}
        >
          {summaryLabel}
        </span>
      </div>
      <p className="text-caption text-[var(--tv-muted)]">
        직접 연결과 localhost HTTP 프록시를 합쳐 CPU 개수({parallelWorkerCount}개)만큼 경로를 사용할 수 있습니다.
      </p>
      <div className="divide-y divide-[color:var(--tv-border)]">
        {["직접 연결", ...routes].map((route, index) => {
          const ipState = routeIpState(index);
          return (
            <div key={index === 0 ? "direct" : `proxy-${index}`} className="flex min-w-0 items-center gap-2 py-2">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-start gap-2">
                  <span className="w-4 shrink-0 pt-2 text-right font-mono text-caption text-[var(--tv-muted)]">{index}</span>
                  <div className="min-w-0 flex-1">
                    {index === 0 ? (
                      <p className="flex h-8 items-center text-body font-medium text-[var(--tv-text)]">직접 연결</p>
                    ) : (
                      <Input
                        aria-label={`경로 ${index} 프록시 주소`}
                        value={route}
                        disabled={checking || saving}
                        placeholder="http://127.0.0.1:25001"
                        onChange={(event) => changeRoutes(routes.map((value, routeIndex) => routeIndex === index - 1 ? event.target.value : value))}
                        className="h-8 min-w-0 font-mono text-body"
                      />
                    )}
                    <p className={`mt-0.5 font-mono text-caption ${ipState.className}`}>
                      {ipState.label}
                    </p>
                  </div>
                </div>
              </div>
              {index > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  aria-label={`경로 ${index} 삭제`}
                  disabled={checking || saving}
                  onClick={() => changeRoutes(routes.filter((_, routeIndex) => routeIndex !== index - 1))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              ) : <span className="h-8 w-8 shrink-0" aria-hidden="true" />}
            </div>
          );
        })}
      </div>
      <div className="flex justify-start">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8"
          disabled={routes.length >= maxProxyRoutes || checking || saving}
          onClick={() => changeRoutes([...routes, ""])}
        >
          <Plus className="mr-1.5 h-3.5 w-3.5" />경로 추가
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2 border-t border-[color:var(--tv-border)] pt-2.5">
        <Button type="button" variant="outline" size="sm" disabled={checking || saving} onClick={() => void checkRoutes()}>
          {checking ? "검사 중" : "연결 검사"}
        </Button>
        <Button type="button" size="sm" disabled={!hasChanges || checking || saving} onClick={() => void saveRoutes()}>
          {saving ? "저장 중" : "변경사항 저장"}
        </Button>
      </div>
      {message ? (
        <p role="status" className="text-caption text-[var(--tv-muted)]">{message}</p>
      ) : null}
    </section>
  );
}
