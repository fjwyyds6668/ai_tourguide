import React, { useEffect, useState } from 'react';
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
    local_tts_enabled: false,
    local_tts_force: false,
    local_tts_engine: 'paddlespeech',
    paddlespeech_default_voice: 'fastspeech2_csmsc',
    coqui_tts_model: 'tts_models/zh-CN/baker/tacotron2-DDC-GST',
    coqui_tts_speaker: null,
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
      // 保存后立即刷新配置，确保显示最新值
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
          description="修改配置后需要重启后端服务才能生效。保底TTS会在Edge TTS失败时自动切换到本地TTS（PaddleSpeech 或 Coqui TTS）。"
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
            label="启用保底TTS（本地TTS）"
            name="local_tts_enabled"
            valuePropName="checked"
            tooltip="启用后，当Edge TTS失败（如403错误或网络问题）时，会自动降级到本地TTS进行语音合成"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="强制使用本地TTS"
            name="local_tts_force"
            valuePropName="checked"
            tooltip="启用后，将始终使用本地TTS，不再尝试Edge TTS"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="本地TTS引擎"
            name="local_tts_engine"
            tooltip="选择本地TTS引擎：PaddleSpeech（中文优化）或 Coqui TTS（多语言支持）"
          >
            <Select>
              <Option value="paddlespeech">PaddleSpeech</Option>
              <Option value="coqui">Coqui TTS</Option>
            </Select>
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.local_tts_engine !== currentValues.local_tts_engine}
          >
            {({ getFieldValue }) => {
              const engine = getFieldValue('local_tts_engine');
              if (engine === 'paddlespeech') {
                return (
                  <Form.Item
                    label="PaddleSpeech 默认音色"
                    name="paddlespeech_default_voice"
                    tooltip="PaddleSpeech的默认音色配置，例如：fastspeech2_csmsc"
                  >
                    <Input placeholder="fastspeech2_csmsc" />
                  </Form.Item>
                );
              } else if (engine === 'coqui') {
                return (
                  <>
                    <Form.Item
                      label="Coqui TTS 模型"
                      name="coqui_tts_model"
                      tooltip="Coqui TTS模型名称，例如：tts_models/zh-CN/baker/tacotron2-DDC-GST（中文）或 tts_models/en/ljspeech/tacotron2-DDC（英文）"
                    >
                      <Input placeholder="tts_models/zh-CN/baker/tacotron2-DDC-GST" />
                    </Form.Item>
                    <Form.Item
                      label="Coqui TTS 说话人（可选）"
                      name="coqui_tts_speaker"
                      tooltip="某些Coqui TTS模型支持多说话人，可以指定说话人ID（留空使用默认）"
                    >
                      <Input placeholder="留空使用默认说话人" allowClear />
                    </Form.Item>
                  </>
                );
              }
              return null;
            }}
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
            <Text>本地TTS引擎：</Text>
            <Text code>{config.local_tts_engine || 'paddlespeech'}</Text>
          </div>
          {config.local_tts_engine === 'paddlespeech' && (
            <div style={{ marginTop: 4 }}>
              <Text>PaddleSpeech音色：</Text>
              <Text code>{config.paddlespeech_default_voice}</Text>
            </div>
          )}
          {config.local_tts_engine === 'coqui' && (
            <>
              <div style={{ marginTop: 4 }}>
                <Text>Coqui模型：</Text>
                <Text code>{config.coqui_tts_model || '未设置'}</Text>
              </div>
              {config.coqui_tts_speaker && (
                <div style={{ marginTop: 4 }}>
                  <Text>Coqui说话人：</Text>
                  <Text code>{config.coqui_tts_speaker}</Text>
                </div>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  );
};

export default Settings;

