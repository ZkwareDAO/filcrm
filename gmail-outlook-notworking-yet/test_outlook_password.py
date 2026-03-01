"""
Outlook 应用密码验证工具

使用方法:
    python test_outlook_password.py your_email@outlook.com your_app_password

或者运行后输入：
    python test_outlook_password.py
"""

import imaplib
import sys
import getpass


def test_outlook_login(email_address: str, app_password: str) -> bool:
    """
    测试 Outlook 应用密码是否正确

    Args:
        email_address: Outlook 邮箱地址
        app_password: 应用专用密码

    Returns:
        bool: 密码是否有效
    """
    imap_server = 'outlook.office365.com'
    imap_port = 993

    print(f'\nTesting connection to {imap_server}:{imap_port}')
    print(f'Email: {email_address}')
    print(f'Password: {"*" * len(app_password)} (hidden)\n')

    try:
        # 创建 SSL 连接
        print('[1/3] Connecting...')
        imap = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=10)
        print('      Connection established')

        # 尝试登录
        print('[2/3] Logging in...')
        imap.login(email_address, app_password)
        print('      Login SUCCESS!\n')

        # 列出可用文件夹
        print('[3/3] Checking folders...')
        status, folders = imap.list()
        if status == 'OK':
            print('      Available folders:')
            for f in folders[:10]:  # 只显示前 10 个
                folder_name = f.decode().split('"')[-1] if '"' in f.decode() else f.decode()
                print(f'        - {folder_name}')

        # 检查收件箱
        imap.select('INBOX')
        status, count = imap.search(None, 'ALL')
        if status == 'OK':
            emails = len(count[0].split()) if count[0] else 0
            print(f'\n      INBOX: {emails} emails')

        # 检查未读邮件
        status, unread = imap.search(None, 'UNSEEN')
        if status == 'OK':
            unread_count = len(unread[0].split()) if unread[0] else 0
            print(f'      Unread: {unread_count} emails')

        imap.close()
        imap.logout()

        print('\n' + '=' * 50)
        print('RESULT: Password is VALID')
        print('=' * 50)
        return True

    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        print('\n' + '=' * 50)
        print('RESULT: Login FAILED')
        print('=' * 50)
        print(f'\nError type: IMAP4.error')
        print(f'Details: {error_msg}')

        if 'AUTHENTICATIONFAILED' in error_msg:
            print('\nPossible causes:')
            print('  1. App password is incorrect')
            print('  2. Password has expired')
            print('  3. Two-factor authentication not enabled')
        elif 'LOGIN failed' in error_msg:
            print('\nPossible causes:')
            print('  1. Wrong password')
            print('  2. Account locked')
        return False

    except Exception as e:
        print('\n' + '=' * 50)
        print('RESULT: Connection FAILED')
        print('=' * 50)
        print(f'\nError type: {type(e).__name__}')
        print(f'Details: {e}')
        return False


def get_app_password_help():
    """显示获取应用密码的帮助信息"""
    print('\n' + '=' * 50)
    print('How to get Outlook App Password:')
    print('=' * 50)
    print('''
1. Go to Microsoft Account Security:
   https://account.microsoft.com/security

2. Enable Two-factor authentication (if not already enabled)

3. Go to "Advanced security options"

4. Under "App passwords", click "Create a new app password"

5. Copy the generated password (format: xxxxxxxx xxxxxxxx)
   - This is NOT your login password
   - You only see it once
   - Save it somewhere safe

6. Use this password in your application
   - Remove spaces when using: "xxxxxxxxxxxxxxxx"
''')


def main():
    print('=' * 50)
    print('Outlook App Password Validator')
    print('=' * 50)

    # 从命令行参数获取或交互式输入
    if len(sys.argv) > 2:
        email = sys.argv[1]
        password = sys.argv[2]
    elif len(sys.argv) == 2:
        email = sys.argv[1]
        password = getpass.getpass('Enter app password: ').strip()
    else:
        print('\nUsage:')
        print('  python test_outlook_password.py email@outlook.com your_password')
        print('  python test_outlook_password.py email@outlook.com')
        print()
        email = input('Enter Outlook email: ').strip()
        password = getpass.getpass('Enter app password: ').strip()

    # 移除密码中的空格（Microsoft 应用密码通常带空格显示）
    password = password.replace(' ', '')

    success = test_outlook_login(email, password)

    # 如果失败，显示帮助信息
    if not success:
        get_app_password_help()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
