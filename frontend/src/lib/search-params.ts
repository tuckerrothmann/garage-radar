export type SearchParamValue = string | string[] | undefined;
export type SearchParams = Record<string, SearchParamValue>;

export function firstValue(value: SearchParamValue): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

export function allValues(value: SearchParamValue): string[] {
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

export function displayValue(value: SearchParamValue): string {
  return allValues(value).join(", ");
}

export function parseMultiValueInput(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function parseNumberValue(value: SearchParamValue): number | undefined {
  const raw = firstValue(value);
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function parseNumberValues(value: SearchParamValue): number[] | undefined {
  const parsed = allValues(value)
    .flatMap((item) => parseMultiValueInput(item))
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
  return parsed.length > 0 ? parsed : undefined;
}

export function buildSearchParams(searchParams: SearchParams): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    for (const item of allValues(value)) {
      params.append(key, item);
    }
  }
  return params;
}
