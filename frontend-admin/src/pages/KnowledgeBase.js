import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Button, Table, Modal, Form, Input, message, Popconfirm, Space, Tabs, List, Upload } from 'antd';
import { PlusOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import api from '../api';

const KnowledgeBase = () => {
  const [loading, setLoading] = useState(false);

  // Scenic spots
  const [scenicSpots, setScenicSpots] = useState([]);
  const [selectedScenicId, setSelectedScenicId] = useState(null);
  const [scenicVisible, setScenicVisible] = useState(false);
  const [scenicEditing, setScenicEditing] = useState(null);
  const [scenicForm] = Form.useForm();

  // Scenic knowledge
  const [knowledgeVisible, setKnowledgeVisible] = useState(false);
  const [knowledgeForm] = Form.useForm();
  const [knowledgeData, setKnowledgeData] = useState([]);

  // Attractions under scenic
  const [attractionsData, setAttractionsData] = useState([]);
  const [attractionVisible, setAttractionVisible] = useState(false);
  const [attractionForm] = Form.useForm();

  const loadScenicSpots = useCallback(async (preferId = null) => {
    try {
      setLoading(true);
      const res = await api.get('/admin/scenic-spots');
      const list = res.data || [];
      setScenicSpots(list);
      const nextId =
        (preferId && list.find((x) => x.id === preferId)?.id) ||
        (selectedScenicId && list.find((x) => x.id === selectedScenicId)?.id) ||
        (list.length > 0 ? list[0].id : null);
      setSelectedScenicId(nextId);
    } catch (error) {
      console.error('加载景区失败:', error);
      setScenicSpots([]);
    } finally {
      setLoading(false);
    }
  }, [selectedScenicId]);

  useEffect(() => {
    loadScenicSpots();
  }, [loadScenicSpots]);

  // 当选中的景区变化时，加载该景区下的知识/景点
  useEffect(() => {
    if (!selectedScenicId) return;
    loadScenicKnowledge(selectedScenicId);
    loadScenicAttractions(selectedScenicId);
  }, [selectedScenicId]);

  const selectedScenic = useMemo(
    () => scenicSpots.find((s) => s.id === selectedScenicId) || null,
    [scenicSpots, selectedScenicId]
  );

  const loadScenicKnowledge = async (scenicId) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/scenic-spots/${scenicId}/knowledge`);
      setKnowledgeData(res.data || []);
    } catch (e) {
      console.error('加载景区知识失败:', e);
      setKnowledgeData([]);
    } finally {
      setLoading(false);
    }
  };

  const loadScenicAttractions = async (scenicId) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/scenic-spots/${scenicId}/attractions`);
      setAttractionsData(res.data || []);
    } catch (e) {
      console.error('加载景点失败:', e);
      setAttractionsData([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCoverUpload = async (options) => {
    const { file, onSuccess, onError } = options;
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/admin/uploads/image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const url = res.data?.image_url;
      if (url) {
        scenicForm.setFieldsValue({ cover_image_url: url });
      }
      message.success('封面图片上传成功');
      onSuccess?.(res.data);
    } catch (err) {
      console.error('封面上传失败:', err);
      message.error(err.response?.data?.detail || '封面上传失败');
      onError?.(err);
    }
  };

  const knowledgeColumns = [
    {
      title: 'ID',
      dataIndex: 'text_id',
      key: 'text_id',
    },
    {
      title: '内容',
      dataIndex: 'text',
      key: 'text',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Popconfirm
          title="确定要删除这条知识吗？"
          okText="删除"
          cancelText="取消"
          onConfirm={async () => {
            try {
              setLoading(true);
              await api.delete(`/admin/knowledge/${encodeURIComponent(record.text_id)}`);
              message.success('删除成功');
              if (selectedScenicId) loadScenicKnowledge(selectedScenicId);
            } catch (error) {
              console.error('删除失败:', error);
              message.error(error.response?.data?.detail || '删除失败');
            } finally {
              setLoading(false);
            }
          }}
        >
          <Button danger size="small">删 除</Button>
        </Popconfirm>
      ),
    },
  ];

  const handleSubmitKnowledge = async (values) => {
    try {
      setLoading(true);
      if (!selectedScenicId) {
        message.error('请先选择一个景区');
        return;
      }
      await api.post(
        `/admin/scenic-spots/${selectedScenicId}/knowledge/upload`,
        [
          {
            text: values.text,
            text_id: values.text_id || `kb_${Date.now()}`,
            metadata: {},
          },
        ],
        { timeout: 120000 }
      );
      message.success('上传成功');
      setKnowledgeVisible(false);
      knowledgeForm.resetFields();
      loadScenicKnowledge(selectedScenicId);
    } catch (error) {
      message.error(error.response?.data?.detail || ('上传失败：' + error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleClearGraph = async () => {
    try {
      setLoading(true);
      await api.post('/admin/knowledge/clear-graph');
      message.success('已清空图数据库');
    } catch (error) {
      console.error('清空图数据库失败:', error);
      message.error(error.response?.data?.detail || '清空失败');
    } finally {
      setLoading(false);
    }
  };

  const handleClearVector = async () => {
    try {
      setLoading(true);
      await api.post('/admin/knowledge/clear-vector');
      message.success('已清空向量数据库');
    } catch (error) {
      console.error('清空向量数据库失败:', error);
      message.error(error.response?.data?.detail || '清空失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Card
        title="景区管理"
        extra={
          <Space>
            <Popconfirm
              title="确定要清空图数据库吗？此操作不可恢复！"
              okText="确定"
              cancelText="取消"
              onConfirm={handleClearGraph}
            >
              <Button danger icon={<DeleteOutlined />} disabled={loading}>
                清空图数据库
              </Button>
            </Popconfirm>
            <Popconfirm
              title="确定要清空向量数据库吗？此操作不可恢复！"
              okText="确定"
              cancelText="取消"
              onConfirm={handleClearVector}
            >
              <Button danger icon={<DeleteOutlined />} disabled={loading}>
                清空向量数据库
              </Button>
            </Popconfirm>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setScenicEditing(null);
                scenicForm.resetFields();
                setScenicVisible(true);
              }}
            >
              新增景区
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                if (!selectedScenicId) {
                  message.error('请先在左侧选择一个景区');
                  return;
                }
                setKnowledgeVisible(true);
              }}
            >
              添加景区知识
            </Button>
            {selectedScenicId && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setAttractionVisible(true)}
              >
                添加景点
              </Button>
            )}
            <Button
              onClick={() => {
                if (!selectedScenic) {
                  message.error('请先选择一个景区');
                  return;
                }
                setScenicEditing(selectedScenic);
                scenicForm.setFieldsValue({
                  name: selectedScenic.name,
                  location: selectedScenic.location,
                  description: selectedScenic.description,
                  cover_image_url: selectedScenic.cover_image_url,
                });
                setScenicVisible(true);
              }}
              disabled={!selectedScenicId}
            >
              编辑景区
            </Button>
            <Popconfirm
              title="确定要删除当前景区吗？（若该景区下仍有知识/景点会阻止删除）"
              okText="删除"
              cancelText="取消"
              onConfirm={async () => {
                if (!selectedScenicId) return;
                try {
                  setLoading(true);
                  await api.delete(`/admin/scenic-spots/${selectedScenicId}`);
                  message.success('删除成功');
                  await loadScenicSpots(null);
                } catch (e) {
                  message.error(e.response?.data?.detail || '删除失败');
                } finally {
                  setLoading(false);
                }
              }}
              disabled={!selectedScenicId}
            >
              <Button danger disabled={!selectedScenicId}>
                删除景区
              </Button>
            </Popconfirm>
            <Popconfirm
              title="确定要级联删除当前景区吗？（会删除该景区下所有知识/景点，并清理图/向量）"
              okText="级联删除"
              cancelText="取消"
              onConfirm={async () => {
                if (!selectedScenicId) return;
                try {
                  setLoading(true);
                  await api.delete(`/admin/scenic-spots/${selectedScenicId}`, { params: { cascade: true } });
                  message.success('已级联删除');
                  await loadScenicSpots(null);
                } catch (e) {
                  message.error(e.response?.data?.detail || '级联删除失败');
                } finally {
                  setLoading(false);
                }
              }}
              disabled={!selectedScenicId}
            >
              <Button danger disabled={!selectedScenicId}>
                级联删除
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ width: 320 }}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>景区列表</div>
            <List
              bordered
              dataSource={scenicSpots}
              loading={loading}
              renderItem={(item) => (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    background: item.id === selectedScenicId ? '#f5f5f5' : 'transparent',
                  }}
                  onClick={() => setSelectedScenicId(item.id)}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ fontWeight: 600 }}>{item.name}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>
                      知识 {item.knowledge_count} / 景点 {item.attractions_count}
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </div>

          <div style={{ flex: 1 }}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>
              {selectedScenic ? `当前景区：${selectedScenic.name}` : '请选择景区'}
            </div>
            <Tabs
              items={[
                {
                  key: 'knowledge',
                  label: '景区总知识',
                  children: (
                    <Table
                      columns={knowledgeColumns}
                      dataSource={knowledgeData}
                      loading={loading}
                      rowKey="text_id"
                    />
                  ),
                },
                {
                  key: 'attractions',
                  label: '景点',
                  disabled: !selectedScenicId,
                  children: (
                    <Table
                      columns={[
                        { title: 'ID', dataIndex: 'id', key: 'id' },
                        { title: '名称', dataIndex: 'name', key: 'name' },
                        { title: '位置', dataIndex: 'location', key: 'location', ellipsis: true },
                        { title: '类别', dataIndex: 'category', key: 'category' },
                        {
                          title: '操作',
                          key: 'action',
                          render: (_, record) => (
                            <Popconfirm
                              title="确定要删除这个景点吗？"
                              onConfirm={async () => {
                                try {
                                  setLoading(true);
                                  await api.delete(`/admin/attractions/${record.id}`);
                                  message.success('删除成功');
                                  if (selectedScenicId) loadScenicAttractions(selectedScenicId);
                                } catch (e) {
                                  message.error(e.response?.data?.detail || '删除失败');
                                } finally {
                                  setLoading(false);
                                }
                              }}
                            >
                              <Button danger size="small">删 除</Button>
                            </Popconfirm>
                          ),
                        },
                      ]}
                      dataSource={attractionsData}
                      loading={loading}
                      rowKey="id"
                    />
                  ),
                },
              ]}
            />
          </div>
        </div>
      </Card>

      <Modal
        title={scenicEditing ? '编辑景区' : '新增景区'}
        open={scenicVisible}
        onCancel={() => setScenicVisible(false)}
        onOk={() => scenicForm.submit()}
        confirmLoading={loading}
      >
        <Form
          form={scenicForm}
          layout="vertical"
          onFinish={async (values) => {
            try {
              setLoading(true);
              if (scenicEditing?.id) {
                await api.put(`/admin/scenic-spots/${scenicEditing.id}`, values);
                message.success('更新成功');
                setScenicVisible(false);
                setScenicEditing(null);
                await loadScenicSpots(scenicEditing.id);
              } else {
                const res = await api.post('/admin/scenic-spots', values);
                message.success('创建成功');
                setScenicVisible(false);
                const newId = res.data?.id;
                await loadScenicSpots(newId || null);
              }
            } catch (e) {
              message.error(e.response?.data?.detail || '保存失败');
            } finally {
              setLoading(false);
            }
          }}
        >
          <Form.Item name="name" label="景区名称" rules={[{ required: true, message: '请输入景区名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="location" label="位置">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="简介">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="cover_image_url" label="封面图片">
            <Space.Compact style={{ width: '100%' }}>
              <Input placeholder="上传后自动填入 URL" readOnly />
              <Upload
                accept="image/*"
                showUploadList={false}
                customRequest={handleCoverUpload}
              >
                <Button icon={<UploadOutlined />}>上传</Button>
              </Upload>
            </Space.Compact>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="添加景区知识"
        open={knowledgeVisible}
        onCancel={() => setKnowledgeVisible(false)}
        onOk={() => knowledgeForm.submit()}
        confirmLoading={loading}
      >
        <Form
          form={knowledgeForm}
          layout="vertical"
          onFinish={handleSubmitKnowledge}
        >
          <Form.Item
            name="text_id"
            label="知识ID"
          >
            <Input placeholder="留空自动生成" />
          </Form.Item>
          <Form.Item
            name="text"
            label="知识内容"
            rules={[{ required: true, message: '请输入知识内容' }]}
          >
            <Input.TextArea rows={6} placeholder="输入知识内容..." />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="添加景点"
        open={attractionVisible}
        onCancel={() => setAttractionVisible(false)}
        onOk={() => attractionForm.submit()}
        confirmLoading={loading}
      >
        <Form
          form={attractionForm}
          layout="vertical"
          onFinish={async (values) => {
            if (!selectedScenicId) {
              message.error('请先选择一个景区');
              return;
            }
            try {
              setLoading(true);
              await api.post(`/admin/scenic-spots/${selectedScenicId}/attractions`, values);
              message.success('创建成功');
              setAttractionVisible(false);
              attractionForm.resetFields();
              loadScenicAttractions(selectedScenicId);
            } catch (e) {
              message.error(e.response?.data?.detail || '创建失败');
            } finally {
              setLoading(false);
            }
          }}
        >
          <Form.Item name="name" label="景点名称" rules={[{ required: true, message: '请输入景点名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述" rules={[{ required: true, message: '请输入景点描述' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="location" label="位置">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="类别">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default KnowledgeBase;

