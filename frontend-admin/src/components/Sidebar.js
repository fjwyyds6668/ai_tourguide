import React, { useState } from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  EnvironmentOutlined
} from '@ant-design/icons';

const { Sider } = Layout;

const Sidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: '仪表盘',
    },
    {
      key: '/knowledge',
      icon: <DatabaseOutlined />,
      label: '知识库管理',
    },
    {
      key: '/attractions',
      icon: <EnvironmentOutlined />,
      label: '景点管理',
    },
    {
      key: '/analytics',
      icon: <BarChartOutlined />,
      label: '数据分析',
    },
  ];

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      theme="light"
      style={{
        overflow: 'auto',
        height: '100vh',
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
      }}
    >
      <div style={{ height: 32, margin: 16, textAlign: 'center', fontWeight: 'bold' }}>
        {collapsed ? 'AI' : 'AI 导游管理'}
      </div>
      <Menu
        theme="light"
        selectedKeys={[location.pathname]}
        mode="inline"
        items={menuItems}
        onClick={({ key }) => navigate(key)}
      />
    </Sider>
  );
};

export default Sidebar;

