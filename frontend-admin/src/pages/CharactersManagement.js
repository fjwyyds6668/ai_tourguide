import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import api from '../api';

const emptyToNull = (v) => (v === '' ? null : v);

const CharactersManagement = () => {
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form] = Form.useForm();

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/characters/characters', { params: { active_only: false } });
      setRows(res.data || []);
    } catch (e) {
      console.error(e);
      message.error(e.response?.data?.detail || '获取角色列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setModalOpen(true);
  }, [form]);

  const openEdit = useCallback((row) => {
    setEditing(row);
    form.setFieldsValue({
      name: row.name,
      style: row.style ?? '',
      avatar_url: row.avatar_url ?? '',
      description: row.description ?? '',
      prompt: row.prompt ?? '',
      is_active: !!row.is_active,
    });
    setModalOpen(true);
  }, [form]);

  const handleDelete = useCallback(async (row) => {
    Modal.confirm({
      title: `删除角色「${row.name}」？`,
      content: '删除后不可恢复（如需隐藏建议改为禁用）。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.delete(`/characters/characters/${row.id}`);
          message.success('删除成功');
          fetchList();
        } catch (e) {
          console.error(e);
          message.error(e.response?.data?.detail || '删除失败');
        }
      },
    });
  }, [fetchList]);

  const handleToggleActive = useCallback(async (row, checked) => {
    try {
      await api.put(`/characters/characters/${row.id}`, { is_active: checked });
      message.success('更新成功');
      fetchList();
    } catch (e) {
      console.error(e);
      message.error(e.response?.data?.detail || '更新失败');
    }
  }, [fetchList]);

  const columns = useMemo(
    () => [
      { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
      {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        render: (v, row) => (
          <Space direction="vertical" size={0}>
            <strong>{v}</strong>
            {row.style ? <Tag color="blue">{row.style}</Tag> : null}
          </Space>
        ),
      },
      {
        title: '头像/模型ID',
        dataIndex: 'avatar_url',
        key: 'avatar_url',
        ellipsis: true,
        render: (v) => (v ? <span title={v}>{v}</span> : <span style={{ color: '#999' }}>-</span>),
      },
      {
        title: '启用',
        dataIndex: 'is_active',
        key: 'is_active',
        width: 100,
        render: (v, row) => (
          <Switch checked={!!v} onChange={(checked) => handleToggleActive(row, checked)} />
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 180,
        render: (_, row) => (
          <Space>
            <Button icon={<EditOutlined />} onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(row)}>
              删除
            </Button>
          </Space>
        ),
      },
    ],
    [handleDelete, handleToggleActive, openEdit]
  );

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        style: emptyToNull(values.style?.trim() ?? ''),
        avatar_url: emptyToNull(values.avatar_url?.trim() ?? ''),
        description: emptyToNull(values.description?.trim() ?? ''),
        prompt: emptyToNull(values.prompt?.trim() ?? ''),
        is_active: !!values.is_active,
      };

      if (editing) {
        await api.put(`/characters/characters/${editing.id}`, payload);
        message.success('更新成功');
      } else {
        await api.post('/characters/characters', payload);
        message.success('创建成功');
      }

      setModalOpen(false);
      fetchList();
    } catch (e) {
      if (e?.errorFields) return; // form validate error
      console.error(e);
      message.error(e.response?.data?.detail || '保存失败');
    }
  };

  return (
    <div>
      <h1>数字人角色管理</h1>

      <Card
        style={{ marginTop: 16 }}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchList}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增角色
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          dataSource={rows}
          columns={columns}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editing ? '编辑角色' : '新增角色'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="角色名称"
            name="name"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="例如：亲切导游 / 专业学者 / 儿童版小伙伴" />
          </Form.Item>

          <Form.Item label="讲解风格（style）" name="style">
            <Input placeholder="例如：亲切导游" />
          </Form.Item>

          <Form.Item label="头像/模型ID（avatar_url）" name="avatar_url">
            <Input placeholder="可用于游客端选择模型，例如：Mao / Tsumiki / 或资源URL" />
          </Form.Item>

          <Form.Item label="简介（description）" name="description">
            <Input.TextArea rows={2} placeholder="角色简介" />
          </Form.Item>

          <Form.Item label="角色提示词（prompt）" name="prompt">
            <Input.TextArea rows={4} placeholder="用于控制角色说话风格、口吻、身份设定等" />
          </Form.Item>

          <Form.Item label="是否启用" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CharactersManagement;


