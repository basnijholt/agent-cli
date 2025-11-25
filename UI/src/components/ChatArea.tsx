import { useEffect } from "react";
import { useChat } from "@ai-sdk/react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "./Thread";

interface ChatAreaProps {
  conversationId: string;
}

export const ChatArea = ({ conversationId }: ChatAreaProps) => {
  const chat = useChat({
    api: "http://localhost:8100/v1/chat/completions",
    body: {
      memory_id: conversationId,
    },
    id: conversationId,
  });

  const { setMessages } = chat;

  useEffect(() => {
    // Fetch history for this conversation
    fetch(`http://localhost:8100/v1/conversations/${conversationId}`)
      .then(res => res.json())
      .then(data => {
        if (data.messages && data.messages.length > 0) {
          setMessages(data.messages);
        }
      })
      .catch(console.error);
  }, [conversationId, setMessages]);

  const runtime = useAISDKRuntime(chat);

  return (
    <div className="h-full w-full flex flex-col bg-white">
      <AssistantRuntimeProvider runtime={runtime}>
        <Thread />
      </AssistantRuntimeProvider>
    </div>
  );
};
