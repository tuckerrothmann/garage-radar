"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import {
  displayValue,
  parseMultiValueInput,
  type SearchParams,
} from "@/lib/search-params";

interface Props {
  current: SearchParams;
  generations: string[];
  bodyStyles: string[];
  transmissions: string[];
  sources: string[];
}

export default function ListingFiltersForm({
  current,
  generations,
  bodyStyles,
  transmissions,
  sources,
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const pushParams = useCallback(
    (params: URLSearchParams) => {
      params.delete("offset");
      const query = params.toString();
      router.push(query ? `?${query}` : "/");
    },
    [router],
  );

  const updateMulti = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(sp.toString());
      params.delete(key);
      for (const item of parseMultiValueInput(value)) {
        params.append(key, item);
      }
      pushParams(params);
    },
    [pushParams, sp],
  );

  const updateSingle = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(sp.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      pushParams(params);
    },
    [pushParams, sp],
  );

  const TextInput = ({
    name,
    label,
    placeholder,
    hint,
    suggestions,
    numeric = false,
  }: {
    name: string;
    label: string;
    placeholder: string;
    hint?: string;
    suggestions?: string[];
    numeric?: boolean;
  }) => {
    const datalistId = suggestions?.length ? `${name}-suggestions` : undefined;
    return (
      <div className="flex flex-col gap-1">
        <label className="text-xs uppercase tracking-wide text-radar-muted">{label}</label>
        <input
          type={numeric ? "number" : "text"}
          list={datalistId}
          className="w-36 rounded border border-radar-border bg-radar-card px-2 py-1.5 text-sm
                     text-white focus:border-gray-500 focus:outline-none"
          placeholder={placeholder}
          defaultValue={displayValue(current[name])}
          onBlur={(event) => (
            numeric ? updateSingle(name, event.target.value) : updateMulti(name, event.target.value)
          )}
        />
        {hint && <span className="text-[11px] text-radar-muted">{hint}</span>}
        {datalistId && (
          <datalist id={datalistId}>
            {suggestions?.map((suggestion) => (
              <option key={suggestion} value={suggestion} />
            ))}
          </datalist>
        )}
      </div>
    );
  };

  return (
    <div
      className="flex flex-wrap items-end gap-4 rounded-lg border border-radar-border
                 bg-radar-card/40 p-4"
    >
      <div className="w-full text-xs text-radar-muted">
        Use commas for multi-value search, like <code>Ford, BMW</code> or <code>1972, 1974</code>.
      </div>
      <TextInput name="make" label="Make" placeholder="Porsche, BMW" />
      <TextInput name="model" label="Model" placeholder="911, M3" />
      <TextInput
        name="generation"
        label="Generation"
        placeholder="G5, G6"
        suggestions={generations}
      />
      <TextInput
        name="body_style"
        label="Body"
        placeholder="coupe, suv"
        suggestions={bodyStyles}
      />
      <TextInput
        name="transmission"
        label="Transmission"
        placeholder="manual, auto"
        suggestions={transmissions}
      />
      <TextInput
        name="source"
        label="Source"
        placeholder="bat, ebay"
        suggestions={sources}
      />
      <TextInput
        name="status"
        label="Status"
        placeholder="active, sold"
        suggestions={["active", "ended", "sold", "relist"]}
      />
      <TextInput
        name="year"
        label="Years"
        placeholder="1972, 1974"
        hint="Exact years"
      />
      <TextInput
        name="year_min"
        label="Year Min"
        placeholder="1886"
        numeric
      />
      <TextInput
        name="year_max"
        label="Year Max"
        placeholder="2026"
        numeric
      />
      <TextInput
        name="price_min"
        label="Price Min"
        placeholder="0"
        numeric
      />
      <TextInput
        name="price_max"
        label="Price Max"
        placeholder="500000"
        numeric
      />

      <button
        onClick={() => router.push("/")}
        className="mt-5 text-xs text-radar-muted underline hover:text-white"
      >
        Reset
      </button>
    </div>
  );
}
