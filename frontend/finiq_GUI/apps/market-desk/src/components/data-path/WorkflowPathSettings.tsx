"use client";

import { Label } from "@finiq/ui";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import type { DataPathField } from "./DataPathCard";

type WorkflowPathSettingsProps = {
  id: string;
  fields: DataPathField[];
  onError: (message: string) => void;
};

/**
 * 작업공간 경로만 우측 설정 패널에 둔다. 본문에는 경로 입력을 두지 않는다.
 * 저장 경로는 코드/설정에서만 따로 둘 수 있고, UI에는 노출하지 않는다.
 */
export function WorkflowPathSettings({ id, fields, onError }: WorkflowPathSettingsProps) {
  const inputFields = fields.filter((field) => !field.separateOutputOnly);

  return (
    <div id={id} className="space-y-3">
      <div className="border-b border-[color:var(--tv-border)] pb-2">
        <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">데이터 경로</p>
      </div>
      {inputFields.map((field) => (
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
