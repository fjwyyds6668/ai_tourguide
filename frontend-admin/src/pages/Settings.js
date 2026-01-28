import React, { useEffect, useState, useCallback } from 'react';
import { Card, Switch, Form, Input, Button, message, Space, Typography, Alert, Select } from 'antd';
import { SettingOutlined, SaveOutlined } from '@ant-design/icons';
import api from '../api';

const { Title, Text } = Typography;
const { Option } = Select;

const Settings = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState({
    // 线上：科大讯飞 TTS（WebSocket API）
    // 备用：本地 CosyVoice2（由后端 LOCAL_TTS_* 控制降级/强制）
    local_tts_enabled: false,
    local_tts_force: false,
    local_tts_engine: 'cosyvoice2',
    cosyvoice2_model_path: '',
    cosyvoice2_device: 'cpu',
    cosyvoice2_language: 'zh',
  });

  const fetchConfig = useCallback(async () => {
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
  }, [form]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = async (values) => {
    setSaving(true);
    try {
      await api.put('/admin/settings/tts', values);
      message.success('配置已保存（需要重启后端服务才能生效）');
      await fetchConfig();
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
          description="修改配置后需要重启后端服务才能生效。默认使用在线科大讯飞 TTS；当启用备用TTS后，在线服务失败会自动降级到本地 CosyVoice2（也可选择强制始终使用 CosyVoice2）。"
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
            label="启用备用TTS（本地 CosyVoice2）"
            name="local_tts_enabled"
            valuePropName="checked"
            tooltip="启用后，当在线 TTS（科大讯飞）失败（如鉴权失败、网络问题）时，会自动降级到本地 CosyVoice2 进行语音合成"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="强制使用备用TTS（CosyVoice2）"
            name="local_tts_force"
            valuePropName="checked"
            tooltip="启用后，将始终使用 CosyVoice2，不再尝试在线 TTS（科大讯飞）"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="备用TTS引擎"
            name="local_tts_engine"
            tooltip="当前仅支持 CosyVoice2（与后端保持一致）"
          >
            <Select disabled>
              <Option value="cosyvoice2">CosyVoice2</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="CosyVoice2 模型路径（可选）"
            name="cosyvoice2_model_path"
            tooltip="留空则由后端自动下载/使用缓存；也可填本地模型目录路径"
          >
            <Input placeholder="例如：CosyVoice/models 或留空" allowClear />
          </Form.Item>

          <Form.Item
            label="CosyVoice2 运行设备"
            name="cosyvoice2_device"
            tooltip="cpu/cuda（需要环境支持 CUDA 才能使用 cuda）"
          >
            <Select>
              <Option value="cpu">cpu</Option>
              <Option value="cuda">cuda</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="CosyVoice2 语言"
            name="cosyvoice2_language"
            tooltip="如 zh/en/ja 等（与后端支持范围保持一致）"
          >
            <Select>
              <Option value="zh">zh</Option>
              <Option value="en">en</Option>
              <Option value="ja">ja</Option>
            </Select>
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
            <Text>备用TTS（CosyVoice2）：</Text>
            <Text type={config.local_tts_enabled ? 'success' : 'secondary'}>
              {config.local_tts_enabled ? '已启用' : '未启用'}
            </Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>强制使用 CosyVoice2：</Text>
            <Text type={config.local_tts_force ? 'warning' : 'secondary'}>
              {config.local_tts_force ? '已启用' : '未启用'}
            </Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>备用引擎：</Text>
            <Text code>{config.local_tts_engine || 'cosyvoice2'}</Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>CosyVoice2模型路径：</Text>
            <Text code>{config.cosyvoice2_model_path || '未设置'}</Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>CosyVoice2设备：</Text>
            <Text code>{config.cosyvoice2_device || 'cpu'}</Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text>CosyVoice2语言：</Text>
            <Text code>{config.cosyvoice2_language || 'zh'}</Text>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default Settings;

