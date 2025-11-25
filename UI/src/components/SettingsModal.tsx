import { useState, useEffect } from "react";
import type { AgentCLIRuntimeConfig } from "../runtime/useAgentCLIRuntime";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: AgentCLIRuntimeConfig;
  onConfigChange: (config: AgentCLIRuntimeConfig) => void;
}

const AVAILABLE_MODELS = [
  { id: "gpt-4o", name: "GPT-4o", provider: "OpenAI" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", provider: "OpenAI" },
  { id: "gpt-4-turbo", name: "GPT-4 Turbo", provider: "OpenAI" },
  { id: "llama3.2", name: "Llama 3.2", provider: "Ollama" },
  { id: "llama3.1", name: "Llama 3.1", provider: "Ollama" },
  { id: "mistral", name: "Mistral", provider: "Ollama" },
];

export const SettingsModal = ({ isOpen, onClose, config, onConfigChange }: SettingsModalProps) => {
  const [localModel, setLocalModel] = useState(config.model || "gpt-4o");
  const [localTopK, setLocalTopK] = useState(config.memoryTopK || 5);

  // Sync local state when config changes externally
  useEffect(() => {
    setLocalModel(config.model || "gpt-4o");
    setLocalTopK(config.memoryTopK || 5);
  }, [config]);

  if (!isOpen) return null;

  const handleSave = () => {
    onConfigChange({
      model: localModel,
      memoryTopK: localTopK,
    });
    onClose();
  };

  const handleCancel = () => {
    // Reset to original values
    setLocalModel(config.model || "gpt-4o");
    setLocalTopK(config.memoryTopK || 5);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={handleCancel}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Settings</h2>

        {/* Model Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Model
          </label>
          <select
            value={localModel}
            onChange={(e) => setLocalModel(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            {AVAILABLE_MODELS.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name} ({model.provider})
              </option>
            ))}
          </select>
        </div>

        {/* RAG Configuration */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Memory Top-K
            <span className="ml-2 text-gray-400 font-normal">
              (number of context chunks to retrieve)
            </span>
          </label>
          <input
            type="number"
            min={1}
            max={20}
            value={localTopK}
            onChange={(e) => setLocalTopK(parseInt(e.target.value, 10) || 5)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Higher values retrieve more context but may increase response time.
          </p>
        </div>

        {/* Current Config Display */}
        <div className="mb-6 p-3 bg-gray-50 rounded-lg">
          <p className="text-xs text-gray-500 mb-1">Current configuration:</p>
          <code className="text-xs text-gray-700">
            model: {config.model || "gpt-4o"}, memory_top_k: {config.memoryTopK || 5}
          </code>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={handleCancel}
            className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
};
