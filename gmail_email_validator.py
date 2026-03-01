"""
Gmail 邮件验证模块

功能：
1. 从 Gmail 收取邮件
2. 在邮件正文中查找手机号码（必须且只能有一个有效的中国手机号）
3. 检查身份证号码（必须且只能有一个有效的身份证号）
4. 检查是否包含姓名

使用方法：
    python gmail_email_validator.py

配置：
    需要在 Gmail 设置中启用 IMAP，并生成应用专用密码
"""

import re
import imaplib
import email
from email.message import Message
from email.header import decode_header
from typing import Optional, List, Dict, Any


# ==================== 验证函数 ====================

def find_chinese_mobile_numbers(text: str) -> List[str]:
    """
    在输入文本中搜索中国大陆有效手机号码

    条件:
    1. 11 位数字
    2. 以 1 开头
    3. 符合中国大陆手机号格式 (1[3-9]\\d{{9}})
    """
    pattern = r'\b1[3-9]\d{9}\b'
    matches = re.findall(pattern, text)
    return matches


def validate_mobile_number(phone: str) -> bool:
    """验证手机号码是否有效"""
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def find_id_card_numbers(text: str) -> List[str]:
    """
    在文本中查找中国居民身份证号码
    支持 18 位（含 X）和 15 位格式
    """
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

    # 检查手机号码
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

    # 检查身份证号码
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

    # 检查姓名
    name = find_name(email_text)
    if name:
        result['name'] = name
    else:
        result['valid'] = False
        result['errors'].append('未找到姓名')

    return result


# ==================== Gmail 验证器类 ====================

class GmailEmailValidator:
    """Gmail 邮件验证器"""

    def __init__(self, email_address: str, app_password: str):
        """
        初始化 Gmail 验证器

        Args:
            email_address: Gmail 邮箱地址
            app_password: Gmail 应用专用密码（不是登录密码）
                         需要在 Google 账户设置中启用两步验证并生成应用密码
        """
        self.email_address = email_address
        self.app_password = app_password
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993

    def connect(self) -> imaplib.IMAP4_SSL:
        """连接到 Gmail IMAP 服务器"""
        imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        imap.login(self.email_address, self.app_password)
        return imap

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

    def test_connection(self) -> bool:
        """测试连接是否成功"""
        try:
            imap = self.connect()
            imap.select('INBOX')
            status, count = imap.search(None, 'ALL')
            if status == 'OK':
                emails = len(count[0].split()) if count[0] else 0
                print(f"连接成功！收件箱共有 {emails} 封邮件")
            imap.close()
            imap.logout()
            return True
        except Exception as e:
            print(f"连接失败：{e}")
            return False


# ==================== 主函数 ====================

def main():
    """主函数 - 测试验证功能"""

    # 测试样例数据
    sample_email_body = """
    您好，

    我是张三，想咨询一下贵公司的服务。
    我的联系方式如下：
    姓名：张三
    手机号：13812345678
    身份证号：110101199003076317

    期待您的回复！
    """

    print("=" * 60)
    print("Gmail 邮件验证模块 - 功能测试")
    print("=" * 60)

    # 测试验证功能
    print("\n[测试] 邮件内容验证")
    print("-" * 40)

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

    # 测试其他验证场景
    print("\n" + "=" * 60)
    print("其他测试场景")
    print("=" * 60)

    # 测试 1: 无手机号
    print("\n[测试] 无手机号的情况")
    test1 = validate_email_content("你好，我叫李四，身份证号：110101199001010011")
    print(f"结果：{'通过' if test1['valid'] else '失败'}")
    print(f"错误：{test1['errors']}")

    # 测试 2: 多个手机号
    print("\n[测试] 多个手机号的情况")
    test2 = validate_email_content("你好，电话 13800138000 或 13900139000，姓名：王五")
    print(f"结果：{'通过' if test2['valid'] else '失败'}")
    print(f"错误：{test2['errors']}")

    # 测试 3: 完整有效数据
    print("\n[测试] 完整有效数据")
    test3 = validate_email_content("姓名：赵六，手机：18600138000，身份证：110101199001010011")
    print(f"结果：{'通过' if test3['valid'] else '失败'}")
    if test3['mobile_phone']:
        print(f"手机：{test3['mobile_phone']}")
    if test3['id_card']:
        print(f"身份证：{test3['id_card']}")
    if test3['name']:
        print(f"姓名：{test3['name']}")

    # Gmail 连接示例
    print("\n" + "=" * 60)
    print("Gmail 连接示例")
    print("=" * 60)
    print("""
使用方法:

from gmail_email_validator import GmailEmailValidator

# 创建验证器
validator = GmailEmailValidator(
    email_address="your_email@gmail.com",
    app_password="xxxx xxxx xxxx xxxx"  # 16 位应用密码
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
    if result['id_card']:
        print(f"身份证：{result['id_card']}")
    if result['name']:
        print(f"姓名：{result['name']}")
    print("-" * 40)

如何获取 Gmail 应用密码:
1. 访问 https://myaccount.google.com/security
2. 启用"两步验证"
3. 在"应用密码"中生成新密码
4. 复制 16 位密码（格式：xxxx xxxx xxxx xxxx）
""")


if __name__ == "__main__":
    main()
