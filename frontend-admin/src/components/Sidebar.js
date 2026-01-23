import React, { useState } from 'react';
import { Layout, Menu, Dropdown, Avatar } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  EnvironmentOutlined,
  UserOutlined,
  LogoutOutlined
} from '@ant-design/icons';

const { Sider } = Layout;

const Sidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // 获取用户信息
  const userStr = localStorage.getItem('user');
  const user = userStr ? JSON.parse(userStr) : null;

  // 退出登录
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const userMenuItems = [
    {
      key: 'user',
      label: (
        <div style={{ padding: '4px 0' }}>
          <div style={{ fontWeight: 'bold' }}>{user?.username}</div>
          <div style={{ fontSize: '12px', color: '#999' }}>{user?.email}</div>
        </div>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      label: '退出登录',
      icon: <LogoutOutlined />,
      onClick: handleLogout,
    },
  ];

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
      {user && (
        <div style={{
          position: 'absolute',
          bottom: 16,
          left: 0,
          right: 0,
          padding: collapsed ? '0 16px' : '0 24px',
        }}>
          <Dropdown menu={{ items: userMenuItems }} placement="topLeft">
            <div style={{
              cursor: 'pointer',
              padding: '8px',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background 0.3s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#f5f5f5'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <Avatar size="small" icon={<UserOutlined />} />
              {!collapsed && (
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {user.username}
                </span>
              )}
            </div>
          </Dropdown>
        </div>
      )}
    </Sider>
  );
};

export default Sidebar;

