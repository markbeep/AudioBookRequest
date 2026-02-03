import { useState } from "preact/hooks";

export interface SearchInputProps {
  searchTerm?: string;
  regions: string[];
  initialRegion: string;
}

export default function SearchInput({
  searchTerm,
  regions,
  initialRegion,
}: SearchInputProps) {
  const [search, setSearch] = useState(searchTerm || "");
  const [suggestions, setSuggestions] = useState([]);
  const [selectedRegion, setSelectedRegion] = useState(initialRegion);

  const onInput = async (e: Event) => {
    const target = e.target as HTMLInputElement;
    const value = target.value;
    setSearch(value);

    let url = `/api/search/suggestions?q=${encodeURIComponent(value)}`;
    if (selectedRegion) {
      url += `&region=${encodeURIComponent(selectedRegion)}`;
    }

    const response = await fetch(url);
    if (response.ok) {
      const data = await response.json();
      setSuggestions(data.suggestions || []);
    } else {
      console.debug("Failed to fetch suggestions", response);
      setSuggestions([]);
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
        {suggestions.slice(3).map((v) => (
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
