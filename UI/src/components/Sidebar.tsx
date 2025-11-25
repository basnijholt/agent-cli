import { MessageSquarePlus, MessageSquare } from "lucide-react";

interface SidebarProps {
  conversations: string[];
  currentId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
}

export const Sidebar = ({ conversations, currentId, onSelect, onCreate }: SidebarProps) => {
  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <button
          onClick={onCreate}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
        >
          <MessageSquarePlus size={20} />
          New Chat
        </button>
      </div>

      <div className="flex-grow overflow-y-auto p-2 space-y-1">
        {conversations.map((id) => (
          <button
            key={id}
            onClick={() => onSelect(id)}
            className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 transition-colors ${
              currentId === id
                ? "bg-white shadow-sm text-blue-600 font-medium ring-1 ring-gray-200"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            <MessageSquare size={18} className="opacity-70" />
            <span className="truncate">{id}</span>
          </button>
        ))}
      </div>
    </div>
  );
};
