import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";

const App = () => {
  const [conversations, setConversations] = useState<string[]>([]);
  const [currentId, setCurrentId] = useState<string>("default");

  useEffect(() => {
    fetch("http://localhost:8100/v1/conversations")
      .then((res) => res.json())
      .then((data) => {
        if (data.conversations) {
          setConversations(data.conversations);
        }
      })
      .catch(console.error);
  }, []);

  const handleCreate = () => {
    const newId = `chat-${Date.now()}`;
    setConversations((prev) => [...prev, newId]);
    setCurrentId(newId);
  };

  return (
    <div className="flex h-screen w-full bg-white overflow-hidden">
      <Sidebar
        conversations={conversations}
        currentId={currentId}
        onSelect={setCurrentId}
        onCreate={handleCreate}
      />
      <div className="flex-grow h-full relative">
        <ChatArea key={currentId} conversationId={currentId} />
      </div>
    </div>
  );
};

export default App;
