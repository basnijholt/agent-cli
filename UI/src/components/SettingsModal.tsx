import { useState, useEffect } from "react";
import { X } from "lucide-react";
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
        if (modelList.length > 0 && !modelList.some((m) => m.id === localModel)) {
          setLocalModel(modelList[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch models");
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
    setLocalModel(config.model || "");
    setLocalTopK(config.memoryTopK || 5);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={handleCancel} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md mx-4 transition-colors">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
          <button
            onClick={handleCancel}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-5">
          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Model
            </label>
            {isLoading ? (
              <div className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-sm">
                Loading models...
              </div>
            ) : error ? (
              <div className="space-y-2">
                <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">
                  {error}
                </div>
                <input
                  type="text"
                  value={localModel}
                  onChange={(e) => setLocalModel(e.target.value)}
                  placeholder="Enter model name manually"
                  className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                />
              </div>
            ) : models.length === 0 ? (
              <input
                type="text"
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                placeholder="Enter model name"
                className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
              />
            ) : (
              <select
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
              >
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.id}
                    {model.owned_by ? ` (${model.owned_by})` : ""}
                  </option>
                ))}
              </select>
            )}
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              {models.length} model{models.length !== 1 ? "s" : ""} available
            </p>
          </div>

          {/* RAG Configuration */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Memory Top-K
              <span className="ml-2 text-gray-400 dark:text-gray-500 font-normal">
                (context chunks)
              </span>
            </label>
            <input
              type="number"
              min={1}
              max={20}
              value={localTopK}
              onChange={(e) => setLocalTopK(parseInt(e.target.value, 10) || 5)}
              className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
            />
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              Higher values = more context, slower responses
            </p>
          </div>

          {/* Current Config Display */}
          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Current:</p>
            <code className="text-xs text-gray-700 dark:text-gray-300 font-mono">
              {config.model || "(no model)"} • top_k: {config.memoryTopK || 5}
            </code>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={handleCancel}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!localModel}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
};
