"""
Gmail 应用密码测试工具

使用方法:
    python test_gmail_password.py your_email@gmail.com your_app_password
"""

import imaplib
import sys
import getpass


def test_gmail_login(email_address: str, app_password: str) -> bool:
    """测试 Gmail 应用密码是否正确"""
    imap_server = 'imap.gmail.com'
    imap_port = 993

    print(f'\n测试服务器：{imap_server}:{imap_port}')
    print(f'邮箱：{email_address}')
    print(f'密码：{"*" * len(app_password)} (已隐藏)\n')

    try:
        # 连接
        print('[1/3] 连接服务器...')
        imap = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=15)
        print('      连接成功')

        # 登录
        print('[2/3] 登录...')
        imap.login(email_address, app_password)
        print('      登录成功!\n')

        # 检查邮箱
        print('[3/3] 检查收件箱...')
        imap.select('INBOX')
        status, count = imap.search(None, 'ALL')
        if status == 'OK':
            emails = len(count[0].split()) if count[0] else 0
            print(f'      收件箱邮件数：{emails}')

        status, unread = imap.search(None, 'UNSEEN')
        if status == 'OK':
            unread_count = len(unread[0].split()) if unread[0] else 0
            print(f'      未读邮件数：{unread_count}')

        imap.close()
        imap.logout()

        print('\n' + '=' * 50)
        print('结果：密码有效，连接成功!')
        print('=' * 50)
        return True

    except imaplib.IMAP4.error as e:
        print('\n' + '=' * 50)
        print('结果：登录失败!')
        print('=' * 50)
        print(f'\n错误：{e}')
        print('\n可能原因:')
        print('  1. 应用密码错误')
        print('  2. 未启用两步验证')
        print('  3. IMAP 未启用')
        return False

    except Exception as e:
        print(f'\n错误：{e}')
        return False


def get_app_password_help():
    """显示获取应用密码的帮助"""
    print('\n' + '=' * 50)
    print('如何获取 Gmail 应用密码:')
    print('=' * 50)
    print('''
1. 访问 Google 账户安全页面:
   https://myaccount.google.com/security

2. 启用"两步验证"(如果尚未启用)

3. 在"应用密码"中:
   - 点击"应用密码"
   - 选择应用：邮件
   - 选择设备：其他
   - 点击"生成"

4. 复制 16 位密码 (格式：xxxx xxxx xxxx xxxx)
   - 这只显示一次，请妥善保存
   - 使用时可以带空格或不带空格

5. 在 Gmail 中启用 IMAP:
   - 访问 https://mail.google.com
   - 设置 > 查看所有设置
   - 转发和 POP/IMAP
   - 启用 IMAP
''')


def main():
    print('=' * 50)
    print('Gmail 应用密码验证工具')
    print('=' * 50)

    if len(sys.argv) > 2:
        email = sys.argv[1]
        password = sys.argv[2]
    elif len(sys.argv) == 2:
        email = sys.argv[1]
        password = getpass.getpass('输入应用密码：').strip()
    else:
        print('\n使用方法:')
        print('  python test_gmail_password.py email@gmail.com password')
        print()
        email = input('输入 Gmail 邮箱地址：').strip()
        password = getpass.getpass('输入应用密码：').strip()

    # 移除密码中的空格
    password = password.replace(' ', '')

    success = test_gmail_login(email, password)

    if not success:
        get_app_password_help()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
