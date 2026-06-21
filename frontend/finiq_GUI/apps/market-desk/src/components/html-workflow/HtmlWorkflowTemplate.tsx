"use client"

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Search } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Checkbox, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { WorkflowSidebar } from "@/components/layout/WorkflowSidebar";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { getSidebarDefinition, type WorkflowId } from "@/config/navigation";

export const htmlControlClassName = "h-10 text-sm dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:placeholder:text-slate-600";
export const htmlSelectTriggerClassName = htmlControlClassName;
export const htmlSelectContentClassName = "dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200";

type HtmlWorkflowPageProps = {
  workflowId?: WorkflowId;
  eyebrow?: string;
  title: string;
  description: string;
  notice?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
};

type HtmlWorkflowCardProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
};

type HtmlFieldProps = {
  label: string;
  children: ReactNode;
  help?: string;
  span?: 1 | 2 | 3 | 4;
  className?: string;
};

type HtmlStepItem = {
  icon: LucideIcon;
  title: string;
  description: string;
};

type HtmlStepGuideProps = {
  items: HtmlStepItem[];
};

type HtmlSearchInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
};

type HtmlWorkflowFieldBase = {
  id: string;
  label?: string;
  help?: string;
  span?: 1 | 2 | 3 | 4;
  className?: string;
};

type HtmlPathField = HtmlWorkflowFieldBase & {
  kind: "path";
  label: string;
  mode: "folder" | "file" | "save";
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  onError?: (err: Error) => void;
  placeholder?: string;
  trailing?: ReactNode;
};

type HtmlInputField = HtmlWorkflowFieldBase & {
  kind: "input";
  label: string;
  type?: "text" | "number" | "search";
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  trailing?: ReactNode;
};

type HtmlSelectField = HtmlWorkflowFieldBase & {
  kind: "select";
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
};

type HtmlCheckboxField = HtmlWorkflowFieldBase & {
  kind: "checkbox";
  checked: boolean;
  onChange: (checked: boolean) => void;
  checkboxLabel: string;
};

type HtmlCustomField = HtmlWorkflowFieldBase & {
  kind: "custom";
  content: ReactNode;
};

export type HtmlWorkflowField =
  | HtmlPathField
  | HtmlInputField
  | HtmlSelectField
  | HtmlCheckboxField
  | HtmlCustomField;

type HtmlWorkflowFormProps = {
  fields: HtmlWorkflowField[];
  className?: string;
};

export function HtmlWorkflowPage({
  workflowId = "html-processing",
  eyebrow: _eyebrow = "HTML Workflow",
  title: _title,
  description: _description,
  notice,
  actions,
  children,
}: HtmlWorkflowPageProps) {
  const sidebar = getSidebarDefinition(workflowId);

  return (
    <main className="grid w-full gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <WorkflowSidebar title={sidebar.title} groups={sidebar.groups} />
      <div className="min-w-0 flex flex-col gap-6">
        {(actions || notice) ? (
          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:bg-[#161b22] dark:border-[#30363d]">
            {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
            {notice ? <div className={actions ? "mt-4" : ""}>{notice}</div> : null}
          </section>
        ) : null}
        {children}
      </div>
    </main>
  );
}

export function HtmlWorkflowCard({
  title,
  description,
  actions,
  children,
  footer,
}: HtmlWorkflowCardProps) {
  return (
    <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
      <CardHeader className={cn(
        "flex flex-col md:flex-row md:items-start md:justify-between md:space-y-0",
        description ? "gap-3 pb-4" : "gap-0"
      )}>
        <div className="min-w-0 space-y-1">
          <CardTitle className="dark:text-white">{title}</CardTitle>
          {description ? <CardDescription className="dark:text-slate-400">{description}</CardDescription> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
      {footer}
    </Card>
  );
}

export function HtmlFieldGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("grid gap-4 md:grid-cols-4", className)}>{children}</div>;
}

export function HtmlField({
  label,
  children,
  help,
  span = 1,
  className,
}: HtmlFieldProps) {
  return (
    <div
      className={cn(
        "min-w-0 space-y-2",
        span === 2 && "md:col-span-2",
        span === 3 && "md:col-span-3",
        span === 4 && "md:col-span-4",
        className
      )}
    >
      <Label className="text-slate-600 dark:text-slate-300">{label}</Label>
      {children}
      {help ? <p className="text-xs leading-5 text-slate-500 dark:text-slate-500">{help}</p> : null}
    </div>
  );
}

export function HtmlStepGuide({ items }: HtmlStepGuideProps) {
  return (
    <section className="grid gap-4 md:grid-cols-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.title} className="rounded-lg border border-slate-200 bg-white p-4 dark:bg-[#161b22] dark:border-[#30363d]">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-slate-100 text-slate-700 dark:bg-[#21262d] dark:text-slate-200">
              <Icon className="h-4 w-4" />
            </div>
            <h2 className="text-sm font-bold text-slate-950 dark:text-white">{item.title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.description}</p>
          </div>
        );
      })}
    </section>
  );
}

export function HtmlSearchInput({
  value,
  onChange,
  placeholder,
  className,
}: HtmlSearchInputProps) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
      <Input
        className={cn("pl-9", htmlControlClassName)}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function HtmlWorkflowForm({ fields, className }: HtmlWorkflowFormProps) {
  return (
    <HtmlFieldGrid className={className}>
      {fields.map((field) => (
        <HtmlWorkflowFieldControl key={field.id} field={field} />
      ))}
    </HtmlFieldGrid>
  );
}

function HtmlWorkflowFieldControl({ field }: { field: HtmlWorkflowField }) {
  if (field.kind === "checkbox") {
    return (
      <div
        className={cn(
          "flex h-10 min-w-0 items-center space-x-2 self-end",
          field.span === 2 && "md:col-span-2",
          field.span === 3 && "md:col-span-3",
          field.span === 4 && "md:col-span-4",
          field.className
        )}
      >
        <Checkbox id={field.id} checked={field.checked} onCheckedChange={(value) => field.onChange(!!value)} className="dark:border-[#30363d]" />
        <Label htmlFor={field.id} className="cursor-pointer dark:text-slate-300">{field.checkboxLabel}</Label>
      </div>
    );
  }

  if (field.kind === "custom") {
    if (!field.label) {
      return (
        <div
          className={cn(
            "min-w-0",
            field.span === 2 && "md:col-span-2",
            field.span === 3 && "md:col-span-3",
            field.span === 4 && "md:col-span-4",
            field.className
          )}
        >
          {field.content}
        </div>
      );
    }
    return (
      <HtmlField label={field.label} help={field.help} span={field.span} className={field.className}>
        {field.content}
      </HtmlField>
    );
  }

  if (field.kind === "path") {
    return (
      <HtmlField label={field.label} help={field.help} span={field.span} className={field.className}>
        <div className="flex min-w-0 gap-2">
          <PathPickerInput
            mode={field.mode}
            value={field.value}
            onChange={field.onChange}
            onBlur={field.onBlur}
            onError={field.onError}
            placeholder={field.placeholder}
            className="flex-1"
          />
          {field.trailing}
        </div>
      </HtmlField>
    );
  }

  if (field.kind === "select") {
    return (
      <HtmlField label={field.label} help={field.help} span={field.span} className={field.className}>
        <Select value={field.value} onValueChange={field.onChange}>
          <SelectTrigger className={htmlSelectTriggerClassName}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className={htmlSelectContentClassName}>
            {field.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </HtmlField>
    );
  }

  return (
    <HtmlField label={field.label} help={field.help} span={field.span} className={field.className}>
      <div className="flex min-w-0 gap-2">
        <Input
          type={field.type || "text"}
          value={field.value}
          onChange={(event) => field.onChange(event.target.value)}
          placeholder={field.placeholder}
          className={htmlControlClassName}
        />
        {field.trailing}
      </div>
    </HtmlField>
  );
}
