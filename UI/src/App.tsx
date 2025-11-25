import { useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadList } from "./components/ThreadList";
import { Thread } from "./components/Thread";
import { SettingsModal } from "./components/SettingsModal";
import { useAgentCLIRuntime, type AgentCLIRuntimeConfig } from "./runtime/useAgentCLIRuntime";

const App = () => {
  const [config, setConfig] = useState<AgentCLIRuntimeConfig>({
    model: "", // Will be selected from available models in settings
    memoryTopK: 5,
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const runtime = useAgentCLIRuntime(config);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-screen w-full bg-white overflow-hidden">
        <ThreadList onOpenSettings={() => setIsSettingsOpen(true)} />
        <div className="flex-grow h-full relative">
          <Thread />
        </div>
      </div>
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        config={config}
        onConfigChange={setConfig}
      />
    </AssistantRuntimeProvider>
  );
};

export default App;
