import React, { useMemo, useState } from 'react';
import { Layout, Menu, Dropdown, Avatar, Upload, message } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  TeamOutlined,
  UserOutlined,
  UploadOutlined,
  LogoutOutlined,
  SettingOutlined
} from '@ant-design/icons';
import api from '../api';

const { Sider } = Layout;

const Sidebar = ({ collapsed, onCollapse }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const [user, setUser] = useState(() => {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  });

  const avatarSrc = useMemo(() => {
    if (!user?.avatar_url) return null;
    return user.avatar_url;
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const handleAvatarUpload = async (options) => {
    const { file, onSuccess, onError } = options;
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/admin/profile/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const updatedUser = res.data?.user;
      if (updatedUser) {
        localStorage.setItem('user', JSON.stringify(updatedUser));
        setUser(updatedUser);
      }
      message.success('头像上传成功');
      onSuccess?.(res.data);
    } catch (err) {
      console.error('Upload avatar failed:', err);
      message.error(err.response?.data?.detail || '头像上传失败');
      onError?.(err);
    }
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
      key: 'upload_avatar',
      label: (
        <Upload
          accept="image/*"
          showUploadList={false}
          customRequest={handleAvatarUpload}
          beforeUpload={(file) => {
            const isImage = file.type?.startsWith('image/');
            if (!isImage) {
              message.error('只能上传图片文件');
              return Upload.LIST_IGNORE;
            }
            const isLt5M = file.size / 1024 / 1024 < 5;
            if (!isLt5M) {
              message.error('图片大小不能超过 5MB');
              return Upload.LIST_IGNORE;
            }
            return true;
          }}
        >
          上传头像
        </Upload>
      ),
      icon: <UploadOutlined />,
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
      key: '/characters',
      icon: <TeamOutlined />,
      label: '角色管理',
    },
    {
      key: '/knowledge',
      icon: <DatabaseOutlined />,
      label: '景区管理',
    },
    // 景点管理将合并进“景区管理”页面（按景区分组）
    {
      key: '/analytics',
      icon: <BarChartOutlined />,
      label: '数据分析',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '系统设置',
    },
  ];

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={onCollapse}
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
          bottom: 56,
          left: 0,
          right: 0,
          padding: collapsed ? '0 16px' : '0 24px',
          zIndex: 2,
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
              <Avatar size="small" src={avatarSrc} icon={!avatarSrc ? <UserOutlined /> : undefined} />
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

