import React, { useState, useEffect } from 'react';
import { Card, Table, Row, Col, Statistic, Tag } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import api from '../api';

const Analytics = () => {
  const [interactionData, setInteractionData] = useState(null);
  const [popularData, setPopularData] = useState(null);
  const [ragLogs, setRagLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const [interactionsRes, popularRes, ragRes] = await Promise.all([
        api.get('/admin/analytics/interactions'),
        api.get('/admin/analytics/popular-attractions'),
        api.get('/admin/analytics/rag-logs'),
      ]);
      setInteractionData(interactionsRes.data);
      setPopularData(popularRes.data);
      setRagLogs(ragRes.data || []);
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

  const ragColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
    },
    {
      title: '是否使用RAG',
      dataIndex: 'use_rag',
      key: 'use_rag',
      width: 100,
      render: (v) => (v ? <Tag color="green">RAG</Tag> : <Tag>Direct</Tag>),
    },
    {
      title: '用户问题',
      dataIndex: 'query',
      key: 'query',
      width: 260,
      ellipsis: true,
    },
    {
      title: 'RAG 检索&上下文',
      key: 'rag_context',
      align: 'left',
      render: (_, row) => {
        const debug = row?.rag_debug || {};
        const vectorResults = debug.vector_results || [];
        const graphResults = debug.graph_results || [];
        const ctx = debug.enhanced_context || '';

        const renderVector = () => {
          if (!vectorResults.length) {
            return <div style={{ color: '#999' }}>（无向量检索结果）</div>;
          }
          return (
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              {vectorResults.slice(0, 5).map((r, idx) => (
                <li key={idx}>
                  <span>
                    text_id: <code>{r.text_id}</code>，相似度: {(r.score ?? 0).toFixed(2)}
                  </span>
                </li>
              ))}
            </ol>
          );
        };

        const renderGraph = () => {
          if (!graphResults.length) {
            return <div style={{ color: '#999' }}>（无图数据库检索结果）</div>;
          }
          return (
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              {graphResults.slice(0, 5).map((r, idx) => {
                const a = r.a || r['a'] || {};
                const b = r.b || r['b'] || {};
                const rel = r.rel_type || r['rel_type'] || '关联';
                const aName = a.name || (a.properties && a.properties.name) || '节点A';
                const bName = b.name || (b.properties && b.properties.name) || '节点B';
                const arrow = '→';
                return (
                  <li key={idx}>
                    {aName} [{rel}] {arrow} {bName}
                  </li>
                );
              })}
            </ul>
          );
        };

        const fullContext = debug.final_sent_to_llm || ctx;
        const renderFullContext = () => {
          if (!fullContext) return <div style={{ color: '#999' }}>（未构造上下文或未使用 RAG）</div>;
          return (
            <div
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                marginTop: 4,
                padding: 8,
                background: '#fafafa',
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              {fullContext}
            </div>
          );
        };

        return (
          <div
            style={{
              maxHeight: 400,
              overflowY: 'auto',
              fontSize: 13,
            }}
          >
            <div style={{ marginBottom: 8 }}>
              <strong>① 向量数据库命中（Milvus）</strong>
              {renderVector()}
            </div>
            <div style={{ marginBottom: 8 }}>
              <strong>② 图数据库命中（Neo4j）</strong>
              {renderGraph()}
            </div>
            <div>
              <strong>③ 组装后传给 LLM 的完整信息</strong>
              {renderFullContext()}
            </div>
            <div style={{ marginTop: 8 }}>
              <strong>④ 大模型回复</strong>
              <div
                style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  marginTop: 4,
                  color: row.final_answer_preview ? '#333' : '#999',
                }}
              >
                {row.final_answer_preview || '（本次未记录回复预览）'}
              </div>
            </div>
          </div>
        );
      },
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
        </Row>
      )}

      <Card
        title="热门景点"
        extra={popularData?.visit_count_note ? (
          <span style={{ fontSize: 12, color: '#666' }}>{popularData.visit_count_note}</span>
        ) : null}
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={popularColumns}
          dataSource={popularData?.popular_attractions || []}
          loading={loading}
          rowKey="id"
        />
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

      <Card title="RAG 检索上下文日志（传给 LLM 的信息）" style={{ marginTop: 24 }}>
        <Table
          columns={ragColumns}
          dataSource={ragLogs}
          loading={loading}
          rowKey={(row) => `${row.timestamp}-${row.query.slice(0, 20)}`}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  );
};

export default Analytics;

