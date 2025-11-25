import { ThreadPrimitive, ComposerPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { MarkdownText } from "@assistant-ui/react-markdown";

export const Thread = () => {
  return (
    <ThreadPrimitive.Root className="h-full flex flex-col bg-white">
      <ThreadPrimitive.Viewport className="flex-grow overflow-y-auto p-4 space-y-4">
        <ThreadPrimitive.Empty>
          <div className="text-center text-gray-500 mt-10">No messages yet</div>
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>

      <div className="p-4 border-t bg-gray-50">
        <ComposerPrimitive.Root className="flex gap-2 max-w-4xl mx-auto w-full">
          <ComposerPrimitive.Input
            className="flex-grow p-3 border rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            placeholder="Type a message..."
          />
          <ComposerPrimitive.Send className="px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium">
            Send
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
};

const UserMessage = () => (
  <MessagePrimitive.Root className="flex justify-end mb-4">
    <div className="bg-blue-600 text-white px-4 py-2 rounded-2xl rounded-tr-none max-w-[80%] shadow-sm">
      <MessagePrimitive.Content />
    </div>
  </MessagePrimitive.Root>
);

const AssistantMessage = () => (
  <MessagePrimitive.Root className="flex justify-start mb-4">
    <div className="bg-white border border-gray-200 text-gray-900 px-4 py-2 rounded-2xl rounded-tl-none max-w-[80%] shadow-sm">
      <MessagePrimitive.Content components={{ Text: MarkdownText }} />
    </div>
  </MessagePrimitive.Root>
);
