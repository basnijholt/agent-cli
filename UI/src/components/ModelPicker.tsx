import { useEffect, useState, type FC } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const API_BASE = "http://localhost:8100";
const MODEL_STORAGE_KEY = "agent-cli-selected-model";

interface Model {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

interface ModelsResponse {
  data: Model[];
  object: string;
}

interface ModelPickerProps {
  value?: string;
  onChange?: (model: string) => void;
}

export const ModelPicker: FC<ModelPickerProps> = ({ value, onChange }) => {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    // Initialize from localStorage or props
    if (value) return value;
    if (typeof window !== "undefined") {
      return localStorage.getItem(MODEL_STORAGE_KEY) || "";
    }
    return "";
  });

  // Fetch models from the API
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/models`);
        if (response.ok) {
          const data: ModelsResponse = await response.json();
          // Filter out embedding models
          const chatModels = data.data.filter(
            (m) => !m.id.toLowerCase().includes("embedding")
          );
          setModels(chatModels);

          // Set default model if none selected
          if (!selectedModel && chatModels.length > 0) {
            const defaultModel = chatModels[0].id;
            setSelectedModel(defaultModel);
            onChange?.(defaultModel);
            localStorage.setItem(MODEL_STORAGE_KEY, defaultModel);
          }
        }
      } catch (error) {
        console.error("Failed to fetch models:", error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchModels();
  }, []);

  // Sync with external value prop
  useEffect(() => {
    if (value && value !== selectedModel) {
      setSelectedModel(value);
    }
  }, [value]);

  const handleValueChange = (newValue: string) => {
    setSelectedModel(newValue);
    onChange?.(newValue);
    localStorage.setItem(MODEL_STORAGE_KEY, newValue);
  };

  if (isLoading) {
    return (
      <div className="h-9 w-[200px] animate-pulse rounded-md bg-gray-200 dark:bg-gray-700" />
    );
  }

  if (models.length === 0) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400">
        No models available
      </div>
    );
  }

  return (
    <Select value={selectedModel} onValueChange={handleValueChange}>
      <SelectTrigger className="w-[200px] bg-white dark:bg-gray-800">
        <SelectValue placeholder="Select model" />
      </SelectTrigger>
      <SelectContent>
        {models.map((model) => (
          <SelectItem key={model.id} value={model.id}>
            {model.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
