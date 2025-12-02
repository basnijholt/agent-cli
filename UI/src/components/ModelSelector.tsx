import { useEffect, useState, useRef } from "react";
import { ChevronDown, Search, Cpu } from "lucide-react";
import { useModels } from "../hooks/useModels";

function fuzzyMatch(text: string, query: string): boolean {
  const textLower = text.toLowerCase();
  const queryLower = query.toLowerCase();
  let queryIdx = 0;
  for (let i = 0; i < textLower.length && queryIdx < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIdx]) queryIdx++;
  }
  return queryIdx === queryLower.length;
}

interface ModelSelectorProps {
  currentModel?: string;
  onModelChange?: (model: string) => void;
}

export const ModelSelector = ({ currentModel, onModelChange }: ModelSelectorProps) => {
  const { models } = useModels();
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus search and reset on open/close
  useEffect(() => {
    if (isOpen) {
      searchInputRef.current?.focus();
    } else {
      setSearchQuery("");
      setHighlightedIndex(0);
    }
  }, [isOpen]);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (!dropdownRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  const filteredModels = searchQuery ? models.filter((m) => fuzzyMatch(m.id, searchQuery)) : models;

  // Reset highlight on search change
  useEffect(() => setHighlightedIndex(0), [searchQuery]);

  // Scroll highlighted into view
  useEffect(() => {
    const item = listRef.current?.children[highlightedIndex] as HTMLElement;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex, filteredModels.length]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || !filteredModels.length) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((i) => (i + 1) % filteredModels.length);
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((i) => (i - 1 + filteredModels.length) % filteredModels.length);
        break;
      case "Enter":
        e.preventDefault();
        if (filteredModels[highlightedIndex]) {
          onModelChange?.(filteredModels[highlightedIndex].id);
          setIsOpen(false);
        }
        break;
      case "Escape":
        e.preventDefault();
        setIsOpen(false);
        break;
    }
  };

  const displayName = currentModel?.split("/").pop() || "Select model";

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors"
      >
        <Cpu size={16} />
        <span className="text-sm flex-grow text-left truncate">{displayName}</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && models.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 flex flex-col max-h-80">
          <div className="p-2 border-b border-gray-200 dark:border-gray-700">
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search models..."
                className="w-full pl-7 pr-2 py-1.5 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-600 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 text-gray-900 dark:text-gray-100 placeholder-gray-400"
              />
            </div>
          </div>

          <div ref={listRef} className="overflow-y-auto flex-1">
            {filteredModels.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                No models found
              </div>
            ) : (
              filteredModels.map((m, i) => (
                <button
                  key={m.id}
                  onClick={() => {
                    onModelChange?.(m.id);
                    setIsOpen(false);
                  }}
                  onMouseEnter={() => setHighlightedIndex(i)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                    i === highlightedIndex ? "bg-gray-100 dark:bg-gray-700" : ""
                  } ${
                    currentModel === m.id
                      ? "text-blue-600 dark:text-blue-400 font-medium"
                      : "text-gray-700 dark:text-gray-300"
                  }`}
                >
                  {m.id.split("/").pop() || m.id}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
