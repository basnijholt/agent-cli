import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the thread component', () => {
    render(<App />);
    // assistant-ui usually renders an input or some welcome state.
    // We check for the existence of the main container or input.
    // Since we don't have a running backend during test, we just check render.
    const container = screen.getByRole('textbox');
    expect(container).toBeDefined();
  });
});
