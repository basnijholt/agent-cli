import { AssistantRuntimeProvider, ThreadPrimitive, ComposerPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import { MarkdownText } from "@assistant-ui/react-markdown";
import { useChat } from "@ai-sdk/react";

const Thread = () => {
  return (
    <ThreadPrimitive.Root className="h-full flex flex-col">
      <ThreadPrimitive.Viewport className="flex-grow overflow-y-auto p-4 space-y-4">
        <ThreadPrimitive.Empty>
          <div className="text-center text-gray-500 mt-10">No messages yet</div>
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>

      <div className="p-4 border-t bg-white">
        <ComposerPrimitive.Root className="flex gap-2">
          <ComposerPrimitive.Input
            className="flex-grow p-2 border rounded-md"
            placeholder="Type a message..."
          />
          <ComposerPrimitive.Send className="px-4 py-2 bg-blue-600 text-white rounded-md">
            Send
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
};

const UserMessage = () => (
  <MessagePrimitive.Root className="flex justify-end">
    <div className="bg-blue-600 text-white p-3 rounded-lg max-w-[80%]">
      <MessagePrimitive.Content />
    </div>
  </MessagePrimitive.Root>
);

const AssistantMessage = () => (
  <MessagePrimitive.Root className="flex justify-start">
    <div className="bg-gray-100 text-gray-900 p-3 rounded-lg max-w-[80%]">
      <MessagePrimitive.Content components={{ Text: MarkdownText }} />
    </div>
  </MessagePrimitive.Root>
);

const App = () => {
  const chat = useChat({
    api: "http://localhost:8100/v1/chat/completions",
  });
  const runtime = useAISDKRuntime(chat);

  return (
    <div className="h-full w-full flex flex-col items-center justify-center p-4 bg-gray-50">
      <div className="w-full max-w-2xl h-[600px] bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
        <AssistantRuntimeProvider runtime={runtime}>
          <Thread />
        </AssistantRuntimeProvider>
      </div>
    </div>
  );
};

export default App;
