import { useState, useRef, useEffect, type FC } from "react";
import { createPortal } from "react-dom";
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ActionBarPrimitive,
  useMessage,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { Square, Copy, Check, Info } from "lucide-react";

import { Reasoning, ReasoningGroup } from "@/components/assistant-ui/reasoning";

// Type for message metadata
interface MessageMetadata {
  createdAt?: number;
  model?: string;
  systemFingerprint?: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  durationMs?: number;
  // Timings from API
  promptMs?: number;
  predictedMs?: number;
  promptPerSecond?: number;
  predictedPerSecond?: number;
  cacheTokens?: number;
  [key: string]: unknown;
}

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
    <span
      className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce"
      style={{ animationDelay: "0ms" }}
    />
    <span
      className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce"
      style={{ animationDelay: "150ms" }}
    />
    <span
      className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce"
      style={{ animationDelay: "300ms" }}
    />
  </div>
);

export const Thread: FC = () => {
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
        <div className="max-w-4xl mx-auto w-full">
          <ComposerPrimitive.Root className="flex gap-2 w-full">
            <ComposerPrimitive.Input
              className="flex-grow p-3 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 transition-colors"
              placeholder="Type a message..."
            />
            <ThreadPrimitive.If running={false}>
              <ComposerPrimitive.Send className="px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium">
                Send
              </ComposerPrimitive.Send>
            </ThreadPrimitive.If>
            <ThreadPrimitive.If running>
              <ComposerPrimitive.Cancel className="px-4 py-2 bg-red-600 text-white rounded-xl hover:bg-red-700 transition-colors font-medium flex items-center gap-2">
                <Square size={14} fill="currentColor" />
                Stop
              </ComposerPrimitive.Cancel>
            </ThreadPrimitive.If>
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

// Copy button with feedback
const CopyButton = () => {
  const [copied, setCopied] = useState(false);

  return (
    <ActionBarPrimitive.Copy
      copiedDuration={2000}
      onClick={() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
      title="Copy message"
    >
      {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
    </ActionBarPrimitive.Copy>
  );
};

// Info button with hover tooltip showing message metadata
const InfoButton = () => {
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPos, setTooltipPos] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const message = useMessage();
  const metadata = message.metadata?.custom as MessageMetadata | undefined;

  // Update tooltip position when shown
  useEffect(() => {
    if (showTooltip && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setTooltipPos({
        top: rect.top - 8, // 8px gap above button
        left: rect.left + rect.width / 2,
      });
    }
  }, [showTooltip]);

  if (!metadata) return null;

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <>
      <button
        ref={buttonRef}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        title="Message info"
      >
        <Info size={14} />
      </button>
      {showTooltip &&
        createPortal(
          <div
            className="fixed px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg whitespace-nowrap z-[9999] -translate-x-1/2 -translate-y-full"
            style={{ top: tooltipPos.top, left: tooltipPos.left }}
          >
            <div className="space-y-1">
              {metadata.createdAt && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Time:</span>
                  <span>
                    {formatTime(metadata.createdAt)} · {formatDate(metadata.createdAt)}
                  </span>
                </div>
              )}
              {metadata.model && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Model:</span>
                  <span>{metadata.model.split("/").pop()}</span>
                </div>
              )}
              {metadata.systemFingerprint && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Fingerprint:</span>
                  <span>{metadata.systemFingerprint}</span>
                </div>
              )}
              {metadata.totalTokens !== undefined && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Tokens:</span>
                  <span>
                    {metadata.promptTokens ?? 0} + {metadata.completionTokens ?? 0} ={" "}
                    {metadata.totalTokens}
                    {metadata.cacheTokens ? ` (${metadata.cacheTokens} cached)` : ""}
                  </span>
                </div>
              )}
              {metadata.durationMs !== undefined && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Total time:</span>
                  <span>{formatDuration(metadata.durationMs)}</span>
                </div>
              )}
              {(metadata.promptMs !== undefined || metadata.predictedMs !== undefined) && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Timing:</span>
                  <span>
                    {metadata.promptMs !== undefined &&
                      `${formatDuration(metadata.promptMs)} prompt`}
                    {metadata.promptMs !== undefined && metadata.predictedMs !== undefined && " + "}
                    {metadata.predictedMs !== undefined &&
                      `${formatDuration(metadata.predictedMs)} gen`}
                  </span>
                </div>
              )}
              {(metadata.promptPerSecond !== undefined ||
                metadata.predictedPerSecond !== undefined) && (
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">Speed:</span>
                  <span>
                    {metadata.promptPerSecond !== undefined &&
                      `${Math.round(metadata.promptPerSecond)} prompt`}
                    {metadata.promptPerSecond !== undefined &&
                      metadata.predictedPerSecond !== undefined &&
                      " / "}
                    {metadata.predictedPerSecond !== undefined &&
                      `${Math.round(metadata.predictedPerSecond)} gen`}
                    {" tok/s"}
                  </span>
                </div>
              )}
            </div>
            {/* Arrow pointing down */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>,
          document.body
        )}
    </>
  );
};

const AssistantMessage = () => (
  <MessagePrimitive.Root className="group flex justify-start mb-4">
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
        {/* Action bar - only show when message has content */}
        <ActionBarPrimitive.Root
          hideWhenRunning
          autohide="not-last"
          className="flex gap-1 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700 opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <CopyButton />
          <InfoButton />
        </ActionBarPrimitive.Root>
      </MessagePrimitive.If>
    </div>
  </MessagePrimitive.Root>
);
