import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { useModels } from "../hooks/useModels";
import type { AgentCLIRuntimeConfig } from "../runtime/useAgentCLIRuntime";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: AgentCLIRuntimeConfig;
  onConfigChange: (config: AgentCLIRuntimeConfig) => void;
}

export const SettingsModal = ({ isOpen, onClose, config, onConfigChange }: SettingsModalProps) => {
  const { models, isLoading, error } = useModels();
  const [localModel, setLocalModel] = useState(config.model || "");
  const [localTopK, setLocalTopK] = useState(config.memoryTopK || 5);

  // Sync local state when config changes externally
  useEffect(() => {
    setLocalModel(config.model || "");
    setLocalTopK(config.memoryTopK || 5);
  }, [config]);

  // Auto-select first model if current is invalid
  useEffect(() => {
    if (models.length > 0 && !models.some((m) => m.id === localModel)) {
      setLocalModel(models[0].id);
    }
  }, [models, localModel]);

  if (!isOpen) return null;

  const handleSave = () => {
    onConfigChange({ model: localModel, memoryTopK: localTopK });
    onClose();
  };

  const handleCancel = () => {
    setLocalModel(config.model || "");
    setLocalTopK(config.memoryTopK || 5);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleCancel} />

      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md mx-4 transition-colors">
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
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Model
            </label>
            {isLoading ? (
              <div className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-500 text-sm">
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
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}
                    {m.owned_by ? ` (${m.owned_by})` : ""}
                  </option>
                ))}
              </select>
            )}
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              {models.length} model{models.length !== 1 ? "s" : ""} available
            </p>
          </div>

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

          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Current:</p>
            <code className="text-xs text-gray-700 dark:text-gray-300 font-mono">
              {config.model || "(no model)"} • top_k: {config.memoryTopK || 5}
            </code>
          </div>
        </div>

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
