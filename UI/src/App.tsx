import { useState, useEffect } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadList } from "./components/ThreadList";
import { Thread } from "./components/Thread";
import { SettingsModal } from "./components/SettingsModal";
import { useAgentCLIRuntime, type AgentCLIRuntimeConfig } from "./runtime/useAgentCLIRuntime";
import { useTheme } from "./hooks/useTheme";

const API_BASE = "http://localhost:8100";
const MODEL_STORAGE_KEY = "agent-cli-selected-model";

// Keyboard shortcuts helper - detect platform
const isMac = typeof navigator !== "undefined" && navigator.platform.toUpperCase().indexOf("MAC") >= 0;
const modKey = isMac ? "⌘" : "Ctrl";

const AppContent = ({
  config,
  isSettingsOpen,
  setIsSettingsOpen,
  onConfigChange,
  theme,
  toggleTheme,
}: {
  config: AgentCLIRuntimeConfig;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  onConfigChange: (config: AgentCLIRuntimeConfig) => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
}) => {
  // Keyboard shortcuts for settings and dark mode only
  // Thread navigation is handled by clicking in the sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;

      // Cmd/Ctrl+, for settings
      if (mod && e.key === ",") {
        e.preventDefault();
        setIsSettingsOpen(true);
        return;
      }

      // Cmd/Ctrl+D for dark mode toggle
      if (mod && e.key === "d") {
        e.preventDefault();
        toggleTheme();
        return;
      }

      // Escape to close settings
      if (e.key === "Escape" && isSettingsOpen) {
        e.preventDefault();
        setIsSettingsOpen(false);
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSettingsOpen, setIsSettingsOpen, toggleTheme]);

  return (
    <div className="flex h-screen w-full bg-white dark:bg-gray-900 overflow-hidden transition-colors">
      <ThreadList
        onOpenSettings={() => setIsSettingsOpen(true)}
        theme={theme}
        toggleTheme={toggleTheme}
        model={config.model}
        onModelChange={(model) => onConfigChange({ ...config, model })}
      />
      <div className="flex-grow h-full relative">
        <Thread />
        {!config.model && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 dark:bg-gray-900/80">
            <div className="text-center p-6">
              <p className="text-gray-600 dark:text-gray-400 mb-4">No model selected</p>
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
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        config={config}
        onConfigChange={onConfigChange}
      />

      {/* Keyboard shortcuts hint */}
      <div className="fixed bottom-4 right-4 text-xs text-gray-400 dark:text-gray-600 opacity-50 pointer-events-none">
        {modKey}+, Settings • {modKey}+D Dark
      </div>
    </div>
  );
};

const App = () => {
  const [config, setConfig] = useState<AgentCLIRuntimeConfig>(() => {
    // Load saved model from localStorage on init
    const savedModel = typeof window !== "undefined"
      ? localStorage.getItem(MODEL_STORAGE_KEY) || ""
      : "";
    return {
      model: savedModel,
      memoryTopK: 5,
    };
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const { theme, toggleTheme } = useTheme();

  // Save model to localStorage when it changes
  const handleConfigChange = (newConfig: AgentCLIRuntimeConfig) => {
    setConfig(newConfig);
    if (newConfig.model) {
      localStorage.setItem(MODEL_STORAGE_KEY, newConfig.model);
    }
  };

  // Fetch models on app startup and auto-select the first one if none saved
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/models`);
        if (res.ok) {
          const data = await res.json();
          const models = data.data || [];
          // Only auto-select if no model is saved
          if (models.length > 0 && !config.model) {
            const defaultModel = models[0].id;
            setConfig(prev => ({ ...prev, model: defaultModel }));
            localStorage.setItem(MODEL_STORAGE_KEY, defaultModel);
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
      <div className="flex h-screen w-full items-center justify-center bg-white dark:bg-gray-900 transition-colors">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AppContent
        config={config}
        isSettingsOpen={isSettingsOpen}
        setIsSettingsOpen={setIsSettingsOpen}
        onConfigChange={handleConfigChange}
        theme={theme}
        toggleTheme={toggleTheme}
      />
    </AssistantRuntimeProvider>
  );
};

export default App;
