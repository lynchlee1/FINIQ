export const stableJson = (val: any) => {
  if (val === null || val === undefined) return "null";
  if (typeof val !== "object") return String(val);
  try { return JSON.stringify(val); } catch { return String(val); }
};

export const formatValueWithField = (value: any, fieldName: string) => {
  if (value === null || value === undefined || value === "") return "-";
  if (fieldName === "발행금액" || fieldName === "발행가액") {
    const num = Number(value);
    return Number.isFinite(num) ? (num / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : String(value);
  }
  if ((fieldName === "발행대상자" || fieldName === "투자자") && Array.isArray(value)) {
    return value.map((target: any) => {
      if (Array.isArray(target)) {
        const name = target[0];
        const amount = target[target.length - 1];
        return !isNaN(Number(amount)) ? `${name} (${Number(amount).toLocaleString()})` : target.join(" ");
      }
      return String(target);
    }).join("\n");
  }
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
};

export const parseKoreanDate = (dateStr: any) => {
  if (!dateStr || typeof dateStr !== "string") return NaN;
  const match = dateStr.match(/(\d{4})\s*[년.-]\s*(\d{1,2})\s*[월.-]\s*(\d{1,2})/);
  if (match) return new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3])).getTime();
  const clean = dateStr.replace(/[^\d]/g, "");
  if (clean.length === 8) return new Date(parseInt(clean.substring(0, 4)), parseInt(clean.substring(4, 6)) - 1, parseInt(clean.substring(6, 8))).getTime();
  return NaN;
};

export const parseNumericValue = (val: any) => {
  if (typeof val === "number") return val;
  if (typeof val !== "string") return NaN;
  const clean = val.replace(/,/g, "").match(/-?\d+\.?\d*/);
  return clean ? parseFloat(clean[0]) : NaN;
};

const numericSignature = (value: any): { shape: string; values: number[] } => {
  if (typeof value === "number" || typeof value === "string") {
    const parsed = parseNumericValue(value);
    if (!Number.isNaN(parsed)) return { shape: "number", values: [parsed] };
    return { shape: `literal:${stableJson(value)}`, values: [] };
  }
  if (Array.isArray(value)) {
    const children = value.map(numericSignature);
    return {
      shape: `list:[${children.map((child) => child.shape).join("|")}]`,
      values: children.flatMap((child) => child.values),
    };
  }
  if (value && typeof value === "object") {
    const children = Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, numericSignature(item)] as const);
    return {
      shape: `object:{${children.map(([key, child]) => `${key}:${child.shape}`).join("|")}}`,
      values: children.flatMap(([, child]) => child.values),
    };
  }
  return { shape: `literal:${stableJson(value)}`, values: [] };
};

export const numericChangeWithinThreshold = (before: any, after: any, threshold: number) => {
  const beforeSignature = numericSignature(before);
  const afterSignature = numericSignature(after);
  if (
    beforeSignature.shape !== afterSignature.shape ||
    beforeSignature.values.length === 0 ||
    beforeSignature.values.length !== afterSignature.values.length
  ) return false;
  return beforeSignature.values.every((beforeValue, index) => {
    const afterValue = afterSignature.values[index];
    if (afterValue === 0) return beforeValue === afterValue;
    return Math.abs((afterValue - beforeValue) / afterValue) * 100 <= threshold;
  });
};

export const getChangedFields = (family: any) => {
  return Array.isArray(family?.changed_field_names) ? family.changed_field_names : [];
};

export const getMatrixData = (family: any) => {
  if (!family || !family.has_details) return null;
  const records = family.records || [];
  const changes = family.changes || [];
  const fields = getChangedFields(family);
  if (!fields.length) return null;
  
  const unset = Symbol("unset matrix value");
  const matrix: Record<string, any[]> = {};
  for (const field of fields) matrix[field] = new Array(records.length).fill(unset);

  const recordPositionByIndex = new Map<unknown, number>();
  records.forEach((record: any, position: number) => {
    recordPositionByIndex.set(record.index, position);
  });
  for (const change of changes) {
    const beforePosition = recordPositionByIndex.get(change.before?.index);
    const afterPosition = recordPositionByIndex.get(change.after?.index);
    if (beforePosition === undefined || afterPosition === undefined) continue;
    for (const delta of change.changes || []) {
      if (!matrix[delta.field]) continue;
      matrix[delta.field][beforePosition] = delta.before;
      matrix[delta.field][afterPosition] = delta.after;
    }
  }

  for (const field of fields) {
    const values = matrix[field];
    for (let index = 1; index < values.length; index += 1) {
      if (values[index] === unset && values[index - 1] !== unset) values[index] = values[index - 1];
    }
    for (let index = values.length - 2; index >= 0; index -= 1) {
      if (values[index] === unset && values[index + 1] !== unset) values[index] = values[index + 1];
    }
    matrix[field] = values.map((value) => value === unset ? null : value);
  }
  return { fields, records, matrix };
};
