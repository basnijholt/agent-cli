import { ThreadPrimitive, ComposerPrimitive, MessagePrimitive } from "@assistant-ui/react";
import type { TextMessagePartProps, ReasoningMessagePartProps, ReasoningGroupProps } from "@assistant-ui/react";
import { type PropsWithChildren } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Custom markdown text component for assistant messages
const MarkdownText = ({ text }: TextMessagePartProps) => {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {text}
    </ReactMarkdown>
  );
};

// Reasoning text component (renders inside the collapsible group)
const ReasoningText = ({ text }: ReasoningMessagePartProps) => {
  return (
    <div className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
      {text}
    </div>
  );
};

// Collapsible reasoning group wrapper
const ReasoningGroup = ({ children }: PropsWithChildren<ReasoningGroupProps>) => {
  return (
    <details className="mb-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <summary className="px-3 py-2 bg-gray-50 dark:bg-gray-800/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
        <svg className="w-4 h-4 transition-transform details-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        Reasoning
      </summary>
      <div className="px-3 py-2 bg-gray-50/50 dark:bg-gray-800/30 max-h-64 overflow-y-auto">
        {children}
      </div>
    </details>
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

export const Thread = () => {
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
        <ComposerPrimitive.Root className="flex gap-2 max-w-4xl mx-auto w-full">
          <ComposerPrimitive.Input
            className="flex-grow p-3 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 transition-colors"
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
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <MessagePrimitive.Content
            components={{
              Text: MarkdownText,
              Reasoning: ReasoningText,
              ReasoningGroup: ReasoningGroup,
            }}
          />
        </div>
      </MessagePrimitive.If>
    </div>
  </MessagePrimitive.Root>
);
