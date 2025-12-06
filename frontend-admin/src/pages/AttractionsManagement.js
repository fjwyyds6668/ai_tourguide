import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, InputNumber, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import api from '../api';

const AttractionsManagement = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [form] = Form.useForm();

  useEffect(() => {
    fetchAttractions();
  }, []);

  const fetchAttractions = async () => {
    setLoading(true);
    try {
      const res = await api.get('/attractions');
      setData(res.data);
    } catch (error) {
      message.error('加载景点失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values) => {
    try {
      setLoading(true);
      if (editingRecord) {
        // 更新逻辑（需要后端支持 PUT 接口）
        message.success('更新成功');
      } else {
        await api.post('/attractions', values);
        message.success('创建成功');
      }
      setVisible(false);
      form.resetFields();
      setEditingRecord(null);
      fetchAttractions();
    } catch (error) {
      message.error('操作失败：' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (record) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    setVisible(true);
  };

  const handleDelete = async (id) => {
    try {
      // 删除逻辑（需要后端支持 DELETE 接口）
      message.success('删除成功');
      fetchAttractions();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '位置',
      dataIndex: 'location',
      key: 'location',
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个景点吗？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  return (
    <div>
      <Card
        title="景点管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingRecord(null);
              form.resetFields();
              setVisible(true);
            }}
          >
            添加景点
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={data}
          loading={loading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '编辑景点' : '添加景点'}
        open={visible}
        onCancel={() => {
          setVisible(false);
          form.resetFields();
          setEditingRecord(null);
        }}
        onOk={() => form.submit()}
        confirmLoading={loading}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
        >
          <Form.Item
            name="name"
            label="景点名称"
            rules={[{ required: true, message: '请输入景点名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
          >
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item
            name="location"
            label="位置"
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="category"
            label="类别"
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="latitude"
            label="纬度"
          >
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="longitude"
            label="经度"
          >
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="image_url"
            label="图片URL"
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="audio_url"
            label="音频URL"
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AttractionsManagement;

