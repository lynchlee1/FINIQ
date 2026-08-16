"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@finiq/ui";

export type WorkflowModeOption<T extends string> = {
  value: T;
  label: string;
  icon: LucideIcon;
};

export type WorkflowModeSwitchProps<T extends string> = {
  ariaLabel: string;
  value: T;
  options: readonly WorkflowModeOption<T>[];
  onValueChange: (value: T) => void;
  children?: ReactNode;
  testId?: string;
};

export function WorkflowModeSwitch<T extends string>({
  ariaLabel,
  value,
  options,
  onValueChange,
  children,
  testId,
}: WorkflowModeSwitchProps<T>) {
  return (
    <div className="space-y-3">
      <div className="flex w-full items-center" data-testid={testId}>
        <div
          className="inline-flex w-full gap-1 rounded-md border border-[color:var(--tv-border)] p-1 sm:w-auto"
          role="group"
          aria-label={ariaLabel}
        >
          {options.map((option) => {
            const Icon = option.icon;
            const selected = value === option.value;

            return (
              <Button
                key={option.value}
                type="button"
                variant={selected ? "default" : "ghost"}
                size="sm"
                className="h-8 flex-1 gap-1 px-2 duration-150 sm:flex-none"
                aria-pressed={selected}
                onClick={() => onValueChange(option.value)}
              >
                <Icon className="h-4 w-4" />
                {option.label}
              </Button>
            );
          })}
        </div>
      </div>
      {children}
    </div>
  );
}
