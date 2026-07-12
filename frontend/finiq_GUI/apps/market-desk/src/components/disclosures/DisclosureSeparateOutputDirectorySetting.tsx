"use client";

import { Checkbox, Label } from "@finiq/ui";
import { useSettingsStore } from "@/store/useSettingsStore";

export function DisclosureSeparateOutputDirectorySetting({ id }: { id: string }) {
  const { disclosure_separate_output_directory: checked, saveSetting } = useSettingsStore();

  return (
    <div className="space-y-3">
      <div className="border-b border-[color:var(--tv-border)] pb-2">
        <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">데이터 경로</p>
      </div>
      <div className="flex items-center space-x-2">
        <Checkbox
          id={id}
          checked={checked}
          onCheckedChange={(value) => saveSetting("disclosure_separate_output_directory", !!value)}
          className="border-[color:var(--tv-border)]"
        />
        <Label htmlFor={id} className="cursor-pointer dark:text-slate-300">
          저장 디렉토리 별도 설정하기
        </Label>
      </div>
    </div>
  );
}
