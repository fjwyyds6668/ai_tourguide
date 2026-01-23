import React, { useState, useEffect } from 'react';
import { Card, Button, Table, Modal, Form, Input, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../api';

const KnowledgeBase = () => {
  const [visible, setVisible] = useState(false);
  const [form] = Form.useForm();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  // 加载知识库数据
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      // 这里需要根据实际API调整
      // 如果API已实现，取消下面的注释
      // const response = await api.get('/admin/knowledge/list');
      // setData(response.data || []);
      
      // 临时使用空数组，避免 ESLint 警告
      setData([]);
    } catch (error) {
      console.error('加载数据失败:', error);
      setData([]); // 出错时也设置空数组
    } finally {
      setLoading(false);
    }
  };

  const columns = [
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
        <Button danger size="small">删除</Button>
      ),
    },
  ];

  const handleSubmit = async (values) => {
    try {
      setLoading(true);
      await api.post('/admin/knowledge/upload', [{
        text: values.text,
        text_id: values.text_id || `kb_${Date.now()}`,
        metadata: {}
      }]);
      message.success('上传成功');
      setVisible(false);
      form.resetFields();
      loadData(); // 重新加载数据
    } catch (error) {
      message.error('上传失败：' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Card
        title="知识库管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setVisible(true)}
          >
            添加知识
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={data}
          loading={loading}
          rowKey="text_id"
        />
      </Card>

      <Modal
        title="添加知识"
        open={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
        confirmLoading={loading}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
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
    </div>
  );
};

export default KnowledgeBase;

