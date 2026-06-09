const integerFormatter = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 0,
});

export function formatInteger(value: unknown): string {
  const number = Number(value || 0);
  return Number.isFinite(number) ? integerFormatter.format(number) : "0";
}
