"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

interface Props {
  current: Record<string, string | undefined>;
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

  const update = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(sp.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      params.delete("offset"); // reset pagination
      router.push(`?${params}`);
    },
    [router, sp],
  );

  const Select = ({
    name,
    label,
    options,
  }: {
    name: string;
    label: string;
    options: string[];
  }) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-radar-muted uppercase tracking-wide">{label}</label>
      <select
        className="bg-radar-card border border-radar-border rounded px-2 py-1.5 text-sm
                   text-white focus:outline-none focus:border-gray-500"
        value={current[name] ?? ""}
        onChange={e => update(name, e.target.value)}
      >
        <option value="">All</option>
        {options.map(o => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );

  const NumberInput = ({
    name,
    label,
    placeholder,
  }: {
    name: string;
    label: string;
    placeholder: string;
  }) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-radar-muted uppercase tracking-wide">{label}</label>
      <input
        type="number"
        className="bg-radar-card border border-radar-border rounded px-2 py-1.5 text-sm
                   text-white w-28 focus:outline-none focus:border-gray-500"
        placeholder={placeholder}
        defaultValue={current[name] ?? ""}
        onBlur={e => update(name, e.target.value)}
      />
    </div>
  );

  return (
    <div className="flex flex-wrap gap-4 items-end bg-radar-card/40 border border-radar-border
                    rounded-lg p-4">
      <Select name="generation"   label="Generation"   options={generations}   />
      <Select name="body_style"   label="Body"         options={bodyStyles}    />
      <Select name="transmission" label="Transmission" options={transmissions} />
      <Select name="source"       label="Source"       options={sources}       />
      <Select
        name="status"
        label="Status"
        options={["active", "ended", "sold", "relist"]}
      />
      <NumberInput name="year_min"   label="Year min"   placeholder="1965" />
      <NumberInput name="year_max"   label="Year max"   placeholder="1998" />
      <NumberInput name="price_min"  label="Price min"  placeholder="$0"   />
      <NumberInput name="price_max"  label="Price max"  placeholder="$500k"/>

      {/* Reset */}
      <button
        onClick={() => router.push("/")}
        className="text-xs text-radar-muted hover:text-white mt-5 underline"
      >
        Reset
      </button>
    </div>
  );
}
