import { useState, useEffect } from "react";
import { X } from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: {
    model: string;
    ragTopK: number;
  };
  onSave: (config: { model: string; ragTopK: number }) => void;
}

export const SettingsModal = ({ isOpen, onClose, config, onSave }: SettingsModalProps) => {
  const [model, setModel] = useState(config.model);
  const [ragTopK, setRagTopK] = useState(config.ragTopK);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  useEffect(() => {
    if (isOpen) {
      fetch("http://localhost:8100/v1/models")
        .then(res => res.json())
        .then(data => {
          if (data.data) {
            setAvailableModels(data.data.map((m: any) => m.id));
          }
        })
        .catch(() => {
            // Fallback if upstream doesn't support models endpoint
            setAvailableModels(["gpt-4o", "gpt-3.5-turbo", "llama3", "mistral"]);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold">Settings</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-full">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full p-2 border rounded-lg"
            >
              {availableModels.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              RAG Context Limit (Top K)
            </label>
            <input
              type="number"
              value={ragTopK}
              onChange={(e) => setRagTopK(Number(e.target.value))}
              className="w-full p-2 border rounded-lg"
              min={1}
              max={20}
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onSave({ model, ragTopK });
              onClose();
            }}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};
