"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Activity, Bell, Settings, X } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { useActionDockFollow } from "./useActionDockFollow";

type DockPanel = "activity" | "notification" | "settings" | null;

export type ActionDockNotificationTone = "neutral" | "success" | "warning" | "error";

type ActionDockProps = {
  activityTitle?: string;
  activityContent?: ReactNode;
  activityActive?: boolean;
  notificationTitle?: string;
  notificationContent?: ReactNode;
  notificationActive?: boolean;
  notificationTone?: ActionDockNotificationTone;
  notificationDismissible?: boolean;
  notificationResetKey?: string | number | boolean | null;
  settingsTitle?: string;
  settingsContent?: ReactNode;
};

export function ActionDock({
  activityTitle = "실행 현황",
  activityContent,
  activityActive = false,
  notificationTitle = "알림",
  notificationContent,
  notificationActive = false,
  notificationTone = "warning",
  notificationDismissible = true,
  notificationResetKey = null,
  settingsTitle = "설정",
  settingsContent,
}: ActionDockProps) {
  const dockRef = useActionDockFollow<HTMLDivElement>();
  const [openPanel, setOpenPanel] = useState<DockPanel>(null);
  const [notificationDismissed, setNotificationDismissed] = useState(false);
  const hasSettingsContent = settingsContent !== undefined && settingsContent !== null;
  const visibleNotificationActive = notificationActive && !notificationDismissed;

  useEffect(() => {
    if (!notificationActive) {
      setNotificationDismissed(false);
    }
  }, [notificationActive]);

  useEffect(() => {
    if (notificationActive) {
      setNotificationDismissed(false);
    }
  }, [notificationActive, notificationResetKey, notificationTone]);

  const togglePanel = (panel: DockPanel) => {
    setOpenPanel((current) => current === panel ? null : panel);
  };

  const iconClass = (active: boolean) => {
    if (active) return "relative h-10 w-10 rounded-lg";
    return "relative h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)] hover:text-[var(--tv-text)]";
  };

  const iconStyle = (active: boolean, selected: boolean, tone: ActionDockNotificationTone): CSSProperties | undefined => {
    if (!active || tone === "neutral") return undefined;
    const tokens = tone === "error"
      ? ["--tv-down", "--tv-down-soft", "--tv-down-text"]
      : tone === "warning"
        ? ["--tv-warning", "--tv-warning-soft", "--tv-warning-text"]
        : ["--tv-up", "--tv-up-soft", "--tv-up-text"];
    return {
      borderColor: `var(${tokens[0]})`,
      backgroundColor: `var(${tokens[1]})`,
      color: `var(${tokens[2]})`,
      outline: selected ? `2px solid var(${tokens[0]})` : undefined,
      outlineOffset: selected ? "1px" : undefined,
    };
  };

  const notificationDotClass = notificationTone === "error"
    ? "bg-[var(--tv-down)]"
    : notificationTone === "warning"
      ? "bg-[var(--tv-warning)]"
      : notificationTone === "success"
        ? "bg-[var(--tv-up)]"
        : "bg-[var(--tv-muted)]";

  const renderPanel = (panel: DockPanel, title: string, content: ReactNode) => {
    if (openPanel !== panel) return null;
    const isNotificationPanel = panel === "notification";
    const panelContent = isNotificationPanel && notificationDismissed
      ? <div className="text-body text-[var(--tv-muted)]">알림 없음</div>
      : content;
    return (
      <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-md md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-[var(--tv-text)]">{title}</CardTitle>
            <div className="flex items-center gap-2">
              {isNotificationPanel && visibleNotificationActive && notificationDismissible && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setNotificationDismissed(true)}
                  className="h-8 border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] hover:text-[var(--tv-accent)]"
                  title="누적 알림 지우기"
                >
                  지우기
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setOpenPanel(null)}
                className="h-8 w-8 text-[var(--tv-text)] hover:text-[var(--tv-accent)]"
                title={`${title} 닫기`}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className={panel === "settings" ? "action-dock-settings-panel space-y-4" : "space-y-4"}>{panelContent}</CardContent>
      </Card>
    );
  };

  return (
    <div ref={dockRef} className="action-dock-root relative z-40 md:inset-x-auto md:bottom-auto md:top-auto md:col-start-2 md:row-start-1 md:row-end-[-1] md:m-0 md:w-16 md:self-start md:justify-self-end" onClick={(event) => event.stopPropagation()}>
      <div className="flex h-14 items-center justify-center gap-2 rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-2 md:h-auto md:w-16 md:flex-col">
        <Button
          variant="outline"
          size="icon"
          onClick={() => togglePanel("activity")}
          aria-pressed={openPanel === "activity"}
          className={iconClass(false)}
          title={openPanel === "activity" ? `${activityTitle} 닫기` : `${activityTitle} 열기`}
        >
          <Activity className="h-5 w-5" />
          {activityActive && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[var(--tv-muted)]" />}
        </Button>

        <Button
          variant="outline"
          size="icon"
          onClick={() => togglePanel("notification")}
          aria-pressed={openPanel === "notification"}
          className={iconClass(visibleNotificationActive && notificationTone !== "neutral")}
          style={iconStyle(visibleNotificationActive, openPanel === "notification", notificationTone)}
          title={openPanel === "notification" ? `${notificationTitle} 닫기` : `${notificationTitle} 열기`}
        >
          <Bell className="h-5 w-5" />
          {visibleNotificationActive && <span className={`absolute right-2 top-2 h-2 w-2 rounded-full ${notificationDotClass}`} />}
        </Button>

        {hasSettingsContent && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => togglePanel("settings")}
            aria-pressed={openPanel === "settings"}
            className={iconClass(false)}
            title={openPanel === "settings" ? `${settingsTitle} 닫기` : `${settingsTitle} 열기`}
          >
            <Settings className="h-5 w-5" />
          </Button>
        )}
      </div>

      {renderPanel("activity", activityTitle, activityContent)}
      {renderPanel("notification", notificationTitle, notificationContent)}
      {hasSettingsContent && renderPanel("settings", settingsTitle, settingsContent)}
    </div>
  );
}
