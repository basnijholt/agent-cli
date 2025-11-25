import type { FC } from "react";
import { ThreadPrimitive, ComposerPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";

import { Reasoning, ReasoningGroup } from "@/components/assistant-ui/reasoning";
import { ModelPicker } from "@/components/ModelPicker";

// Custom markdown text component for assistant messages
const MarkdownText = () => {
  return (
    <MarkdownTextPrimitive
      remarkPlugins={[remarkGfm]}
      className="prose prose-sm dark:prose-invert max-w-none"
    />
  );
};

// Animated typing indicator
const TypingIndicator = () => (
  <div className="flex items-center gap-1 py-1">
    <span className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
    <span className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
    <span className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
  </div>
);

interface ThreadProps {
  model?: string;
  onModelChange?: (model: string) => void;
}

export const Thread: FC<ThreadProps> = ({ model, onModelChange }) => {
  return (
    <ThreadPrimitive.Root className="h-full flex flex-col bg-white dark:bg-gray-900 transition-colors">
      <ThreadPrimitive.Viewport className="flex-grow overflow-y-auto p-4 space-y-4">
        <ThreadPrimitive.Empty>
          <div className="text-center text-gray-400 dark:text-gray-500 mt-10">
            Start a conversation
          </div>
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>

      <div className="p-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 transition-colors">
        <div className="max-w-4xl mx-auto w-full space-y-2">
          <div className="flex items-center gap-2">
            <ModelPicker value={model} onChange={onModelChange} />
          </div>
          <ComposerPrimitive.Root className="flex gap-2 w-full">
            <ComposerPrimitive.Input
              className="flex-grow p-3 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 transition-colors"
              placeholder="Type a message..."
            />
            <ComposerPrimitive.Send className="px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium">
              Send
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </div>
      </div>
    </ThreadPrimitive.Root>
  );
};

const UserMessage = () => (
  <MessagePrimitive.Root className="flex justify-end mb-4">
    <div className="bg-blue-600 text-white px-4 py-2 rounded-2xl rounded-tr-sm max-w-[80%] shadow-sm">
      <MessagePrimitive.Content />
    </div>
  </MessagePrimitive.Root>
);

const AssistantMessage = () => (
  <MessagePrimitive.Root className="flex justify-start mb-4">
    <div className="bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-4 py-2 rounded-2xl rounded-tl-sm max-w-[80%] shadow-sm border border-gray-200 dark:border-gray-700 transition-colors">
      {/* Show typing indicator when no content yet */}
      <MessagePrimitive.If hasContent={false}>
        <TypingIndicator />
      </MessagePrimitive.If>
      {/* Show actual content when available */}
      <MessagePrimitive.If hasContent>
        <MessagePrimitive.Content
          components={{
            Text: MarkdownText,
            Reasoning: Reasoning,
            ReasoningGroup: ReasoningGroup,
          }}
        />
      </MessagePrimitive.If>
    </div>
  </MessagePrimitive.Root>
);
