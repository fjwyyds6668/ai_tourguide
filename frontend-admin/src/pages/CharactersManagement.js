import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, message, Select } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import api from '../api';

// 可用的中文语音列表
const VOICE_OPTIONS = [
  { value: 'zh-CN-XiaoxiaoNeural', label: '晓晓 (女声) - zh-CN-XiaoxiaoNeural' },
  { value: 'zh-CN-XiaoyiNeural', label: '晓伊 (女声) - zh-CN-XiaoyiNeural' },
  { value: 'zh-CN-YunjianNeural', label: '云健 (男声) - zh-CN-YunjianNeural' },
  { value: 'zh-CN-YunxiNeural', label: '云希 (男声) - zh-CN-YunxiNeural' },
  { value: 'zh-CN-YunxiaNeural', label: '云夏 (男声) - zh-CN-YunxiaNeural' },
  { value: 'zh-CN-YunyangNeural', label: '云扬 (男声) - zh-CN-YunyangNeural' },
  { value: 'zh-CN-liaoning-XiaobeiNeural', label: '晓北 (女声，东北话) - zh-CN-liaoning-XiaobeiNeural' },
  { value: 'zh-CN-shaanxi-XiaoniNeural', label: '晓妮 (女声，陕西话) - zh-CN-shaanxi-XiaoniNeural' },
];

// 可用的 Live2D 角色列表
const LIVE2D_CHARACTER_OPTIONS = [
  { value: 'Mao', label: 'Mao - 艺术家风格，有丰富的动作和表情（默认）' },
  { value: 'Chitose', label: 'Chitose - 温柔风格，有指引动作' },
  { value: 'Tsumiki', label: 'Tsumiki - 可爱风格' },
  { value: 'Hibiki', label: 'Hibiki - 活泼风格' },
  { value: 'Izumi', label: 'Izumi - 成熟风格' },
  { value: 'Hiyori', label: 'Hiyori - 标准风格' },
  { value: 'Haru', label: 'Haru - 友好风格' },
  { value: 'Epsilon', label: 'Epsilon - 优雅风格' },
  { value: 'Shizuku', label: 'Shizuku - 文静风格' },
  { value: 'Kei', label: 'Kei - 专业风格（支持多语言）' },
];

// Live2D 角色组选项
const LIVE2D_GROUP_OPTIONS = [
  { value: 'free', label: 'free（免费组，默认）' },
];

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
        title: 'Live2D 配置',
        key: 'live2d',
        width: 200,
        render: (_, row) => {
          if (!row.live2d_character_name) {
            return <span style={{ color: '#999' }}>-</span>;
          }
          return (
            <Space direction="vertical" size={0}>
              <Tag color="cyan">{row.live2d_character_name}</Tag>
              {row.live2d_character_group && (
                <Tag color="default" style={{ fontSize: '11px' }}>
                  {row.live2d_character_group}
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
          const voiceOption = VOICE_OPTIONS.find(opt => opt.value === v);
          return voiceOption ? (
            <Tag color="purple" title={v}>{voiceOption.label.split(' - ')[0]}</Tag>
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

          <Form.Item 
            label="语音选择（voice）" 
            name="voice"
            tooltip="选择该角色使用的TTS语音，留空则使用默认语音（zh-CN-XiaoxiaoNeural）"
          >
            <Select
              placeholder="选择语音（可选，默认使用晓晓）"
              allowClear
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={VOICE_OPTIONS}
            />
          </Form.Item>

          <Form.Item 
            label="Live2D 角色名称" 
            name="live2d_character_name"
            tooltip="选择该角色使用的 Live2D 数字人模型，留空则不使用 Live2D"
          >
            <Select
              placeholder="选择 Live2D 角色（可选）"
              allowClear
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={LIVE2D_CHARACTER_OPTIONS}
            />
          </Form.Item>

          <Form.Item 
            label="Live2D 角色组" 
            name="live2d_character_group"
            tooltip="Live2D 角色所属的组，默认为 'free'"
          >
            <Select
              placeholder="选择角色组（默认：free）"
              options={LIVE2D_GROUP_OPTIONS}
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


