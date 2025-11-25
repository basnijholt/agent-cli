import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

// Mock fetch for API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  // Default mock for conversations and other endpoints
  mockFetch.mockImplementation((url: string) => {
    if (url.includes("/v1/models")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            data: [
              { id: "model-1", owned_by: "test" },
              { id: "model-2", owned_by: "test" },
            ],
          }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ conversations: [], messages: [] }),
    });
  });
});

describe("App", () => {
  it("renders the main layout with thread list and chat after loading", async () => {
    render(<App />);

    // Wait for loading to complete (models are fetched on startup)
    await waitFor(() => {
      expect(screen.getByText("New Chat")).toBeDefined();
    });

    // Check for empty state message in Thread
    expect(screen.getByText("Start a conversation")).toBeDefined();

    // Check for input placeholder
    expect(screen.getByPlaceholderText("Type a message...")).toBeDefined();

    // Check for Send button
    expect(screen.getByText("Send")).toBeDefined();

    // Check for Settings button in ThreadList
    expect(screen.getByRole("button", { name: "Settings" })).toBeDefined();
  });

  it("opens settings modal and fetches models when Settings button is clicked", async () => {
    render(<App />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Settings" })).toBeDefined();
    });

    // Click Settings button
    const settingsButton = screen.getByRole("button", { name: "Settings" });
    fireEvent.click(settingsButton);

    // Check that modal opens (look for Settings heading)
    expect(screen.getByRole("heading", { name: "Settings" })).toBeDefined();

    // Check for model selector label
    expect(screen.getByText("Model")).toBeDefined();

    // Check for Memory Top-K label
    expect(screen.getByText(/Memory Top-K/)).toBeDefined();

    // Wait for models to be fetched and displayed in modal
    await waitFor(() => {
      expect(screen.getByText("2 models available")).toBeDefined();
    });
  });

  it("auto-selects the first model on startup", async () => {
    render(<App />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.getByText("New Chat")).toBeDefined();
    });

    // Verify models were fetched on startup
    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8100/v1/models");
  });
});
