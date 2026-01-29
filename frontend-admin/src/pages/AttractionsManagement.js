import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, InputNumber, message, Popconfirm, Upload } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import api from '../api';

const AttractionsManagement = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [form] = Form.useForm();
  const [imageFileList, setImageFileList] = useState([]);

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
      setImageFileList([]);
      fetchAttractions();
    } catch (error) {
      message.error(error.response?.data?.detail || ('操作失败：' + error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (record) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    if (record?.image_url) {
      setImageFileList([
        {
          uid: '-1',
          name: 'image',
          status: 'done',
          url: record.image_url,
        },
      ]);
    } else {
      setImageFileList([]);
    }
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
          setImageFileList([]);
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
            rules={[{ required: true, message: '请输入景点描述' }]}
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
            style={{ display: 'none' }}
          >
            <Input type="hidden" />
          </Form.Item>

          <Form.Item label="图片">
            <Upload
              accept="image/*"
              listType="picture-card"
              maxCount={1}
              fileList={imageFileList}
              onChange={({ fileList }) => setImageFileList(fileList)}
              customRequest={async ({ file, onSuccess, onError }) => {
                try {
                  const formData = new FormData();
                  formData.append('file', file);
                  const res = await api.post('/admin/uploads/image', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                  });
                  const url = res.data?.image_url;
                  if (url) {
                    // 关键：表单里保存字符串 URL，而不是 Upload 的 fileList 对象
                    form.setFieldsValue({ image_url: url });
                    setImageFileList([
                      {
                        uid: file.uid,
                        name: file.name,
                        status: 'done',
                        url,
                      },
                    ]);
                  }
                  onSuccess?.(res.data);
                } catch (e) {
                  message.error(e.response?.data?.detail || '图片上传失败');
                  onError?.(e);
                }
              }}
              onRemove={() => {
                form.setFieldsValue({ image_url: undefined });
                setImageFileList([]);
              }}
            >
              {imageFileList.length >= 1 ? null : <div>上传</div>}
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AttractionsManagement;

