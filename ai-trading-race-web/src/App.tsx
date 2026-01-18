import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header, Sidebar, Footer } from './components/layout';
import { Dashboard } from './pages/Dashboard';
import { AgentDetail } from './pages/AgentDetail';
import './styles/variables.css';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10000, // 10 seconds
      retry: 2,
    },
  },
});

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const toggleSidebar = () => setSidebarOpen(prev => !prev);
  const closeSidebar = () => setSidebarOpen(false);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app-layout">
          <Header onToggleSidebar={toggleSidebar} sidebarOpen={sidebarOpen} />
          <Sidebar isOpen={sidebarOpen} onClose={closeSidebar} />
          
          <main className="main-content">
            <div className="content-wrapper">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/agents/:id" element={<AgentDetail />} />
              </Routes>
            </div>
          </main>
          
          <Footer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
