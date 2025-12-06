import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import { UserOutlined, EnvironmentOutlined, MessageOutlined } from '@ant-design/icons';

const Dashboard = () => {
  return (
    <div>
      <h1>仪表盘</h1>
      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="总用户数"
              value={1128}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="景点数量"
              value={45}
              prefix={<EnvironmentOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="交互次数"
              value={8932}
              prefix={<MessageOutlined />}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;

