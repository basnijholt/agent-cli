import {
  ThreadListPrimitive,
  ThreadListItemPrimitive,
} from "@assistant-ui/react";
import { MessageSquarePlus, MessageSquare, Trash2 } from "lucide-react";

export const ThreadList = () => {
  return (
    <ThreadListPrimitive.Root className="w-64 bg-gray-50 border-r border-gray-200 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <ThreadListPrimitive.New asChild>
          <button className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
            <MessageSquarePlus size={20} />
            New Chat
          </button>
        </ThreadListPrimitive.New>
      </div>

      <div className="flex-grow overflow-y-auto p-2 space-y-1">
        <ThreadListPrimitive.Items components={{ ThreadListItem }} />
      </div>
    </ThreadListPrimitive.Root>
  );
};

const ThreadListItem = () => {
  return (
    <ThreadListItemPrimitive.Root className="group data-[active]:bg-white data-[active]:shadow-sm data-[active]:text-blue-600 data-[active]:font-medium data-[active]:ring-1 data-[active]:ring-gray-200 text-gray-700 hover:bg-gray-100 w-full rounded-lg flex items-center transition-colors">
      <ThreadListItemPrimitive.Trigger className="flex-grow px-3 py-2 flex items-center gap-2 text-left">
        <MessageSquare size={18} className="opacity-70 flex-shrink-0" />
        <span className="truncate text-sm">
          <ThreadListItemPrimitive.Title fallback="New Chat" />
        </span>
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Archive asChild>
        <button className="mr-2 p-1 opacity-0 group-hover:opacity-100 hover:text-red-600 transition-opacity">
          <Trash2 size={16} />
        </button>
      </ThreadListItemPrimitive.Archive>
    </ThreadListItemPrimitive.Root>
  );
};
