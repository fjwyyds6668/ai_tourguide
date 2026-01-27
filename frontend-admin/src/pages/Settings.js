import React, { useEffect, useState } from 'react';
import { Card, Switch, Form, Input, Button, message, Space, Typography, Alert } from 'antd';
import { SettingOutlined, SaveOutlined } from '@ant-design/icons';
import api from '../api';

const { Title, Text } = Typography;

const Settings = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState({
    local_tts_enabled: false,
    local_tts_force: false,
    paddlespeech_default_voice: 'fastspeech2_csmsc',
  });

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/settings/tts');
      setConfig(res.data);
      form.setFieldsValue(res.data);
    } catch (error) {
      console.error('Failed to fetch TTS config:', error);
      message.error('获取TTS配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (values) => {
    setSaving(true);
    try {
      await api.put('/admin/settings/tts', values);
      message.success('配置已保存（需要重启后端服务才能生效）');
      setConfig(values);
    } catch (error) {
      console.error('Failed to save TTS config:', error);
      message.error(error.response?.data?.detail || '保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Title level={2}>
        <SettingOutlined /> 系统设置
      </Title>

      <Card
        title="TTS 语音合成配置"
        style={{ marginTop: 24 }}
        loading={loading}
      >
        <Alert
          message="配置说明"
          description="修改配置后需要重启后端服务才能生效。保底TTS会在Edge TTS失败时自动切换到本地PaddleSpeech。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />

        <Form
          form={form}
          layout="vertical"
          initialValues={config}
          onFinish={handleSave}
        >
          <Form.Item
            label="启用保底TTS（本地PaddleSpeech）"
            name="local_tts_enabled"
            valuePropName="checked"
            tooltip="启用后，当Edge TTS失败（如403错误或网络问题）时，会自动降级到本地PaddleSpeech进行语音合成"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="强制使用本地TTS"
            name="local_tts_force"
            valuePropName="checked"
            tooltip="启用后，将始终使用本地PaddleSpeech，不再尝试Edge TTS"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="PaddleSpeech 默认音色"
            name="paddlespeech_default_voice"
            tooltip="PaddleSpeech的默认音色配置，例如：fastspeech2_csmsc"
          >
            <Input placeholder="fastspeech2_csmsc" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={saving}
              >
                保存配置
              </Button>
              <Button onClick={fetchConfig} disabled={loading}>
                刷新
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div style={{ marginTop: 24, padding: 16, background: '#f5f5f5', borderRadius: 4 }}>
          <Text strong>当前配置状态：</Text>
          <div style={{ marginTop: 8 }}>
            <Text>保底TTS：</Text>
            <Text type={config.local_tts_enabled ? 'success' : 'secondary'}>
              {config.local_tts_enabled ? '已启用' : '未启用'}
            </Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>强制本地TTS：</Text>
            <Text type={config.local_tts_force ? 'warning' : 'secondary'}>
              {config.local_tts_force ? '已启用' : '未启用'}
            </Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>默认音色：</Text>
            <Text code>{config.paddlespeech_default_voice}</Text>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default Settings;

