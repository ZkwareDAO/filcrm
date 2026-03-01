"""
Outlook 邮件验证模块 (OAuth2 版本)

功能：
1. 从 Outlook 收取邮件
2. 在邮件正文中查找手机号码（必须且只能有一个有效的中国手机号）
3. 检查身份证号码（必须且只能有一个有效的身份证号）
4. 检查是否包含姓名

注意：Microsoft 已禁用基本认证，需要使用 OAuth2 认证
"""

import re
import imaplib
import email
from email.message import Message
from email.header import decode_header
from typing import Optional, Tuple, List, Dict, Any
import json
import base64
import hashlib
import secrets
import webbrowser
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import threading


# Microsoft Graph API 配置
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Microsoft 公共客户端 ID
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
REDIRECT_PORT = 8765


def find_chinese_mobile_numbers(text: str) -> List[str]:
    """
    在输入文本中搜索中国大陆有效手机号码

    条件:
    1. 11 位数字
    2. 以 1 开头
    3. 符合中国大陆手机号格式 (1[3-9]\\d{{9}})

    Args:
        text: 输入的文本字符串

    Returns:
        list: 匹配的手机号码列表
    """
    pattern = r'\b1[3-9]\d{9}\b'
    matches = re.findall(pattern, text)
    return matches


def validate_mobile_number(phone: str) -> bool:
    """
    验证手机号码是否有效

    Args:
        phone: 手机号码字符串

    Returns:
        bool: 是否有效
    """
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def find_id_card_numbers(text: str) -> List[str]:
    """
    在文本中查找中国居民身份证号码

    支持 18 位（含 X）和 15 位格式

    Args:
        text: 输入的文本字符串

    Returns:
        list: 匹配的身份证号码列表
    """
    # 18 位身份证：前 17 位数字，最后 1 位数字或 X
    pattern_18 = r'\b\d{17}[\dXx]\b'
    # 15 位身份证：15 位数字
    pattern_15 = r'\b\d{15}\b'

    matches_18 = re.findall(pattern_18, text, re.IGNORECASE)
    matches_15 = re.findall(pattern_15, text)

    return matches_18 + matches_15


def validate_id_card_number(id_card: str) -> bool:
    """
    验证身份证号码是否有效

    Args:
        id_card: 身份证号码字符串

    Returns:
        bool: 是否有效
    """
    id_card = id_card.upper().strip()

    # 18 位身份证验证
    if len(id_card) == 18:
        # 检查前 17 位是否都是数字
        if not id_card[:17].isdigit():
            return False

        # 检查最后一位
        if not (id_card[17].isdigit() or id_card[17] == 'X'):
            return False

        # 校验码验证
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

        total = sum(int(id_card[i]) * weights[i] for i in range(17))
        check_code = check_codes[total % 11]

        return check_code == id_card[17]

    # 15 位身份证验证（旧格式）
    elif len(id_card) == 15:
        return id_card.isdigit()

    return False


def find_name(text: str) -> Optional[str]:
    """
    在文本中查找姓名

    查找常见的姓名模式，如：
    - 姓名：XXX
    - 名字：XXX
    - 联系人：XXX
    - 称呼：XXX

    Args:
        text: 输入的文本字符串

    Returns:
        str or None: 找到的姓名，如果没有则返回 None
    """
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
    """
    从邮件消息中提取纯文本内容

    Args:
        msg: 邮件消息对象

    Returns:
        str: 提取的文本内容
    """
    text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            # 跳过附件
            if "attachment" in content_disposition:
                continue

            # 优先获取纯文本部分
            if content_type == "text/plain":
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        text += payload.decode(charset, errors='ignore')
                except Exception:
                    pass
            elif content_type == "text/html":
                # 如果没有纯文本，尝试获取 HTML 并提取文本
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_text = payload.decode(charset, errors='ignore')
                        # 简单的 HTML 标签清理
                        clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                        text += clean_text
                except Exception:
                    pass
    else:
        # 非多部分邮件
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(charset, errors='ignore')
        except Exception:
            pass

    return text


def decode_mime_word(s: str) -> str:
    """
    解码 MIME 编码的字符串

    Args:
        s: MIME 编码的字符串

    Returns:
        str: 解码后的字符串
    """
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
    """
    验证邮件内容，检查手机号、身份证和姓名

    Args:
        email_text: 邮件正文字符串

    Returns:
        dict: 验证结果
    """
    result = {
        'valid': True,
        'errors': [],
        'mobile_phone': None,
        'id_card': None,
        'name': None,
    }

    # 检查手机号码
    mobile_numbers = find_chinese_mobile_numbers(email_text)

    if len(mobile_numbers) == 0:
        result['valid'] = False
        result['errors'].append('未找到手机号码')
    elif len(mobile_numbers) > 1:
        result['valid'] = False
        result['errors'].append(f'找到多个手机号码 ({len(mobile_numbers)} 个): {", ".join(mobile_numbers)}')
    else:
        # 验证唯一的手机号码
        if validate_mobile_number(mobile_numbers[0]):
            result['mobile_phone'] = mobile_numbers[0]
        else:
            result['valid'] = False
            result['errors'].append(f'手机号码格式无效：{mobile_numbers[0]}')

    # 检查身份证号码
    id_cards = find_id_card_numbers(email_text)

    if len(id_cards) == 0:
        result['valid'] = False
        result['errors'].append('未找到身份证号码')
    elif len(id_cards) > 1:
        result['valid'] = False
        result['errors'].append(f'找到多个身份证号码 ({len(id_cards)} 个): {", ".join(id_cards)}')
    else:
        # 验证唯一的身份证号码
        if validate_id_card_number(id_cards[0]):
            result['id_card'] = id_cards[0].upper()
        else:
            result['valid'] = False
            result['errors'].append(f'身份证号码无效：{id_cards[0]}')

    # 检查姓名
    name = find_name(email_text)
    if name:
        result['name'] = name
    else:
        result['valid'] = False
        result['errors'].append('未找到姓名')

    return result


def generate_pkce() -> Tuple[str, str]:
    """生成 PKCE 代码挑战和验证器"""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


def get_auth_url(email: str, code_challenge: str) -> str:
    """生成授权 URL"""
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': f'http://localhost:{REDIRECT_PORT}',
        'scope': SCOPE,
        'response_mode': 'query',
        'prompt': 'select_account',
        'login_hint': email,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    query = '&'.join([f'{k}={v}' for k, v in params.items()])
    return f'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{query}'


def get_token_from_code(code: str, code_verifier: str, email: str) -> Dict[str, Any]:
    """使用授权码换取访问令牌"""
    import urllib.request
    import urllib.error
    import json

    token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = {
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': f'http://localhost:{REDIRECT_PORT}',
        'code_verifier': code_verifier,
        'scope': SCOPE,
    }

    req = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(data).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Token exchange failed: {error_body}")


class AuthHandler(http.server.BaseHTTPRequestHandler):
    """处理 OAuth2 回调的 HTTP 服务器"""
    code = None
    error = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'code' in params:
            self.code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = '''
                <html><head><title>Success</title></head>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                    <script>window.close()</script>
                </body></html>
            '''.encode('utf-8')
            self.wfile.write(html)
        elif 'error' in params:
            self.error = params.get('error_description', ['Unknown error'])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f'''
                <html><head><title>认证失败</title></head>
                <body>
                    <h1>认证失败!</h1>
                    <p>错误：{self.error}</p>
                </body></html>
            '''.encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默日志


class OutlookEmailValidator:
    """Outlook 邮件验证器 (OAuth2 认证)"""

    def __init__(self, email_address: str, access_token: str = None, refresh_token: str = None):
        """
        初始化 Outlook 验证器

        Args:
            email_address: Outlook 邮箱地址
            access_token: OAuth2 访问令牌（可选，如果提供则直接使用）
            refresh_token: OAuth2 刷新令牌（可选）
        """
        self.email_address = email_address
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.imap_server = "outlook.office365.com"
        self.imap_port = 993
        self._token_file = f".outlook_token_{email_address.replace('@', '_')}.json"

    def authenticate(self) -> bool:
        """
        执行 OAuth2 认证流程

        Returns:
            bool: 是否认证成功
        """
        print("正在启动 OAuth2 认证流程...")
        print("1. 浏览器将自动打开 Microsoft 登录页面")
        print("2. 登录并授权应用访问您的 Outlook 邮箱")
        print("3. 认证完成后会自动返回")
        print()

        code_verifier, code_challenge = generate_pkce()

        # 启动本地服务器接收回调
        auth_code = [None]
        auth_error = [None]

        def run_server():
            with socketserver.TCPServer(("", REDIRECT_PORT), AuthHandler) as httpd:
                httpd.handle_request()
                AuthHandler.code = None
                AuthHandler.error = None
                auth_code[0] = AuthHandler.code
                auth_error[0] = AuthHandler.error

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # 打开浏览器
        auth_url = get_auth_url(self.email_address, code_challenge)
        print(f"如果浏览器未自动打开，请访问:")
        print(f"{auth_url}")
        print()
        webbrowser.open(auth_url)

        # 等待回调
        server_thread.join(timeout=120)

        if auth_error[0]:
            print(f"认证失败：{auth_error[0]}")
            return False

        if not auth_code[0]:
            print("认证超时")
            return False

        # 换取令牌
        try:
            print("正在获取访问令牌...")
            token_response = get_token_from_code(auth_code[0], code_verifier, self.email_address)

            if 'access_token' in token_response:
                self.access_token = token_response['access_token']
                self.refresh_token = token_response.get('refresh_token')
                print("认证成功!")

                # 保存令牌
                self._save_tokens()
                return True
            else:
                print(f"获取令牌失败：{token_response}")
                return False
        except Exception as e:
            print(f"错误：{e}")
            return False

    def _save_tokens(self):
        """保存令牌到文件"""
        if self.refresh_token:
            tokens = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'email': self.email_address
            }
            try:
                with open(self._token_file, 'w') as f:
                    json.dump(tokens, f)
                print(f"令牌已保存到：{self._token_file}")
            except Exception as e:
                print(f"保存令牌失败：{e}")

    def _load_tokens(self) -> bool:
        """从文件加载令牌"""
        try:
            import os
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

    def connect(self) -> imaplib.IMAP4_SSL:
        """
        连接到 Outlook IMAP 服务器（使用 OAuth2）

        Returns:
            IMAP4_SSL: IMAP 连接对象
        """
        # 尝试加载已保存的令牌
        if not self.access_token:
            self._load_tokens()

        # 如果没有令牌，执行认证
        if not self.access_token:
            if not self.authenticate():
                raise Exception("认证失败")

        # 使用 OAuth2 登录
        imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)

        # OAuth2 认证机制：使用 ACCESS_TOKEN2
        auth_string = f'user={self.email_address}\1auth=Bearer {self.access_token}\1\1'
        imap.authenticate('XOAUTH2', lambda x: auth_string)

        return imap

    def fetch_unread_emails(self, folder: str = "INBOX", limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取未读邮件

        Args:
            folder: 邮箱文件夹，默认 INBOX
            limit: 获取邮件数量限制

        Returns:
            list: 邮件列表
        """
        results = []
        imap = self.connect()

        try:
            # 选择邮箱文件夹
            imap.select(folder)

            # 搜索未读邮件
            status, messages = imap.search(None, "UNSEEN")

            if status == "OK":
                email_ids = messages[0].split()

                # 限制数量
                email_ids = email_ids[-limit:]

                for email_id in reversed(email_ids):
                    try:
                        status, msg_data = imap.fetch(email_id, "(RFC822)")

                        if status == "OK":
                            for response_part in msg_data:
                                if isinstance(response_part, tuple):
                                    msg = email.message_from_bytes(response_part[1])

                                    # 解码主题
                                    subject = msg.get("Subject", "")
                                    subject = decode_mime_word(subject)

                                    # 提取正文
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

    def validate_email(self, email_id: str, folder: str = "INBOX") -> Dict[str, Any]:
        """
        验证指定邮件的内容

        Args:
            email_id: 邮件 ID
            folder: 邮箱文件夹

        Returns:
            dict: 验证结果
        """
        imap = self.connect()

        try:
            imap.select(folder)
            status, msg_data = imap.fetch(email_id.encode(), "(RFC822)")

            if status == "OK":
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        body = extract_text_from_email(msg)
                        subject = decode_mime_word(msg.get("Subject", ""))

                        validation_result = validate_email_content(body)
                        validation_result['subject'] = subject
                        validation_result['from'] = decode_mime_word(msg.get("From", ""))
                        validation_result['email_id'] = email_id

                        return validation_result

        finally:
            imap.close()
            imap.logout()

        return {
            'valid': False,
            'errors': ['无法获取邮件内容'],
            'mobile_phone': None,
            'id_card': None,
            'name': None,
        }

    def validate_all_unread(self, folder: str = "INBOX", limit: int = 10) -> List[Dict[str, Any]]:
        """
        验证所有未读邮件

        Args:
            folder: 邮箱文件夹
            limit: 处理邮件数量限制

        Returns:
            list: 验证结果列表
        """
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


def main():
    """主函数 - 示例用法"""

    # 示例：验证邮件内容（不连接 Outlook）
    sample_email_body = """
    您好，

    我是张三，想咨询一下贵公司的服务。
    我的联系方式如下：
    姓名：张三
    手机号：13812345678
    身份证号：110101199003076317

    期待您的回复！
    """

    print("=" * 50)
    print("邮件内容验证示例")
    print("=" * 50)

    result = validate_email_content(sample_email_body)

    print(f"\n验证结果：{'通过' if result['valid'] else '失败'}")

    if result['mobile_phone']:
        print(f"手机号码：{result['mobile_phone']}")

    if result['id_card']:
        print(f"身份证号：{result['id_card']}")

    if result['name']:
        print(f"姓名：{result['name']}")

    if result['errors']:
        print("\n错误信息:")
        for error in result['errors']:
            print(f"  - {error}")

    # Outlook OAuth2 连接示例
    print("\n" + "=" * 50)
    print("Outlook OAuth2 连接示例")
    print("=" * 50)

    print("""
使用 OAuth2 认证:

from outlook_email_validator_oauth2 import OutlookEmailValidator

validator = OutlookEmailValidator(
    email_address="your_email@outlook.com"
)

# 首次使用会打开浏览器进行 OAuth2 认证
# 令牌会自动保存到本地文件
# 后续使用会自动加载已保存的令牌

results = validator.validate_all_unread(limit=5)
for result in results:
    print(f"主题：{result['subject']}")
    print(f"验证：{'通过' if result['valid'] else '失败'}")
    if result['mobile_phone']:
        print(f"手机：{result['mobile_phone']}")
    print("-" * 40)
""")


if __name__ == "__main__":
    main()
