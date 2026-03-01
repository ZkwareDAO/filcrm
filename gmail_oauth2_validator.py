"""
Gmail OAuth2 邮件验证模块

功能：
1. 使用 Google OAuth2 认证连接 Gmail
2. 从 Gmail 收取邮件
3. 验证邮件内容（手机号、身份证、姓名）

使用方法：
    python gmail_oauth2_validator.py

配置 OAuth2:
    1. 访问 https://console.cloud.google.com/
    2. 创建新项目或选择现有项目
    3. 启用 Gmail API
    4. 创建 OAuth2 凭据
    5. 下载 client_secret.json 文件
"""

import re
import imaplib
import email
import base64
import json
import os
import webbrowser
import http.server
import socketserver
import threading
from email.message import Message
from email.header import decode_header
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error


# ==================== Google OAuth2 配置 ====================

# 使用 Google 官方 OAuth2 端点
GOOGLE_CLIENT_ID = "992041989314-hqj6c5s8vvfm2o9f4vvfm2o9f4vvfm2o.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "GOCSPX-abcdefghijklmnopqrstuvwx"  # 占位符，需要替换
GOOGLE_SCOPE = "https://mail.google.com/"
GOOGLE_REDIRECT_URI = "http://localhost:8080/"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


# ==================== 验证函数 ====================

def find_chinese_mobile_numbers(text: str) -> List[str]:
    """在输入文本中搜索中国大陆有效手机号码"""
    pattern = r'\b1[3-9]\d{9}\b'
    matches = re.findall(pattern, text)
    return matches


def validate_mobile_number(phone: str) -> bool:
    """验证手机号码是否有效"""
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def find_id_card_numbers(text: str) -> List[str]:
    """在文本中查找中国居民身份证号码"""
    pattern_18 = r'\b\d{17}[\dXx]\b'
    pattern_15 = r'\b\d{15}\b'

    matches_18 = re.findall(pattern_18, text, re.IGNORECASE)
    matches_15 = re.findall(pattern_15, text)

    return matches_18 + matches_15


def validate_id_card_number(id_card: str) -> bool:
    """验证身份证号码是否有效"""
    id_card = id_card.upper().strip()

    if len(id_card) == 18:
        if not id_card[:17].isdigit():
            return False
        if not (id_card[17].isdigit() or id_card[17] == 'X'):
            return False

        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

        total = sum(int(id_card[i]) * weights[i] for i in range(17))
        check_code = check_codes[total % 11]
        return check_code == id_card[17]

    elif len(id_card) == 15:
        return id_card.isdigit()

    return False


def find_name(text: str) -> Optional[str]:
    """在文本中查找姓名"""
    patterns = [
        r'姓名\s*[:：]\s*([\u4e00-\u9fa5]{2,4})',
        r'名字\s*[:：]\s*([\u4e00-\u9fa5]{2,4})',
        r'联系人\s*[:：]\s*([\u4e00-\u9fa5]{2,4})',
        r'称呼\s*[:：]\s*([\u4e00-\u9fa5]{2,4})',
        r'我叫\s*([\u4e00-\u9fa5]{2,4})',
        r'本人\s*([\u4e00-\u9fa5]{2,4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_text_from_email(msg: Message) -> str:
    """从邮件消息中提取纯文本内容"""
    text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        text += payload.decode(charset, errors='ignore')
                except Exception:
                    pass
            elif content_type == "text/html":
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_text = payload.decode(charset, errors='ignore')
                        clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                        text += clean_text
                except Exception:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(charset, errors='ignore')
        except Exception:
            pass

    return text


def decode_mime_word(s: str) -> str:
    """解码 MIME 编码的字符串"""
    decoded_parts = decode_header(s)
    result = ""
    for content, encoding in decoded_parts:
        if isinstance(content, bytes):
            if encoding:
                result += content.decode(encoding, errors='ignore')
            else:
                result += content.decode('utf-8', errors='ignore')
        else:
            result += content
    return result


def validate_email_content(email_text: str) -> Dict[str, Any]:
    """验证邮件内容，检查手机号、身份证和姓名"""
    result = {
        'valid': True,
        'errors': [],
        'mobile_phone': None,
        'id_card': None,
        'name': None,
    }

    mobile_numbers = find_chinese_mobile_numbers(email_text)

    if len(mobile_numbers) == 0:
        result['valid'] = False
        result['errors'].append('未找到手机号码')
    elif len(mobile_numbers) > 1:
        result['valid'] = False
        result['errors'].append(f'找到多个手机号码 ({len(mobile_numbers)} 个): {", ".join(mobile_numbers)}')
    else:
        if validate_mobile_number(mobile_numbers[0]):
            result['mobile_phone'] = mobile_numbers[0]
        else:
            result['valid'] = False
            result['errors'].append(f'手机号码格式无效：{mobile_numbers[0]}')

    id_cards = find_id_card_numbers(email_text)

    if len(id_cards) == 0:
        result['valid'] = False
        result['errors'].append('未找到身份证号码')
    elif len(id_cards) > 1:
        result['valid'] = False
        result['errors'].append(f'找到多个身份证号码 ({len(id_cards)} 个): {", ".join(id_cards)}')
    else:
        if validate_id_card_number(id_cards[0]):
            result['id_card'] = id_cards[0].upper()
        else:
            result['valid'] = False
            result['errors'].append(f'身份证号码无效：{id_cards[0]}')

    name = find_name(email_text)
    if name:
        result['name'] = name
    else:
        result['valid'] = False
        result['errors'].append('未找到姓名')

    return result


# ==================== OAuth2 认证处理 ====================

class OAuth2CallbackHandler(http.server.BaseHTTPRequestHandler):
    """处理 OAuth2 回调的 HTTP 服务器"""
    code = None
    error = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'code' in params:
            self.code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            response = '''
                <html><head><title>认证成功</title>
                <style>body{font-family:sans-serif;text-align:center;padding:50px;}</style>
                </head>
                <body>
                    <h1 style="color:green;">认证成功!</h1>
                    <p>您可以关闭此窗口，返回应用程序继续操作。</p>
                    <script>window.close()</script>
                </body></html>
            '''
            self.wfile.write(response.encode('utf-8'))
        elif 'error' in params:
            self.error = params.get('error_description', ['Unknown error'])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            response = f'''
                <html><head><title>认证失败</title>
                <style>body{font-family:sans-serif;text-align:center;padding:50px;}</style>
                </head>
                <body>
                    <h1 style="color:red;">认证失败!</h1>
                    <p>错误：{self.error}</p>
                </body></html>
            '''
            self.wfile.write(response.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class GmailOAuth2Validator:
    """Gmail OAuth2 邮件验证器"""

    def __init__(self, email_address: str, client_id: str = None, client_secret: str = None,
                 access_token: str = None, refresh_token: str = None):
        """
        初始化 Gmail OAuth2 验证器

        Args:
            email_address: Gmail 邮箱地址
            client_id: Google Cloud OAuth2 客户端 ID
            client_secret: Google Cloud OAuth2 客户端密钥
            access_token: OAuth2 访问令牌（可选）
            refresh_token: OAuth2 刷新令牌（可选）
        """
        self.email_address = email_address
        self.client_id = client_id or GOOGLE_CLIENT_ID
        self.client_secret = client_secret or GOOGLE_CLIENT_SECRET
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
        self.redirect_port = 8080
        self._token_file = f".gmail_token_{email_address.replace('@', '_')}.json"
        self._creds_file = ".gmail_oauth2_creds.json"

    def _load_credentials(self) -> bool:
        """从文件加载 OAuth2 凭据"""
        try:
            if os.path.exists(self._creds_file):
                with open(self._creds_file, 'r') as f:
                    creds = json.load(f)
                self.client_id = creds.get('client_id', self.client_id)
                self.client_secret = creds.get('client_secret', self.client_secret)
                return True
        except Exception:
            pass
        return False

    def _save_credentials(self):
        """保存 OAuth2 凭据到文件"""
        creds = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        with open(self._creds_file, 'w') as f:
            json.dump(creds, f, indent=2)

    def _load_tokens(self) -> bool:
        """从文件加载令牌"""
        try:
            if os.path.exists(self._token_file):
                with open(self._token_file, 'r') as f:
                    tokens = json.load(f)
                if tokens.get('email') == self.email_address:
                    self.access_token = tokens['access_token']
                    self.refresh_token = tokens.get('refresh_token')
                    return True
        except Exception:
            pass
        return False

    def _save_tokens(self):
        """保存令牌到文件"""
        if self.access_token:
            tokens = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'email': self.email_address,
                'scope': GOOGLE_SCOPE
            }
            with open(self._token_file, 'w') as f:
                json.dump(tokens, f, indent=2)

    def _exchange_code(self, code: str) -> Dict[str, Any]:
        """使用授权码换取访问令牌"""
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': f'http://localhost:{self.redirect_port}',
        }

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=urllib.parse.urlencode(data).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise Exception(f"Token exchange failed: {error_body}")

    def _refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            return False

        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token',
        }

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=urllib.parse.urlencode(data).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                token_data = json.loads(response.read().decode())
                self.access_token = token_data.get('access_token')
                self._save_tokens()
                return True
        except Exception as e:
            print(f"刷新令牌失败：{e}")
            return False

    def authenticate(self) -> bool:
        """执行 OAuth2 认证流程"""
        print("\n" + "=" * 60)
        print("Gmail OAuth2 认证")
        print("=" * 60)

        # 尝试加载已保存的凭据
        self._load_credentials()

        # 尝试加载已保存的令牌
        if self._load_tokens():
            print("已找到已保存的令牌")
            # 尝试刷新令牌
            if self._refresh_access_token():
                print("令牌刷新成功!")
                return True
            print("令牌已过期，需要重新认证")

        print("\n即将启动 OAuth2 认证流程...")
        print("1. 浏览器将自动打开 Google 登录页面")
        print("2. 登录并授权应用访问您的 Gmail")
        print("3. 认证完成后会自动返回")
        print()

        # 生成授权 URL
        import secrets
        state = secrets.token_urlsafe(16)

        params = {
            'client_id': self.client_id,
            'redirect_uri': f'http://localhost:{self.redirect_port}',
            'response_type': 'code',
            'scope': GOOGLE_SCOPE,
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent',
            'login_hint': self.email_address,
        }
        query = '&'.join([f'{k}={urllib.parse.quote(v)}' for k, v in params.items()])
        auth_url = f"{GOOGLE_AUTH_URL}?{query}"

        print(f"如果浏览器未自动打开，请访问:")
        print(f"{auth_url}\n")

        # 启动本地服务器接收回调
        auth_code = [None]
        auth_error = [None]
        received_state = [None]

        class Handler(OAuth2CallbackHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                if 'state' in params:
                    received_state[0] = params['state'][0]
                super().do_GET()
                auth_code[0] = self.code
                auth_error[0] = self.error

        server_thread = None
        try:
            with socketserver.TCPServer(("", self.redirect_port), Handler) as httpd:
                server_thread = threading.Thread(target=httpd.handle_request, daemon=True)
                server_thread.start()

                # 打开浏览器
                webbrowser.open(auth_url)

                # 等待回调（最多 2 分钟）
                start_time = threading.Event()
                def wait_for_callback():
                    server_thread.join(timeout=120)
                    start_time.set()
                wait_for_callback()

                if auth_error[0]:
                    print(f"认证失败：{auth_error[0]}")
                    return False

                if not auth_code[0]:
                    print("认证超时")
                    return False

                if received_state[0] and received_state[0] != state:
                    print("警告：state 不匹配，可能存在 CSRF 攻击")

                # 换取令牌
                print("正在获取访问令牌...")
                try:
                    token_response = self._exchange_code(auth_code[0])

                    if 'access_token' in token_response:
                        self.access_token = token_response['access_token']
                        self.refresh_token = token_response.get('refresh_token')
                        print("认证成功!")

                        # 保存令牌
                        self._save_tokens()

                        # 保存凭据
                        self._save_credentials()

                        return True
                    else:
                        print(f"获取令牌失败：{token_response}")
                        return False
                except Exception as e:
                    print(f"错误：{e}")
                    return False

        except OSError as e:
            print(f"无法启动本地服务器（端口 {self.redirect_port} 可能被占用）: {e}")
            print("\n手动认证方法:")
            print(f"1. 在浏览器中打开：{auth_url}")
            print("2. 授权后复制回调 URL 中的 code 参数")
            code = input("3. 输入授权码：").strip()
            if code:
                try:
                    token_response = self._exchange_code(code)
                    if 'access_token' in token_response:
                        self.access_token = token_response['access_token']
                        self.refresh_token = token_response.get('refresh_token')
                        self._save_tokens()
                        self._save_credentials()
                        print("认证成功!")
                        return True
                except Exception as e:
                    print(f"错误：{e}")
            return False

    def connect(self) -> imaplib.IMAP4_SSL:
        """使用 OAuth2 连接到 Gmail IMAP 服务器"""
        # 尝试加载已保存的令牌
        if not self.access_token:
            self._load_tokens()
            if self.refresh_token:
                if not self._refresh_access_token():
                    self.access_token = None

        # 如果没有令牌，执行认证
        if not self.access_token:
            if not self.authenticate():
                raise Exception("OAuth2 认证失败")

        # 使用 OAuth2 登录
        imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)

        # XOAUTH2 认证
        auth_string = f'user={self.email_address}\1auth=Bearer {self.access_token}\1\1'
        imap.authenticate('XOAUTH2', lambda x: auth_string)

        return imap

    def test_connection(self) -> bool:
        """测试 OAuth2 连接"""
        try:
            print("正在连接 Gmail...")
            imap = self.connect()
            print("连接成功!")

            imap.select('INBOX')
            status, count = imap.search(None, 'ALL')
            if status == 'OK':
                emails = len(count[0].split()) if count[0] else 0
                print(f"收件箱邮件数：{emails}")

            status, unread = imap.search(None, 'UNSEEN')
            if status == 'OK':
                unread_count = len(unread[0].split()) if unread[0] else 0
                print(f"未读邮件数：{unread_count}")

            imap.close()
            imap.logout()
            return True
        except Exception as e:
            print(f"连接失败：{e}")
            return False

    def fetch_unread_emails(self, folder: str = "INBOX", limit: int = 10) -> List[Dict[str, Any]]:
        """获取未读邮件"""
        results = []
        imap = self.connect()

        try:
            imap.select(folder)
            status, messages = imap.search(None, "UNSEEN")

            if status == "OK":
                email_ids = messages[0].split()
                email_ids = email_ids[-limit:]

                for email_id in reversed(email_ids):
                    try:
                        status, msg_data = imap.fetch(email_id, "(RFC822)")

                        if status == "OK":
                            for response_part in msg_data:
                                if isinstance(response_part, tuple):
                                    msg = email.message_from_bytes(response_part[1])

                                    subject = msg.get("Subject", "")
                                    subject = decode_mime_word(subject)
                                    body = extract_text_from_email(msg)

                                    results.append({
                                        'id': email_id.decode(),
                                        'subject': subject,
                                        'from': decode_mime_word(msg.get("From", "")),
                                        'date': msg.get("Date", ""),
                                        'body': body,
                                    })
                                    break
                    except Exception as e:
                        print(f"处理邮件 {email_id} 时出错：{e}")

        finally:
            imap.close()
            imap.logout()

        return results

    def validate_all_unread(self, folder: str = "INBOX", limit: int = 10) -> List[Dict[str, Any]]:
        """验证所有未读邮件"""
        emails = self.fetch_unread_emails(folder, limit)
        results = []

        for email_info in emails:
            validation_result = validate_email_content(email_info['body'])
            validation_result['subject'] = email_info['subject']
            validation_result['from'] = email_info['from']
            validation_result['email_id'] = email_info['id']
            validation_result['date'] = email_info['date']
            results.append(validation_result)

        return results

    def clear_tokens(self):
        """清除已保存的令牌"""
        if os.path.exists(self._token_file):
            os.remove(self._token_file)
            print(f"已清除令牌文件：{self._token_file}")
        if os.path.exists(self._creds_file):
            os.remove(self._creds_file)
            print(f"已清除凭据文件：{self._creds_file}")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("=" * 60)
    print("Gmail OAuth2 邮件验证")
    print("=" * 60)

    # 配置
    email_address = input("\n输入 Gmail 邮箱地址：").strip()
    if not email_address:
        email_address = "metacqf@gmail.com"

    # 可选：加载 client_secret.json
    client_id = None
    client_secret = None

    if os.path.exists("client_secret.json"):
        print("\n找到 client_secret.json，使用其中的凭据")
        with open("client_secret.json", 'r') as f:
            creds_data = json.load(f)
            # 处理不同的 JSON 格式
            if 'web' in creds_data:
                client_id = creds_data['web'].get('client_id')
                client_secret = creds_data['web'].get('client_secret')
            elif 'installed' in creds_data:
                client_id = creds_data['installed'].get('client_id')
                client_secret = creds_data['installed'].get('client_secret')

    # 创建验证器
    validator = GmailOAuth2Validator(
        email_address=email_address,
        client_id=client_id,
        client_secret=client_secret
    )

    # 测试连接
    print("\n" + "=" * 60)
    print("测试连接")
    print("=" * 60)

    if not validator.test_connection():
        print("\n连接失败，请检查:")
        print("  1. 网络连接")
        print("  2. OAuth2 凭据是否正确")
        print("  3. 是否已授权应用访问 Gmail")
        print("\n清除令牌重试：python gmail_oauth2_validator.py --clear")
        return

    # 获取并验证邮件
    print("\n" + "=" * 60)
    print("获取并验证邮件")
    print("=" * 60)

    results = validator.validate_all_unread(limit=10)

    if not results:
        print("\n没有未读邮件")
        return

    print(f"\n找到 {len(results)} 封未读邮件\n")

    for i, result in enumerate(results, 1):
        print(f"--- 邮件 {i} ---")
        print(f"主题：{result['subject']}")
        print(f"发件人：{result['from']}")
        print(f"日期：{result['date']}")
        print(f"验证：{'通过' if result['valid'] else '失败'}")

        if result['mobile_phone']:
            print(f"手机号：{result['mobile_phone']}")
        if result['id_card']:
            print(f"身份证：{result['id_card']}")
        if result['name']:
            print(f"姓名：{result['name']}")
        if result['errors']:
            print(f"错误：{', '.join(result['errors'])}")
        print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--clear':
        # 清除令牌
        email_addr = input("输入要清除令牌的邮箱：").strip()
        if email_addr:
            token_file = f".gmail_token_{email_addr.replace('@', '_')}.json"
            creds_file = ".gmail_oauth2_creds.json"
            if os.path.exists(token_file):
                os.remove(token_file)
                print(f"已清除：{token_file}")
            if os.path.exists(creds_file):
                os.remove(creds_file)
                print(f"已清除：{creds_file}")
        sys.exit(0)

    main()
