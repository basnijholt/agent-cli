import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from './App';

// Mock fetch
global.fetch = vi.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ conversations: ['default'] }),
  })
) as any;

describe('App', () => {
  it('renders the sidebar and chat area', async () => {
    render(<App />);

    // Check for New Chat button in Sidebar
    expect(screen.getByText('New Chat')).toBeDefined();

    // Check for default conversation in Sidebar
    await waitFor(() => {
        expect(screen.getByText('default')).toBeDefined();
    });
  });
});
