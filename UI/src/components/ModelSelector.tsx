import { useEffect, useState, useRef } from "react";
import { ChevronDown, Search, Cpu } from "lucide-react";
import { ENDPOINTS } from "../config";

// Simple fuzzy match function
function fuzzyMatch(text: string, query: string): boolean {
  const textLower = text.toLowerCase();
  const queryLower = query.toLowerCase();

  // Check if all query characters appear in order
  let queryIdx = 0;
  for (let i = 0; i < textLower.length && queryIdx < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIdx]) {
      queryIdx++;
    }
  }
  return queryIdx === queryLower.length;
}

interface Model {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

interface ModelSelectorProps {
  currentModel?: string;
  onModelChange?: (model: string) => void;
}

export const ModelSelector = ({ currentModel, onModelChange }: ModelSelectorProps) => {
  const [models, setModels] = useState<Model[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await fetch(ENDPOINTS.models);
        if (response.ok) {
          const data = await response.json();
          const chatModels = data.data.filter(
            (m: Model) => !m.id.toLowerCase().includes("embedding")
          );
          setModels(chatModels);
        }
      } catch (error) {
        console.error("Failed to fetch models:", error);
      }
    };
    fetchModels();
  }, []);

  // Focus search input when menu opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
    if (!isOpen) {
      setSearchQuery("");
      setHighlightedIndex(0);
    }
  }, [isOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const displayModelName = currentModel
    ? currentModel.split("/").pop() || currentModel
    : "Select model";

  // Filter models using fuzzy match
  const filteredModels = searchQuery ? models.filter((m) => fuzzyMatch(m.id, searchQuery)) : models;

  // Reset highlighted index when search query changes
  useEffect(() => {
    setHighlightedIndex(0);
  }, [searchQuery]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (listRef.current && filteredModels.length > 0) {
      const item = listRef.current.children[highlightedIndex] as HTMLElement;
      if (item) {
        item.scrollIntoView({ block: "nearest" });
      }
    }
  }, [highlightedIndex, filteredModels.length]);

  // Keyboard navigation handler
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || filteredModels.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) => (prev + 1) % filteredModels.length);
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) => (prev - 1 + filteredModels.length) % filteredModels.length);
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

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors"
      >
        <Cpu size={16} />
        <span className="text-sm flex-grow text-left truncate">{displayModelName}</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen && models.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 flex flex-col max-h-80">
          {/* Search input */}
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
          {/* Model list */}
          <div ref={listRef} className="overflow-y-auto flex-1">
            {filteredModels.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                No models found
              </div>
            ) : (
              filteredModels.map((m, index) => (
                <button
                  key={m.id}
                  onClick={() => {
                    onModelChange?.(m.id);
                    setIsOpen(false);
                  }}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                    index === highlightedIndex ? "bg-gray-100 dark:bg-gray-700" : ""
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
