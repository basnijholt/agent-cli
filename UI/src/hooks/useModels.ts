import { useState, useEffect } from "react";
import { ENDPOINTS } from "../config";
import type { Model } from "../types";

interface UseModelsResult {
  models: Model[];
  isLoading: boolean;
  error: string | null;
}

export function useModels(): UseModelsResult {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(ENDPOINTS.models);
        if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`);
        const data = await res.json();
        // Filter out embedding models
        const chatModels = (data.data || []).filter(
          (m: Model) => !m.id.toLowerCase().includes("embedding")
        );
        setModels(chatModels);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch models");
      } finally {
        setIsLoading(false);
      }
    };
    fetchModels();
  }, []);

  return { models, isLoading, error };
}
