import { useEffect, useState, useRef } from "react";
import {
  ThreadListPrimitive,
  ThreadListItemPrimitive,
} from "@assistant-ui/react";
import { MessageSquarePlus, MessageSquare, Trash2, Settings, Moon, Sun, Cpu, ChevronDown, Search } from "lucide-react";

const API_BASE = "http://localhost:8100";

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

interface ThreadListProps {
  onOpenSettings: () => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
  model?: string;
  onModelChange?: (model: string) => void;
}

export const ThreadList = ({ onOpenSettings, theme, toggleTheme, model, onModelChange }: ThreadListProps) => {
  const [models, setModels] = useState<Model[]>([]);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/models`);
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
    if (isModelMenuOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
    if (!isModelMenuOpen) {
      setSearchQuery("");
      setHighlightedIndex(0);
    }
  }, [isModelMenuOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsModelMenuOpen(false);
      }
    };
    if (isModelMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isModelMenuOpen]);

  const displayModelName = model ? model.split("/").pop() || model : "Select model";

  // Filter models using fuzzy match
  const filteredModels = searchQuery
    ? models.filter((m) => fuzzyMatch(m.id, searchQuery))
    : models;

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
    if (!isModelMenuOpen || filteredModels.length === 0) return;

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
          setIsModelMenuOpen(false);
        }
        break;
      case "Escape":
        e.preventDefault();
        setIsModelMenuOpen(false);
        break;
    }
  };

  return (
    <ThreadListPrimitive.Root className="w-64 bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 h-full flex flex-col transition-colors">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700">
        <ThreadListPrimitive.New asChild>
          <button className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
            <MessageSquarePlus size={18} />
            New Chat
          </button>
        </ThreadListPrimitive.New>
      </div>

      <div className="flex-grow overflow-y-auto p-2 space-y-1">
        <ThreadListPrimitive.Items components={{ ThreadListItem }} />
      </div>

      <div className="p-2 border-t border-gray-200 dark:border-gray-700 space-y-1">
        {/* Model Selector */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setIsModelMenuOpen(!isModelMenuOpen)}
            className="w-full flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors"
          >
            <Cpu size={16} />
            <span className="text-sm flex-grow text-left truncate">{displayModelName}</span>
            <ChevronDown size={14} className={`transition-transform ${isModelMenuOpen ? "rotate-180" : ""}`} />
          </button>
          {isModelMenuOpen && models.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 flex flex-col max-h-80">
              {/* Search input */}
              <div className="p-2 border-b border-gray-200 dark:border-gray-700">
                <div className="relative">
                  <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
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
                        setIsModelMenuOpen(false);
                      }}
                      onMouseEnter={() => setHighlightedIndex(index)}
                      className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                        index === highlightedIndex
                          ? "bg-gray-100 dark:bg-gray-700"
                          : ""
                      } ${
                        model === m.id
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

        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          <span className="text-sm">{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>
        </button>
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors"
        >
          <Settings size={16} />
          <span className="text-sm">Settings</span>
        </button>
      </div>
    </ThreadListPrimitive.Root>
  );
};

const ThreadListItem = () => {
  return (
    <ThreadListItemPrimitive.Root className="group data-[active]:bg-white dark:data-[active]:bg-gray-700 data-[active]:shadow-sm data-[active]:text-blue-600 dark:data-[active]:text-blue-400 data-[active]:font-medium data-[active]:ring-1 data-[active]:ring-gray-200 dark:data-[active]:ring-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 w-full rounded-lg flex items-center transition-colors">
      <ThreadListItemPrimitive.Trigger className="flex-grow px-3 py-2 flex items-center gap-2 text-left">
        <MessageSquare size={16} className="opacity-70 flex-shrink-0" />
        <span className="truncate text-sm">
          <ThreadListItemPrimitive.Title fallback="New Chat" />
        </span>
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Archive asChild>
        <button className="mr-2 p-1 opacity-0 group-hover:opacity-100 hover:text-red-600 dark:hover:text-red-400 transition-opacity">
          <Trash2 size={14} />
        </button>
      </ThreadListItemPrimitive.Archive>
    </ThreadListItemPrimitive.Root>
  );
};
