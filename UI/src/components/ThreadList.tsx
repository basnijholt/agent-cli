import { ThreadListPrimitive, ThreadListItemPrimitive } from "@assistant-ui/react";
import { MessageSquarePlus, MessageSquare, Trash2, Settings, Moon, Sun } from "lucide-react";
import { ModelSelector } from "./ModelSelector";

interface ThreadListProps {
  onOpenSettings: () => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
  model?: string;
  onModelChange?: (model: string) => void;
}

export const ThreadList = ({
  onOpenSettings,
  theme,
  toggleTheme,
  model,
  onModelChange,
}: ThreadListProps) => {
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
        <ModelSelector currentModel={model} onModelChange={onModelChange} />

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
