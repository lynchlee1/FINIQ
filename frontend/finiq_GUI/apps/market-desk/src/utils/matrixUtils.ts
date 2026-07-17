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
  const text = dateStr.trim();
  const separatedMatch = text.match(/^(\d{4})([.-])(\d{1,2})\2(\d{1,2})$/);
  const match = separatedMatch
    || text.match(/^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?$/)
    || text.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (!match) return NaN;
  const year = Number(match[1]);
  const month = Number(separatedMatch ? match[3] : match[2]);
  const day = Number(separatedMatch ? match[4] : match[3]);
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year
    || parsed.getMonth() !== month - 1
    || parsed.getDate() !== day
  ) return NaN;
  return parsed.getTime();
};

export const parseNumericValue = (val: any) => {
  if (typeof val === "number") return Number.isFinite(val) ? val : NaN;
  if (typeof val !== "string") return NaN;
  const text = val.trim();
  if (!/^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(text)) return NaN;
  return Number(text.replace(/,/g, ""));
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

  for (const field of fields) matrix[field] = matrix[field].map((value) => value === unset ? null : value);
  return { fields, records, matrix };
};
