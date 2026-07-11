"use client";

import { useRef, type PointerEvent as ReactPointerEvent } from "react";
import { Flag, Play } from "lucide-react";

type RangeTask = {
  value: number;
  label: string;
};

type DisclosureWorkflowRangeSelectorProps = {
  tasks: RangeTask[];
  start: number;
  end: number;
  disabled?: boolean;
  onRangeChange: (start: number, end: number) => void;
};

export function DisclosureWorkflowRangeSelector({
  tasks,
  start,
  end,
  disabled = false,
  onRangeChange,
}: DisclosureWorkflowRangeSelectorProps) {
  const dragAnchorRef = useRef<number | null>(null);
  const lastDragValueRef = useRef<number | null>(null);

  const selectThrough = (value: number) => {
    const anchor = dragAnchorRef.current;
    if (anchor === null || lastDragValueRef.current === value) return;
    lastDragValueRef.current = value;
    onRangeChange(Math.min(anchor, value), Math.max(anchor, value));
  };

  const taskValueAtPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const taskElement = element?.closest<HTMLElement>("[data-workflow-task-value]");
    const value = Number(taskElement?.dataset.workflowTaskValue);
    return tasks.some((task) => task.value === value) ? value : null;
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled || event.button !== 0) return;
    const value = taskValueAtPointer(event);
    if (value === null) return;
    event.preventDefault();
    dragAnchorRef.current = value;
    lastDragValueRef.current = null;
    event.currentTarget.setPointerCapture(event.pointerId);
    selectThrough(value);
  };

  const finishDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragAnchorRef.current = null;
    lastDragValueRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div className="overflow-x-auto">
      <div
        className={`grid min-w-[720px] touch-none grid-cols-7 overflow-hidden rounded-md border border-[color:var(--tv-border)] ${disabled ? "cursor-not-allowed opacity-60" : "cursor-grab active:cursor-grabbing"}`}
        onPointerDown={handlePointerDown}
        onPointerMove={(event) => {
          if (dragAnchorRef.current === null) return;
          const value = taskValueAtPointer(event);
          if (value !== null) selectThrough(value);
        }}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={() => {
          dragAnchorRef.current = null;
          lastDragValueRef.current = null;
        }}
      >
        {tasks.map((task) => {
          const selected = task.value >= start && task.value <= end;
          const isStart = task.value === start;
          const isEnd = task.value === end;
          const endpointLabel = isStart && isEnd ? "선택 범위" : isStart ? "선택 범위 시작" : isEnd ? "선택 범위 끝" : "";
          return (
            <button
              key={task.value}
              type="button"
              data-workflow-task-value={task.value}
              disabled={disabled}
              aria-pressed={selected}
              aria-label={`${task.label}${endpointLabel ? `, ${endpointLabel}` : ""}`}
              className={[
                "relative flex min-h-16 select-none items-center justify-center border-r border-[color:var(--tv-border)] px-5 py-3 text-center text-xs outline-none last:border-r-0 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--tv-accent)]",
                selected ? "bg-[var(--tv-accent-soft)] font-semibold text-[var(--tv-text)]" : "bg-[var(--tv-control)] font-medium text-[var(--tv-muted)]",
              ].join(" ")}
              onKeyDown={(event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                onRangeChange(task.value, task.value);
              }}
            >
              {selected ? <span className="absolute inset-x-0 top-0 h-0.5 bg-[var(--tv-accent)]" /> : null}
              {isStart ? <Play className="absolute left-2 top-2 h-3.5 w-3.5 text-[var(--tv-accent)]" aria-hidden="true" /> : null}
              {isEnd ? <Flag className="absolute bottom-2 right-2 h-3.5 w-3.5 text-[var(--tv-text)]" aria-hidden="true" /> : null}
              <span>{task.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
