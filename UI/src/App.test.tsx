import { render, screen } from '@testing-library/react';
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
  });
});
