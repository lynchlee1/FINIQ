"use client";

import { HtmlField, HtmlFieldGrid, HtmlWorkflowCard } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useSettingsStore } from "@/store/useSettingsStore";

export const DATA_PATH_LABELS = {
  workspace: "작업공간 디렉토리",
  input: "입력 데이터 경로",
  output: "결과 데이터 경로",
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
  const useSeparateOutputDirectory = useSettingsStore(
    (state) => state.disclosure_separate_output_directory,
  );
  const visibleFields = fields.filter(
    (field) => !field.separateOutputOnly || useSeparateOutputDirectory,
  );

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
