"use client"

import { useState, type ReactNode } from "react";
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
  settingsTitle = "설정",
  settingsContent,
  settingsActive = true,
}: ActionDockProps) {
  const [openPanel, setOpenPanel] = useState<DockPanel>(null);

  const togglePanel = (panel: DockPanel) => {
    setOpenPanel((current) => current === panel ? null : panel);
  };

  const iconClass = (active: boolean, selected: boolean, tone: "blue" | "amber" | "slate") => {
    if (selected) {
      return "h-10 w-10 border-slate-400 bg-slate-100 text-slate-900 shadow-sm dark:border-slate-500 dark:bg-[#21262d] dark:text-slate-100";
    }
    if (active && tone === "blue") {
      return "relative h-10 w-10 border-blue-300 bg-blue-50 text-blue-700 shadow-sm dark:border-blue-500/60 dark:bg-blue-500/15 dark:text-blue-200";
    }
    if (active && tone === "amber") {
      return "relative h-10 w-10 border-amber-300 bg-amber-50 text-amber-700 shadow-sm dark:border-amber-500/60 dark:bg-amber-500/15 dark:text-amber-200";
    }
    return "relative h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300";
  };

  const renderPanel = (panel: DockPanel, title: string, content: ReactNode) => {
    if (openPanel !== panel) return null;
    return (
      <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="dark:text-white">{title}</CardTitle>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setOpenPanel(null)}
              className="h-8 w-8 dark:hover:bg-[#21262d]"
              title={`${title} 닫기`}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className={panel === "settings" ? "action-dock-settings-panel space-y-4" : "space-y-4"}>{content}</CardContent>
      </Card>
    );
  };

  return (
    <div className="absolute left-full top-0 z-40 ml-2" onClick={(event) => event.stopPropagation()}>
      <div className="flex w-16 flex-col items-center gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-lg dark:border-[#30363d] dark:bg-[#161b22]">
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
          className={iconClass(notificationActive, openPanel === "notification", "amber")}
          title={openPanel === "notification" ? `${notificationTitle} 닫기` : `${notificationTitle} 열기`}
        >
          <Bell className="h-5 w-5" />
          {notificationActive && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-300" />}
        </Button>

        <Button
          variant="outline"
          size="icon"
          onClick={() => togglePanel("settings")}
          className={iconClass(settingsActive, openPanel === "settings", "slate")}
          title={openPanel === "settings" ? `${settingsTitle} 닫기` : `${settingsTitle} 열기`}
        >
          <Settings className="h-5 w-5" />
        </Button>
      </div>

      {renderPanel("activity", activityTitle, activityContent)}
      {renderPanel("notification", notificationTitle, notificationContent)}
      {renderPanel("settings", settingsTitle, settingsContent)}
    </div>
  );
}
