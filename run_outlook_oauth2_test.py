"""
Outlook OAuth2 认证测试脚本

运行此脚本将：
1. 打开浏览器进行 OAuth2 认证
2. 认证成功后获取访问令牌
3. 使用令牌连接 IMAP 并收取邮件
"""

import sys
from outlook_email_validator_oauth2 import OutlookEmailValidator, validate_email_content

def main():
    print("=" * 60)
    print("Outlook OAuth2 认证测试")
    print("=" * 60)
    print()

    # 配置邮箱地址
    email_address = "zk0185@outlook.com"

    print(f"邮箱地址：{email_address}")
    print()
    print("即将打开浏览器进行 OAuth2 认证...")
    print()

    # 创建验证器（会自动触发 OAuth2 认证）
    validator = OutlookEmailValidator(email_address=email_address)

    try:
        # 尝试连接并获取未读邮件
        print("正在连接 Outlook 服务器...")
        emails = validator.fetch_unread_emails(limit=5)

        print(f"成功获取 {len(emails)} 封邮件\n")

        if not emails:
            print("没有未读邮件")
            print("\n尝试获取所有邮件（包括已读）...")
            # 修改为获取所有邮件
            imap = validator.connect()
            imap.select('INBOX')
            status, messages = imap.search(None, "ALL")
            if status == "OK":
                email_ids = messages[0].split()[-5:]  # 最后 5 封
                print(f"找到 {len(email_ids)} 封邮件")
            imap.close()
            imap.logout()

        # 验证每封邮件的内容
        print("\n" + "=" * 60)
        print("邮件内容验证")
        print("=" * 60)

        results = validator.validate_all_unread(limit=5)

        if not results:
            print("\n没有未读邮件需要验证")
            return 0

        for i, result in enumerate(results, 1):
            print(f"\n[邮件 {i}]")
            print(f"  主题：{result['subject']}")
            print(f"  发件人：{result['from']}")
            print(f"  验证：{'通过' if result['valid'] else '失败'}")

            if result['mobile_phone']:
                print(f"  手机号：{result['mobile_phone']}")
            if result['id_card']:
                print(f"  身份证：{result['id_card']}")
            if result['name']:
                print(f"  姓名：{result['name']}")
            if result['errors']:
                print(f"  错误：{', '.join(result['errors'])}")

        return 0

    except Exception as e:
        print(f"\n错误：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
