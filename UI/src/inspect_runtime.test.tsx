import { renderHook } from '@testing-library/react';
import { useAISDKRuntime } from '@assistant-ui/react-ai-sdk';
import { useChat } from '@ai-sdk/react';

// Mock useChat
const mockUseChat = () => ({
  messages: [],
  input: '',
  handleInputChange: () => {},
  handleSubmit: () => {},
  status: 'ready',
});

test('inspect runtime', () => {
  const { result } = renderHook(() => {
    const chat = mockUseChat();
    return useAISDKRuntime(chat as any);
  });

  console.log('Runtime keys:', Object.keys(result.current));
  if (result.current.threadList) {
      console.log('ThreadList keys:', Object.keys(result.current.threadList));
  } else {
      console.log('No threadList on runtime');
  }
});
