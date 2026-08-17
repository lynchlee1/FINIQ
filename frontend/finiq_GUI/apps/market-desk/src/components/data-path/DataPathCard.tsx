"use client";

import { HtmlField, HtmlFieldGrid, HtmlWorkflowCard } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { PathPickerInput } from "@/components/ui/PathPickerInput";

/**
 * LEGACY: 본문에 놓던 데이터 경로 카드. 경로 입력은 WorkflowPathSettings(우측 설정 패널)로 옮겼다.
 * 지우지 말 것 — 본문 배치가 다시 필요할 때 쓴다. DataPathField와 DATA_PATH_LABELS는 계속 사용 중이다.
 */
export const DATA_PATH_LABEL = "작업공간 디렉토리";

export const DATA_PATH_LABELS = {
  workspace: DATA_PATH_LABEL,
  input: DATA_PATH_LABEL,
  output: DATA_PATH_LABEL,
} as const;

export type DataPathField = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  mode?: "folder" | "file" | "save";
  placeholder?: string;
  help?: string;
  disabled?: boolean;
  separateOutputOnly?: boolean;
};

type DataPathCardProps = {
  title?: string;
  description?: string;
  fields: DataPathField[];
  onError: (message: string) => void;
};

export function DataPathCard({
  title = "데이터 경로",
  description,
  fields,
  onError,
}: DataPathCardProps) {
  const visibleFields = fields.filter((field) => !field.separateOutputOnly);

  return (
    <HtmlWorkflowCard title={title} description={description}>
      <HtmlFieldGrid>
        {visibleFields.map((field) => (
          <HtmlField key={field.id} label={field.label} help={field.help} span={4}>
            <div className="flex min-w-0 gap-2">
              <PathPickerInput
                mode={field.mode || "folder"}
                value={field.value}
                onChange={field.onChange}
                placeholder={field.placeholder || `${field.label}를 선택하세요`}
                disabled={field.disabled}
                onError={(err) => onError(err.message)}
                className="flex-1"
              />
            </div>
          </HtmlField>
        ))}
      </HtmlFieldGrid>
    </HtmlWorkflowCard>
  );
}
