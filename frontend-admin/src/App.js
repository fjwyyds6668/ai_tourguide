import React, { useMemo, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from 'antd';
import Sidebar from './components/Sidebar';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import CharactersManagement from './pages/CharactersManagement';
import KnowledgeBase from './pages/KnowledgeBase';
import Analytics from './pages/Analytics';
import AttractionsManagement from './pages/AttractionsManagement';
import Settings from './pages/Settings';
import './App.css';

const { Content } = Layout;

function App() {
  const [collapsed, setCollapsed] = useState(false);

  const siderWidth = useMemo(() => (collapsed ? 80 : 200), [collapsed]);

  return (
    <Router>
      <Routes>
        {/* 公开路由 */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        
        {/* 受保护的路由 */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout style={{ minHeight: '100vh' }}>
                <Sidebar collapsed={collapsed} onCollapse={setCollapsed} />
                {/* 右侧内容区：给固定侧边栏预留空间，并让内容区独立滚动 */}
                <Layout style={{ marginLeft: siderWidth, minHeight: '100vh' }}>
                  <Content style={{ margin: '24px 16px', padding: 24, background: '#fff', overflow: 'auto' }}>
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/characters" element={<CharactersManagement />} />
                      <Route path="/knowledge" element={<KnowledgeBase />} />
                      <Route path="/analytics" element={<Analytics />} />
                      <Route path="/attractions" element={<AttractionsManagement />} />
                      <Route path="/settings" element={<Settings />} />
                      <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                  </Content>
                </Layout>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </Router>
  );
}

export default App;

