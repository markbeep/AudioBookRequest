import { searchSuggestionsApiSearchSuggestionsGet } from "@/client";
import { regions, type Region, isRegion } from "@/types/region";
import { useState, useEffect } from "preact/hooks";

export interface SearchInputProps {
  searchTerm?: string;
  initialRegion?: Region;
}

export default function SearchInput({
  searchTerm,
  initialRegion,
}: SearchInputProps) {
  const [search, setSearch] = useState(searchTerm || "");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<Region>(
    initialRegion ?? "us",
  );

  // Read URL parameters on mount
  useEffect(() => {
    const url = new URL(window.location.href);
    const urlSearchTerm = url.searchParams.get("q") || "";
    const urlRegion = url.searchParams.get("region") || "us";

    if (urlSearchTerm) {
      setSearch(urlSearchTerm);
    }

    if (isRegion(urlRegion)) {
      setSelectedRegion(urlRegion);
    }
  }, []);

  const onInput = async (e: Event) => {
    const target = e.target as HTMLInputElement;
    const value = target.value;
    setSearch(value);

    const { data: suggestions, error } =
      await searchSuggestionsApiSearchSuggestionsGet({
        query: { q: value, region: selectedRegion },
      });

    setSuggestions(suggestions || []);
    if (error) {
      console.debug("Failed to fetch suggestions", error);
      setSuggestions([]);
      return;
    }
  };

  return (
    <form class="flex items-start w-full join">
      <input
        name="q"
        type="search"
        class="input join-item focus:z-10"
        placeholder="Book name..."
        autofocus={!!searchTerm}
        value={search}
        spellcheck={false}
        autocomplete="off"
        list="search-suggestions"
        onInput={onInput}
      />
      <datalist id="search-suggestions">
        {suggestions.slice(0, 3).map((v) => (
          <option value={v}></option>
        ))}
      </datalist>
      <select
        class="select join-item max-w-16 sm:max-w-20 focus:z-10"
        name="region"
      >
        {regions.map((v) => (
          <option value={v} selected={v === selectedRegion}>
            {v}
          </option>
        ))}
      </select>
      <button id="search" class="btn btn-primary join-item" type="submit">
        <span id="search-text">Search</span>
        <span id="search-spinner" class="loading hidden"></span>
      </button>
    </form>
  );
}
