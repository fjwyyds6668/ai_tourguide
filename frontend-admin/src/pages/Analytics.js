import React, { useState, useEffect } from 'react';
import { Card, Table, Row, Col, Statistic } from 'antd';
import { MessageOutlined, EnvironmentOutlined } from '@ant-design/icons';
import api from '../api';

const Analytics = () => {
  const [interactionData, setInteractionData] = useState(null);
  const [popularData, setPopularData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const [interactionsRes, popularRes] = await Promise.all([
        api.get('/admin/analytics/interactions'),
        api.get('/admin/analytics/popular-attractions')
      ]);
      setInteractionData(interactionsRes.data);
      setPopularData(popularRes.data);
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
    } finally {
      setLoading(false);
    }
  };

  const interactionColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: '会话ID',
      dataIndex: 'session_id',
      key: 'session_id',
    },
    {
      title: '查询内容',
      dataIndex: 'query_text',
      key: 'query_text',
      ellipsis: true,
    },
    {
      title: '交互类型',
      dataIndex: 'interaction_type',
      key: 'interaction_type',
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
    },
  ];

  const popularColumns = [
    {
      title: '景点ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: '景点名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '访问次数',
      dataIndex: 'visit_count',
      key: 'visit_count',
    },
  ];

  return (
    <div>
      <h1>数据分析</h1>
      
      {interactionData && (
        <Row gutter={16} style={{ marginTop: 24, marginBottom: 24 }}>
          <Col span={12}>
            <Card>
              <Statistic
                title="总交互次数"
                value={interactionData.total}
                prefix={<MessageOutlined />}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card>
              <Statistic
                title="热门景点数"
                value={popularData?.popular_attractions?.length || 0}
                prefix={<EnvironmentOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card title="交互类型统计" style={{ marginBottom: 24 }}>
        {interactionData?.by_type && (
          <Row gutter={16}>
            {Object.entries(interactionData.by_type).map(([type, count]) => (
              <Col span={6} key={type}>
                <Statistic title={type} value={count} />
              </Col>
            ))}
          </Row>
        )}
      </Card>

      <Card title="最近交互记录" style={{ marginBottom: 24 }}>
        <Table
          columns={interactionColumns}
          dataSource={interactionData?.recent_interactions || []}
          loading={loading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Card title="热门景点">
        <Table
          columns={popularColumns}
          dataSource={popularData?.popular_attractions || []}
          loading={loading}
          rowKey="id"
        />
      </Card>
    </div>
  );
};

export default Analytics;

