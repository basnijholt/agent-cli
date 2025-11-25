import { useState, useEffect } from "react";
import type { AgentCLIRuntimeConfig } from "../runtime/useAgentCLIRuntime";

const API_BASE = "http://localhost:8100";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: AgentCLIRuntimeConfig;
  onConfigChange: (config: AgentCLIRuntimeConfig) => void;
}

interface ModelInfo {
  id: string;
  owned_by?: string;
}

export const SettingsModal = ({ isOpen, onClose, config, onConfigChange }: SettingsModalProps) => {
  const [localModel, setLocalModel] = useState(config.model || "");
  const [localTopK, setLocalTopK] = useState(config.memoryTopK || 5);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch models when modal opens
  useEffect(() => {
    if (!isOpen) return;

    const fetchModels = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/v1/models`);
        if (!res.ok) {
          throw new Error(`Failed to fetch models: ${res.status}`);
        }
        const data = await res.json();
        const modelList: ModelInfo[] = data.data || [];
        setModels(modelList);

        // If current model is not in the list and list is not empty, select the first one
        if (modelList.length > 0 && !modelList.some(m => m.id === localModel)) {
          setLocalModel(modelList[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch models");
        // Keep any existing models
      } finally {
        setIsLoading(false);
      }
    };

    fetchModels();
  }, [isOpen]);

  // Sync local state when config changes externally
  useEffect(() => {
    setLocalModel(config.model || "");
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
    setLocalModel(config.model || "");
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
          {isLoading ? (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
              Loading models...
            </div>
          ) : error ? (
            <div className="space-y-2">
              <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
                {error}
              </div>
              <input
                type="text"
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                placeholder="Enter model name manually"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          ) : models.length === 0 ? (
            <input
              type="text"
              value={localModel}
              onChange={(e) => setLocalModel(e.target.value)}
              placeholder="Enter model name"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          ) : (
            <select
              value={localModel}
              onChange={(e) => setLocalModel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.id}{model.owned_by ? ` (${model.owned_by})` : ""}
                </option>
              ))}
            </select>
          )}
          <p className="mt-1 text-xs text-gray-500">
            {models.length} model{models.length !== 1 ? "s" : ""} available
          </p>
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
            model: {config.model || "(not set)"}, memory_top_k: {config.memoryTopK || 5}
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
            disabled={!localModel}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
};
