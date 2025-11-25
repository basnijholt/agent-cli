import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadList } from "./components/ThreadList";
import { Thread } from "./components/Thread";
import { useAgentCLIRuntime } from "./runtime/useAgentCLIRuntime";

const App = () => {
  const runtime = useAgentCLIRuntime({
    model: "gpt-4o",
    memoryTopK: 5,
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-screen w-full bg-white overflow-hidden">
        <ThreadList />
        <div className="flex-grow h-full relative">
          <Thread />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
};

export default App;
