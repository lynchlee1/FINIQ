"use client";

import { Checkbox, Label } from "@finiq/ui";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useSettingsStore } from "@/store/useSettingsStore";
import type { DataPathField } from "./DataPathCard";

type WorkflowPathSettingsProps = {
  id: string;
  fields: DataPathField[];
  onError: (message: string) => void;
};

/**
 * 입력·출력 경로를 모두 우측 설정 패널에서 담당한다. 본문에는 경로 입력을 두지 않는다.
 * 본문 카드에 조건부 행을 두면 설정 상태에 따라 카드 높이가 변해 모드 전환 행의 위치가 흔들린다.
 */
export function WorkflowPathSettings({ id, fields, onError }: WorkflowPathSettingsProps) {
  const {
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    saveSetting,
  } = useSettingsStore();
  const inputFields = fields.filter((field) => !field.separateOutputOnly);
  const outputFields = fields.filter((field) => field.separateOutputOnly);

  return (
    <div className="space-y-3">
      <div className="border-b border-[color:var(--tv-border)] pb-2">
        <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">데이터 경로</p>
      </div>
      {inputFields.map((field) => (
        <WorkflowPathField key={field.id} field={field} onError={onError} />
      ))}
      {outputFields.length > 0 && (
        <div className="flex items-center space-x-2">
          <Checkbox
            id={id}
            checked={useSeparateOutputDirectory}
            onCheckedChange={(value) => saveSetting("disclosure_separate_output_directory", !!value)}
            className="border-[color:var(--tv-border)]"
          />
          <Label htmlFor={id} className="cursor-pointer dark:text-slate-300">
            저장 디렉토리 별도 설정하기
          </Label>
        </div>
      )}
      {useSeparateOutputDirectory && outputFields.map((field) => (
        <WorkflowPathField key={field.id} field={field} onError={onError} />
      ))}
    </div>
  );
}

function WorkflowPathField({
  field,
  onError,
}: {
  field: DataPathField;
  onError: (message: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label className="dark:text-slate-300">{field.label}</Label>
      <PathPickerInput
        mode={field.mode || "folder"}
        value={field.value}
        onChange={field.onChange}
        placeholder={field.placeholder || `${field.label}를 선택하세요`}
        disabled={field.disabled}
        onError={(err) => onError(err.message)}
      />
      {field.help ? <p className="text-caption text-[var(--tv-muted)]">{field.help}</p> : null}
    </div>
  );
}
