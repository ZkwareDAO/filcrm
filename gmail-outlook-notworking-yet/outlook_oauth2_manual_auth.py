"""
Outlook OAuth2 手动认证工具

如果自动浏览器认证失败，可以使用此工具手动完成认证
"""

import sys
import json
import urllib.request
import urllib.parse
import base64
import hashlib
import secrets

# Microsoft Graph API 配置
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
REDIRECT_URI = "https://login.microsoftonline.com/common/oauth2/nativeclient"


def generate_pkce():
    """生成 PKCE 代码挑战和验证器"""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


def get_auth_url(email: str, code_challenge: str):
    """生成授权 URL"""
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'response_mode': 'query',
        'prompt': 'select_account',
        'login_hint': email,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    query = '&'.join([f'{k}={urllib.parse.quote(v)}' for k, v in params.items()])
    return f'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{query}'


def get_token_from_code(code: str, code_verifier: str, email: str):
    """使用授权码换取访问令牌"""
    token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = {
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
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


def main():
    print("=" * 60)
    print("Outlook OAuth2 手动认证工具")
    print("=" * 60)
    print()
    print("当自动浏览器认证失败时，使用此工具手动完成认证")
    print()

    email = input("输入 Outlook 邮箱地址：").strip()
    if not email:
        email = "zk0185@outlook.com"

    print(f"\n邮箱：{email}")
    print()
    print("步骤 1: 复制下面的 URL 并在浏览器中打开")
    print("-" * 60)

    code_verifier, code_challenge = generate_pkce()
    auth_url = get_auth_url(email, code_challenge)

    print(auth_url)
    print()
    print("-" * 60)
    print()
    print("步骤 2: 在浏览器中登录并授权")
    print("步骤 3: 授权后会跳转到一个页面，复制浏览器地址栏中的完整 URL")
    print("步骤 4: 从 URL 中提取 code 参数的值")
    print()
    print("或者，你也可以直接登录 Microsoft Azure 门户获取访问令牌")
    print()

    auth_code = input("输入授权码 (code): ").strip()

    if not auth_code:
        print("未输入授权码，退出。")
        return 1

    print("\n正在获取访问令牌...")

    try:
        token_response = get_token_from_code(auth_code, code_verifier, email)

        if 'access_token' in token_response:
            print("\n" + "=" * 60)
            print("认证成功!")
            print("=" * 60)

            access_token = token_response['access_token']
            refresh_token = token_response.get('refresh_token')
            expires_in = token_response.get('expires_in', 3600)

            print(f"\n访问令牌：{access_token[:50]}...")
            print(f"刷新令牌：{refresh_token[:50] if refresh_token else 'N/A'}...")
            print(f"过期时间：{expires_in} 秒")

            # 保存令牌到文件
            token_file = f".outlook_token_{email.replace('@', '_')}.json"
            tokens = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'email': email,
                'scope': SCOPE
            }

            with open(token_file, 'w') as f:
                json.dump(tokens, f, indent=2)

            print(f"\n令牌已保存到：{token_file}")
            print("\n现在可以运行 run_outlook_oauth2_test.py 来测试邮件收取")

            # 测试 IMAP 连接
            print("\n" + "=" * 60)
            print("测试 IMAP 连接...")
            print("=" * 60)

            import imaplib

            imap = imaplib.IMAP4_SSL("outlook.office365.com", 993)

            # 使用 OAuth2 登录
            auth_string = f'user={email}\1auth=Bearer {access_token}\1\1'
            imap.authenticate('XOAUTH2', lambda x: auth_string)

            print("IMAP 登录成功!")

            # 检查收件箱
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

            print("\n测试完成!")
            return 0

        else:
            print(f"获取令牌失败：{token_response}")
            return 1

    except Exception as e:
        print(f"\n错误：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
