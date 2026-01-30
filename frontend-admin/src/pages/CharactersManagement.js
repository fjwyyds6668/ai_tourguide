import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, message, Select, Upload } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import api from '../api';

const DIGITAL_HUMAN_CHARACTER_OPTIONS = [
  { value: 'Mao', label: '艺术家风格（默认）' },
  { value: 'Chitose', label: '温柔风格' },
  { value: 'Tsumiki', label: '可爱风格' },
  { value: 'Hibiki', label: '活泼风格' },
  { value: 'Izumi', label: '成熟风格' },
  { value: 'Hiyori', label: '标准风格' },
  { value: 'Haru', label: '友好风格' },
  { value: 'Epsilon', label: '优雅风格' },
  { value: 'Shizuku', label: '文静风格' },
  { value: 'Kei', label: '专业风格（多语言）' },
];

const DIGITAL_HUMAN_GROUP_OPTIONS = [
  { value: 'free', label: '免费组（默认）' },
];

const emptyToNull = (v) => (v === '' ? null : v);

const CharactersManagement = () => {
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form] = Form.useForm();
  const [voiceOptions, setVoiceOptions] = useState([]);

  const fetchVoiceOptions = useCallback(async () => {
    try {
      const res = await api.get('/voice/voices');
      setVoiceOptions(res.data || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

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
    fetchVoiceOptions();
  }, [fetchList, fetchVoiceOptions]);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ 
      is_active: true,
      live2d_character_group: 'free'
    });
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
      voice: row.voice ?? undefined,
      live2d_character_name: row.live2d_character_name ?? undefined,
      live2d_character_group: row.live2d_character_group ?? 'free',
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

  const handleAvatarUpload = useCallback(
    async (options) => {
      const { file, onSuccess, onError } = options;
      try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await api.post('/admin/uploads/image', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        const url = res.data?.image_url;
        if (url) {
          form.setFieldsValue({ avatar_url: url });
        }
        message.success('头像图片上传成功');
        onSuccess?.(res.data);
      } catch (e) {
        console.error(e);
        message.error(e.response?.data?.detail || '头像上传失败');
        onError?.(e);
      }
    },
    [form]
  );

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
        title: '数字人配置',
        key: 'live2d',
        width: 200,
        render: (_, row) => {
          if (!row.live2d_character_name) {
            return <span style={{ color: '#999' }}>-</span>;
          }
          const charLabel = DIGITAL_HUMAN_CHARACTER_OPTIONS.find(o => o.value === row.live2d_character_name)?.label ?? row.live2d_character_name;
          const groupLabel = row.live2d_character_group === 'free' ? '免费组（默认）' : (row.live2d_character_group ?? '');
          return (
            <Space direction="vertical" size={0}>
              <Tag color="cyan">{charLabel}</Tag>
              {groupLabel && (
                <Tag color="default" style={{ fontSize: '11px' }}>
                  {groupLabel}
                </Tag>
              )}
            </Space>
          );
        },
      },
      {
        title: '头像/模型ID',
        dataIndex: 'avatar_url',
        key: 'avatar_url',
        ellipsis: true,
        render: (v) => (v ? <span title={v}>{v}</span> : <span style={{ color: '#999' }}>-</span>),
      },
      {
        title: '语音',
        dataIndex: 'voice',
        key: 'voice',
        width: 200,
        ellipsis: true,
        render: (v) => {
          if (!v) return <span style={{ color: '#999' }}>默认</span>;
          const voiceOption = voiceOptions.find(opt => opt.value === v);
          return voiceOption ? (
            <Tag color="purple" title={v}>{voiceOption.label}</Tag>
          ) : (
            <span title={v}>{v}</span>
          );
        },
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
    [handleDelete, handleToggleActive, openEdit, voiceOptions]
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
        voice: emptyToNull(values.voice),
        live2d_character_name: emptyToNull(values.live2d_character_name),
        live2d_character_group: emptyToNull(values.live2d_character_group) || 'free',
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
        maskClosable={false}
        width={640}
        style={{ top: 24 }}
        bodyStyle={{ maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="角色名称"
            name="name"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="例如：亲切导游 / 专业学者 / 儿童版小伙伴" />
          </Form.Item>

          <Form.Item label="讲解风格" name="style">
            <Input placeholder="例如：亲切导游" />
          </Form.Item>

          <Form.Item label="头像/模型ID" name="avatar_url">
            <Space.Compact style={{ width: '100%' }}>
              <Input placeholder="可填模型ID（如 Mao）或通过右侧上传图片" />
              <Upload
                accept="image/*"
                showUploadList={false}
                customRequest={handleAvatarUpload}
              >
                <Button icon={<UploadOutlined />}>上传</Button>
              </Upload>
            </Space.Compact>
          </Form.Item>

          <Form.Item label="简介" name="description">
            <Input.TextArea rows={3} placeholder="角色简介" />
          </Form.Item>

          <Form.Item
            label="角色提示词"
            name="prompt"
            rules={[{ required: true, message: '请输入角色提示词' }]}
          >
            <Input.TextArea rows={12} placeholder="用于控制角色说话风格、口吻、身份设定等" autoSize={{ minRows: 10, maxRows: 16 }} />
          </Form.Item>

          <Form.Item 
            label="语音选择" 
            name="voice"
            tooltip="选择该角色使用的讯飞音色，留空则使用后端默认音色"
          >
            <Select
              placeholder="选择讯飞音色（可选）"
              allowClear
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={voiceOptions}
            />
          </Form.Item>

          <Form.Item 
            label="数字人角色名称" 
            name="live2d_character_name"
            tooltip="选择该角色使用的数字人模型，留空则不使用数字人"
          >
            <Select
              placeholder="选择数字人角色（可选）"
              allowClear
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={DIGITAL_HUMAN_CHARACTER_OPTIONS}
            />
          </Form.Item>

          <Form.Item 
            label="数字人角色组" 
            name="live2d_character_group"
            tooltip="数字人角色所属的组，默认为免费组"
          >
            <Select
              placeholder="选择角色组（默认：免费组）"
              options={DIGITAL_HUMAN_GROUP_OPTIONS}
            />
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


