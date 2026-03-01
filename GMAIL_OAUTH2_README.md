# Gmail OAuth2 使用指南

## 文件说明

- `gmail_oauth2_validator.py` - 主模块，支持 OAuth2 认证收取 Gmail
- `gmail_email_validator.py` - 基础版本，使用应用密码认证

## 快速开始

### 方法 1：自动浏览器认证（推荐）

```bash
python gmail_oauth2_validator.py
```

按提示输入 Gmail 邮箱地址，浏览器会自动打开进行授权。

### 方法 2：使用 client_secret.json

1. 在 Google Cloud Console 创建 OAuth2 凭据
2. 下载 `client_secret.json` 文件
3. 将文件放在脚本同一目录
4. 运行：
```bash
python gmail_oauth2_validator.py
```

## 获取 Google OAuth2 凭据

### 步骤 1：创建 Google Cloud 项目

1. 访问 https://console.cloud.google.com/
2. 点击"选择项目" → "新建项目"
3. 输入项目名称（如：Gmail Validator）
4. 点击"创建"

### 步骤 2：启用 Gmail API

1. 在左侧菜单选择 "API 和服务" → "库"
2. 搜索 "Gmail API"
3. 点击 "启用"

### 步骤 3：创建 OAuth2 凭据

1. 在左侧菜单选择 "API 和服务" → "凭据"
2. 点击 "创建凭据" → "OAuth 客户端 ID"
3. 如果是首次创建，需要先配置"同意屏幕"：
   - 用户类型选择"外部"
   - 填写应用名称、用户支持电子邮件
   - 开发者联系信息填写你的邮箱
   - 保存并继续

4. 创建 OAuth 客户端 ID：
   - 应用类型选择"Web 应用"
   - 名称：Gmail Validator
   - 已授权的重定向 URI：
     - 添加 `http://localhost:8080/`
   - 点击"创建"

5. 下载凭据：
   - 点击刚刚创建的客户端 ID
   - 复制"客户端 ID"和"客户端密钥"
   - 或点击"下载 JSON"保存为 `client_secret.json`

### 步骤 4：运行脚本

将 `client_secret.json` 放在脚本同一目录，然后运行：

```bash
python gmail_oauth2_validator.py
```

## 代码使用示例

```python
from gmail_oauth2_validator import GmailOAuth2Validator

# 创建验证器（首次使用会自动打开浏览器认证）
validator = GmailOAuth2Validator(
    email_address="your_email@gmail.com"
)

# 测试连接
validator.test_connection()

# 验证所有未读邮件
results = validator.validate_all_unread(limit=10)

for result in results:
    print(f"主题：{result['subject']}")
    print(f"发件人：{result['from']}")
    print(f"验证：{'通过' if result['valid'] else '失败'}")
    if result['mobile_phone']:
        print(f"手机：{result['mobile_phone']}")
    if result['name']:
        print(f"姓名：{result['name']}")
    print("-" * 40)
```

## 清除已保存的令牌

```bash
python gmail_oauth2_validator.py --clear
```

## 常见问题

### 1. 认证失败：redirect_uri_mismatch

确保在 Google Cloud Console 中添加的重定向 URI 与代码中的一致：
`http://localhost:8080/`

### 2. 端口被占用

修改代码中的 `self.redirect_port = 8080` 为其他端口

### 3. 令牌过期

脚本会自动刷新令牌，如果失败会重新进行认证

### 4. 需要输入验证码

如果是新设备登录，Google 可能会要求额外的安全验证

## 验证规则

- **手机号**: 必须是且只能是一个有效的中国大陆 11 位手机号（1[3-9]\d{9}）
- **身份证**: 必须是且只能是一个有效的 18 位或 15 位身份证号（含校验码验证）
- **姓名**: 支持多种格式（姓名：、名字：、联系人：、我叫、本人等）
