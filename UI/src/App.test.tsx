import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from './App';

// Mock fetch for API calls
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ conversations: [], messages: [] }),
  })
) as unknown as typeof fetch;

describe('App', () => {
  it('renders the main layout with thread list and chat', () => {
    render(<App />);

    // Check for New Chat button in ThreadList
    expect(screen.getByText('New Chat')).toBeDefined();

    // Check for empty state message in Thread
    expect(screen.getByText('No messages yet')).toBeDefined();

    // Check for input placeholder
    expect(screen.getByPlaceholderText('Type a message...')).toBeDefined();

    // Check for Send button
    expect(screen.getByText('Send')).toBeDefined();

    // Check for Settings button in ThreadList
    expect(screen.getByText('Settings')).toBeDefined();
  });

  it('opens settings modal when Settings button is clicked', () => {
    render(<App />);

    // Click Settings button
    const settingsButton = screen.getByText('Settings');
    fireEvent.click(settingsButton);

    // Check that modal opens (look for Settings heading)
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeDefined();

    // Check for model selector
    expect(screen.getByText('Model')).toBeDefined();

    // Check for Memory Top-K label
    expect(screen.getByText(/Memory Top-K/)).toBeDefined();
  });
});
