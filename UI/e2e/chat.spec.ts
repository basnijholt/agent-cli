import { test, expect } from '@playwright/test';

// Mock API responses
const mockModels = {
  data: [
    { id: 'test-model-1', owned_by: 'test' },
    { id: 'test-model-2', owned_by: 'test' },
  ],
};

const mockConversations = {
  conversations: [],
};

// Helper to create SSE stream response
function createSSEResponse(content: string): string {
  const chunks = content.split(' ');
  let response = '';
  let accumulated = '';

  // Initial chunk with role
  response += `data: {"choices":[{"finish_reason":null,"index":0,"delta":{"role":"assistant","content":null}}]}\n\n`;

  // Content chunks
  for (const chunk of chunks) {
    accumulated += (accumulated ? ' ' : '') + chunk;
    response += `data: {"choices":[{"finish_reason":null,"index":0,"delta":{"content":"${chunk} "}}]}\n\n`;
  }

  // Final chunk
  response += `data: {"choices":[{"finish_reason":"stop","index":0,"delta":{}}]}\n\n`;
  response += `data: [DONE]\n\n`;

  return response;
}

test.describe('Chat UI', () => {
  test.beforeEach(async ({ page }) => {
    // Mock all API endpoints
    await page.route('**/v1/models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockModels),
      });
    });

    await page.route('**/v1/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConversations),
      });
    });

    await page.route('**/v1/conversations/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ messages: [] }),
      });
    });
  });

  test('loads and displays main UI elements', async ({ page }) => {
    await page.goto('/');

    // Wait for loading to complete
    await expect(page.getByRole('button', { name: 'New Chat' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Settings' })).toBeVisible();
    await expect(page.getByPlaceholder('Type a message...')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
  });

  test('opens settings modal and shows fetched models', async ({ page }) => {
    await page.goto('/');

    // Wait for app to load
    await expect(page.getByText('Settings')).toBeVisible();

    // Open settings
    await page.getByText('Settings').click();

    // Check modal is open
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

    // Check models are displayed
    await expect(page.getByText('2 models available')).toBeVisible();

    // Check model dropdown has options
    const select = page.locator('select');
    await expect(select).toBeVisible();
  });

  test('sends a message and receives streamed response', async ({ page }) => {
    // Track ALL requests
    const allRequests: string[] = [];
    const consoleMessages: string[] = [];
    const consoleErrors: string[] = [];

    page.on('request', (request) => {
      allRequests.push(`${request.method()} ${request.url()}`);
    });

    page.on('console', (msg) => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      consoleErrors.push(`PAGE ERROR: ${error.message}`);
    });

    // Mock chat endpoint with streaming response
    await page.route('**/v1/chat/completions', async (route) => {
      console.log('>>> Chat completions route hit!');
      const sseContent = createSSEResponse('Hello! How can I help you today?');
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseContent,
      });
    });

    await page.goto('/');

    // Wait for app to load
    await expect(page.getByPlaceholder('Type a message...')).toBeVisible();

    // Type a message
    const input = page.getByPlaceholder('Type a message...');
    await input.fill('Hello');

    // Send message by pressing Enter (more reliable than clicking)
    await input.press('Enter');

    // Wait a bit for the message to process
    await page.waitForTimeout(3000);

    // Take screenshot
    await page.screenshot({ path: 'test-results/after-send.png' });

    // Debug: log all info
    console.log('All requests to 8100:', allRequests.filter(r => r.includes('8100')));
    console.log('Console errors:', consoleErrors);
    console.log('Console messages:', consoleMessages.slice(-10)); // Last 10 messages

    // Wait for response to appear - use a more flexible matcher
    await expect(page.getByText(/How can I help/)).toBeVisible({ timeout: 10000 });
  });

  test('handles thinking model with reasoning_content', async ({ page }) => {
    // Mock chat endpoint with reasoning_content (thinking model)
    await page.route('**/v1/chat/completions', async (route) => {
      const response = [
        `data: {"choices":[{"finish_reason":null,"index":0,"delta":{"role":"assistant","content":null}}]}`,
        `data: {"choices":[{"finish_reason":null,"index":0,"delta":{"reasoning_content":"Let me think..."}}]}`,
        `data: {"choices":[{"finish_reason":null,"index":0,"delta":{"reasoning_content":" The user said hello."}}]}`,
        `data: {"choices":[{"finish_reason":"stop","index":0,"delta":{}}]}`,
        `data: [DONE]`,
      ].join('\n\n') + '\n\n';

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: response,
      });
    });

    await page.goto('/');
    await expect(page.getByPlaceholder('Type a message...')).toBeVisible();

    await page.getByPlaceholder('Type a message...').fill('Hello');
    await page.getByText('Send').click();

    // Should display reasoning content
    await expect(page.getByText('Let me think... The user said hello.')).toBeVisible({ timeout: 10000 });
  });

  test('shows error when no model selected', async ({ page }) => {
    // Mock models endpoint to return empty list
    await page.route('**/v1/models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      });
    });

    await page.goto('/');

    // Should show "No model selected" warning
    await expect(page.getByText('No model selected')).toBeVisible();
    await expect(page.getByText('Open Settings')).toBeVisible();
  });

  test('loads existing conversations from backend', async ({ page }) => {
    // Mock conversations endpoint to return existing conversations
    const existingConversations = {
      conversations: ['project-alpha', 'work-notes', 'personal-chat'],
    };

    await page.route('**/v1/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(existingConversations),
      });
    });

    // Mock individual conversation endpoint to return messages
    await page.route('**/v1/conversations/project-alpha', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            { role: 'user', content: 'Previous message from user' },
            { role: 'assistant', content: 'Previous response from assistant' },
          ],
        }),
      });
    });

    await page.goto('/');

    // Wait for app to load
    await expect(page.getByRole('button', { name: 'New Chat' }).first()).toBeVisible();

    // The thread list should show existing conversations
    await expect(page.getByText('project-alpha')).toBeVisible();
    await expect(page.getByText('work-notes')).toBeVisible();
    await expect(page.getByText('personal-chat')).toBeVisible();
  });

  test('auto-selects first conversation and loads its messages', async ({ page }) => {
    // Mock conversations endpoint
    const existingConversations = {
      conversations: ['my-conversation'],
    };

    await page.route('**/v1/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(existingConversations),
      });
    });

    // Mock conversation history with messages
    await page.route('**/v1/conversations/my-conversation', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            { role: 'user', content: 'Hello from previous session' },
            { role: 'assistant', content: 'Hi! I remember our conversation.' },
          ],
        }),
      });
    });

    await page.goto('/');

    // Wait for app to load
    await expect(page.getByRole('button', { name: 'New Chat' }).first()).toBeVisible();

    // The conversation should be auto-selected and messages loaded
    await expect(page.getByText('Hello from previous session')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Hi! I remember our conversation.')).toBeVisible({ timeout: 5000 });
  });

  test('persists selected thread in localStorage', async ({ page, context }) => {
    // Mock conversations endpoint
    await page.route('**/v1/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ conversations: ['chat-1', 'chat-2'] }),
      });
    });

    // Mock conversation endpoints
    await page.route('**/v1/conversations/chat-1', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ messages: [{ role: 'user', content: 'Chat 1 message' }] }),
      });
    });

    await page.route('**/v1/conversations/chat-2', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ messages: [{ role: 'user', content: 'Chat 2 message' }] }),
      });
    });

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'New Chat' }).first()).toBeVisible();

    // Click on chat-2 to switch
    await page.getByText('chat-2').click();

    // Wait for chat-2 messages to load
    await expect(page.getByText('Chat 2 message')).toBeVisible({ timeout: 5000 });

    // Verify localStorage was set (we can check via evaluate)
    const savedThread = await page.evaluate(() => localStorage.getItem('agent-cli-selected-thread'));
    expect(savedThread).toBe('chat-2');
  });
});
