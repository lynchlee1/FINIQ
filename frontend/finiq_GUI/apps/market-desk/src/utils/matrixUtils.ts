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

export const getChangedFields = (family: any) => {
  const fields: string[] = [];
  const seen = new Set<string>();
  
  // Use backend-provided field names if available (optimized)
  if (family.changed_field_names) {
    return family.changed_field_names;
  }

  for (const change of family.changes || []) {
    for (const fieldChange of change.changes || []) {
      const field = String(fieldChange.field || "").trim();
      if (!field || seen.has(field) || field === "회차") continue;
      seen.add(field);
      fields.push(field);
    }
  }
  return fields;
};

export const getMatrixData = (family: any) => {
  if (!family || !family.has_details) return null;
  const records = family.records || [];
  const changes = family.changes || [];
  const fields = getChangedFields(family);
  
  const matrix: Record<string, any[]> = {};
  for (const f of fields) matrix[f] = new Array(records.length).fill(null);

  if (changes.length > 0) {
    const firstChange = changes[0];
    for (const f of fields) {
      const delta = firstChange.changes.find((c: any) => c.field === f);
      if (delta) matrix[f][0] = delta.before;
    }
  }

  for (let i = 0; i < changes.length; i++) {
    const change = changes[i];
    const vIdx = i + 1;
    for (const f of fields) {
      const delta = change.changes.find((c: any) => c.field === f);
      if (delta) matrix[f][vIdx] = delta.after;
      else matrix[f][vIdx] = matrix[f][vIdx - 1];
    }
  }

  for (const f of fields) {
    let firstIdx = matrix[f].findIndex((v: any) => v !== null);
    if (firstIdx > 0) {
      for (let j = 0; j < firstIdx; j++) matrix[f][j] = matrix[f][firstIdx];
    }
  }
  return { fields, records, matrix };
};
