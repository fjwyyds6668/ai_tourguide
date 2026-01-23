# 阿里云数字人 WebSDK 集成指南

## 概述

本项目已集成阿里云数字人 WebSDK，支持数字人形象展示、语音播报和互动对话功能。

## 配置步骤

### 1. 获取阿里云数字人服务凭证

1. 登录 [阿里云控制台](https://ecs.console.aliyun.com/)
2. 开通数字人服务
3. 获取以下信息：
   - AccessKey ID
   - AccessKey Secret
   - App ID
   - Avatar ID（数字人形象ID）

### 2. 配置环境变量

在 `frontend-tourist` 目录下创建 `.env` 文件：

```env
VITE_ALIYUN_AVATAR_ACCESS_KEY_ID=your_access_key_id
VITE_ALIYUN_AVATAR_ACCESS_KEY_SECRET=your_access_key_secret
VITE_ALIYUN_AVATAR_APP_ID=your_app_id
```

### 3. SDK 引入

SDK 已通过 CDN 方式引入，在 `index.html` 中：

```html
<script src="https://g.alicdn.com/cloudavatar/web-sdk/1.0.0/index.js"></script>
```

## 功能说明

### 数字人组件 (`DigitalAvatar.vue`)

主要功能：
- 数字人形象展示
- 文本播报（speak）
- 停止播报（stop）
- 表情控制（setExpression）
- 动作控制（setAction）

### 语音导览页面 (`VoiceGuide.vue`)

集成功能：
- ✅ 角色选择（支持多个数字人角色）
- ✅ 语音识别（ASR）
- ✅ 多轮对话（基于会话ID）
- ✅ 数字人播报（TTS）
- ✅ 对话历史记录
- ✅ 历史记录查看

## 使用流程

1. **选择角色**：在语音导览页面选择数字人角色
2. **开始对话**：点击"开始录音"按钮
3. **语音输入**：说出您的问题
4. **AI回复**：系统识别语音，通过GraphRAG检索生成回答
5. **数字人播报**：数字人自动播报AI回复内容
6. **查看历史**：点击"查看历史"查看对话记录

## API 接口

### 角色管理
- `GET /api/v1/characters/characters` - 获取角色列表
- `GET /api/v1/characters/characters/{id}` - 获取角色详情

### 对话生成
- `POST /api/v1/rag/generate` - 生成回答（支持多轮对话）
  ```json
  {
    "query": "用户问题",
    "session_id": "会话ID（可选）",
    "character_id": "角色ID（可选）",
    "use_rag": true
  }
  ```

### 历史记录
- `GET /api/v1/history/history` - 获取历史记录
- `GET /api/v1/history/history/{session_id}` - 获取指定会话历史

## 注意事项

1. **SDK 加载**：确保网络可以访问阿里云 CDN
2. **权限配置**：确保阿里云账号有数字人服务权限
3. **浏览器兼容**：建议使用 Chrome、Edge 等现代浏览器
4. **HTTPS**：生产环境建议使用 HTTPS（某些浏览器功能需要）

## 故障排查

### 数字人无法加载
- 检查环境变量配置是否正确
- 检查网络连接和CDN访问
- 查看浏览器控制台错误信息

### 语音识别失败
- 检查麦克风权限
- 确认浏览器支持 WebRTC
- 检查后端语音识别服务是否正常

### 数字人无法播报
- 检查数字人是否已就绪（avatarReady）
- 查看控制台是否有错误信息
- 确认文本内容不为空

## 开发说明

### 组件结构
```
frontend-tourist/
├── src/
│   ├── components/
│   │   └── DigitalAvatar.vue      # 数字人组件
│   ├── composables/
│   │   └── useAvatar.js           # 数字人 Hook
│   └── views/
│       ├── VoiceGuide.vue         # 语音导览页面
│       └── History.vue            # 历史记录页面
```

### 自定义配置

如需修改数字人配置，编辑 `VoiceGuide.vue` 中的 `avatarConfig`：

```javascript
const avatarConfig = ref({
  accessKeyId: import.meta.env.VITE_ALIYUN_AVATAR_ACCESS_KEY_ID,
  accessKeySecret: import.meta.env.VITE_ALIYUN_AVATAR_ACCESS_KEY_SECRET,
  appId: import.meta.env.VITE_ALIYUN_AVATAR_APP_ID,
})
```

## 参考文档

- [阿里云数字人 WebSDK 文档](https://help.aliyun.com/document_detail/xxx.html)
- [Vue 3 官方文档](https://vuejs.org/)
- [Element Plus 文档](https://element-plus.org/)

