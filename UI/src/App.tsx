import { useState, useEffect } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadList } from "./components/ThreadList";
import { Thread } from "./components/Thread";
import { SettingsModal } from "./components/SettingsModal";
import { useAgentCLIRuntime, type AgentCLIRuntimeConfig } from "./runtime/useAgentCLIRuntime";

const API_BASE = "http://localhost:8100";

const App = () => {
  const [config, setConfig] = useState<AgentCLIRuntimeConfig>({
    model: "",
    memoryTopK: 5,
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLoadingModels, setIsLoadingModels] = useState(true);

  // Fetch models on app startup and auto-select the first one
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/models`);
        if (res.ok) {
          const data = await res.json();
          const models = data.data || [];
          if (models.length > 0 && !config.model) {
            setConfig(prev => ({ ...prev, model: models[0].id }));
          }
        }
      } catch (err) {
        console.error("Failed to fetch models:", err);
      } finally {
        setIsLoadingModels(false);
      }
    };
    fetchModels();
  }, []);

  const runtime = useAgentCLIRuntime(config);

  // Show loading state while fetching initial model
  if (isLoadingModels) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-white">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-screen w-full bg-white overflow-hidden">
        <ThreadList onOpenSettings={() => setIsSettingsOpen(true)} />
        <div className="flex-grow h-full relative">
          <Thread />
          {!config.model && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80">
              <div className="text-center p-6">
                <p className="text-gray-600 mb-4">No model selected</p>
                <button
                  onClick={() => setIsSettingsOpen(true)}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Open Settings
                </button>
              </div>
            </div>
          )}
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
