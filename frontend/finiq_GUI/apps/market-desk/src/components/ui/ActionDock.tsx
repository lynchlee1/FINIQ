"use client"

import { useEffect, useState, type ReactNode } from "react";
import { Activity, Bell, Settings, X } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";

type DockPanel = "activity" | "notification" | "settings" | null;

type ActionDockProps = {
  activityTitle?: string;
  activityContent?: ReactNode;
  activityActive?: boolean;
  notificationTitle?: string;
  notificationContent?: ReactNode;
  notificationActive?: boolean;
  notificationResetKey?: string | number | boolean | null;
  settingsTitle?: string;
  settingsContent?: ReactNode;
  settingsActive?: boolean;
};

export function ActionDock({
  activityTitle = "실행 현황",
  activityContent,
  activityActive = false,
  notificationTitle = "알림",
  notificationContent,
  notificationActive = false,
  notificationResetKey = null,
  settingsTitle = "설정",
  settingsContent,
  settingsActive = true,
}: ActionDockProps) {
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
  }, [notificationActive, notificationResetKey]);

  const togglePanel = (panel: DockPanel) => {
    setOpenPanel((current) => current === panel ? null : panel);
  };

  const iconClass = (active: boolean, selected: boolean, tone: "blue" | "amber" | "slate") => {
    if (selected) {
      return "h-10 w-10 border-slate-300 bg-slate-100 text-slate-950 shadow-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";
    }
    if (active && tone === "blue") {
      return "relative h-10 w-10 border-blue-300 bg-blue-50 text-blue-700 shadow-sm dark:border-blue-400/60 dark:bg-blue-400/15 dark:text-blue-200";
    }
    if (active && tone === "amber") {
      return "relative h-10 w-10 border-amber-300 bg-amber-50 text-amber-700 shadow-sm dark:border-amber-500/60 dark:bg-amber-500/15 dark:text-amber-200";
    }
    return "relative h-10 w-10 border-slate-200 bg-white/90 shadow-sm dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-300";
  };

  const renderPanel = (panel: DockPanel, title: string, content: ReactNode) => {
    if (openPanel !== panel) return null;
    const isNotificationPanel = panel === "notification";
    const panelContent = isNotificationPanel && notificationDismissed
      ? <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
      : content;
    return (
      <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto shadow-2xl md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)] dark:border-slate-800 dark:bg-slate-900">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="dark:text-white">{title}</CardTitle>
            <div className="flex items-center gap-2">
              {isNotificationPanel && visibleNotificationActive && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setNotificationDismissed(true)}
                  className="h-8 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                  title="누적 알림 지우기"
                >
                  지우기
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setOpenPanel(null)}
                className="h-8 w-8 dark:hover:bg-slate-800"
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
    <div className="action-dock-root relative z-40 md:sticky md:inset-x-auto md:bottom-auto md:top-28 md:col-start-2 md:row-start-1 md:row-end-[-1] md:m-0 md:w-16 md:self-start md:justify-self-end" onClick={(event) => event.stopPropagation()}>
      <div className="flex h-14 items-center justify-center gap-2 rounded-2xl border border-slate-200/80 bg-white/85 p-2 shadow-[0_18px_45px_-34px_rgba(15,23,42,0.55)] backdrop-blur md:h-auto md:w-16 md:flex-col dark:border-slate-800 dark:bg-slate-900/85">
        <Button
          variant="outline"
          size="icon"
          onClick={() => togglePanel("activity")}
          className={iconClass(activityActive, openPanel === "activity", "blue")}
          title={openPanel === "activity" ? `${activityTitle} 닫기` : `${activityTitle} 열기`}
        >
          <Activity className="h-5 w-5" />
          {activityActive && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-blue-500 dark:bg-blue-300" />}
        </Button>

        <Button
          variant="outline"
          size="icon"
          onClick={() => togglePanel("notification")}
          className={iconClass(visibleNotificationActive, openPanel === "notification", "amber")}
          title={openPanel === "notification" ? `${notificationTitle} 닫기` : `${notificationTitle} 열기`}
        >
          <Bell className="h-5 w-5" />
          {visibleNotificationActive && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-300" />}
        </Button>

        {hasSettingsContent && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => togglePanel("settings")}
            className={iconClass(settingsActive, openPanel === "settings", "slate")}
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
