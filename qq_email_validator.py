"""
QQ 邮箱自动处理模块

功能：
1. 收取 QQ 邮箱邮件，过滤主题为 "fil 余额提取" 的邮件
2. 排除 HTML 格式和带附件的邮件
3. 验证正文中必须有唯一的手机号码、姓名、身份证
4. 合法邮件记录 log 并回复"收到"
5. 不合法邮件只记录 log

使用方法：
    python qq_email_validator.py

配置：
    需要在 QQ 邮箱设置中启用 IMAP/SMTP 服务，并获取授权码
    授权码获取方式：QQ 邮箱 -> 设置 -> 账户 -> 开启 IMAP/SMTP 服务 -> 生成授权码

环境变量:
    在 .env 文件中配置:
    QQ_EMAIL=your_qq@qq.com
    QQ_AUTH_CODE=your_auth_code
"""

import re
import imaplib
import smtplib
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header, Header
from email.utils import formataddr
import email
from email.message import Message
from typing import Optional, List, Dict, Any, Tuple

# 加载环境变量
load_dotenv()

# 从环境变量获取配置
QQ_EMAIL = os.getenv("QQ_EMAIL", "")
QQ_AUTH_CODE = os.getenv("QQ_AUTH_CODE", "")

# ==================== 日志配置 ====================

# 创建 logs 目录
os.makedirs("logs", exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/qq_email_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== 验证函数 ====================

def find_chinese_mobile_numbers(text: str) -> List[str]:
    """
    在输入文本中搜索中国大陆有效手机号码
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


def check_has_html_content(msg: Message) -> bool:
    """检查邮件是否包含 HTML 内容"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return True
    return False


def check_has_attachment(msg: Message) -> bool:
    """检查邮件是否包含附件"""
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in content_disposition.lower():
                return True
    return False


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


# ==================== QQ 邮箱客户端类 ====================

class QQEmailClient:
    """QQ 邮箱客户端 - 支持收发邮件"""

    def __init__(self, qq_email: str, auth_code: str):
        """
        初始化 QQ 邮箱客户端

        Args:
            qq_email: QQ 邮箱地址（如：123456@qq.com）
            auth_code: QQ 邮箱授权码（不是 QQ 密码）
        """
        self.email_address = qq_email
        self.auth_code = auth_code
        self.imap_server = "imap.qq.com"
        self.imap_port = 993
        self.smtp_server = "smtp.qq.com"
        self.smtp_port = 465
        self.required_subject = "fil余额提取"  # 注意：没有空格

    def connect_imap(self) -> imaplib.IMAP4_SSL:
        """连接到 QQ 邮箱 IMAP 服务器"""
        imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        imap.login(self.email_address, self.auth_code)
        return imap

    def connect_smtp(self) -> smtplib.SMTP_SSL:
        """连接到 QQ 邮箱 SMTP 服务器"""
        smtp = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
        smtp.login(self.email_address, self.auth_code)
        return smtp

    def fetch_target_emails(self, folder: str = "INBOX", limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取目标邮件（主题为 "fil 余额提取" 的未读邮件）

        Args:
            folder: 邮箱文件夹
            limit: 最多获取多少封邮件

        Returns:
            邮件列表
        """
        results = []
        imap = self.connect_imap()

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

                                    # 检查主题是否匹配（不区分大小写，忽略首尾空格）
                                    subject_clean = subject.strip().lower()
                                    required_clean = self.required_subject.lower()
                                    if subject_clean != required_clean:
                                        logger.info(f"邮件 ID {email_id.decode()} 主题不匹配：'{subject}' (期望：'{self.required_subject}')")
                                        continue

                                    results.append({
                                        'id': email_id.decode(),
                                        'subject': subject,
                                        'from': decode_mime_word(msg.get("From", "")),
                                        'date': msg.get("Date", ""),
                                        'raw_message': msg,
                                    })
                                    break
                    except Exception as e:
                        logger.error(f"处理邮件 {email_id} 时出错：{e}")

        finally:
            imap.close()
            imap.logout()

        return results

    def process_email(self, email_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        处理单封邮件：检查 HTML、附件、验证内容

        Args:
            email_info: 邮件信息字典

        Returns:
            (是否合法，验证结果)
        """
        msg = email_info['raw_message']
        result = {
            'email_id': email_info['id'],
            'subject': email_info['subject'],
            'from': email_info['from'],
            'date': email_info['date'],
            'valid': True,
            'errors': [],
            'mobile_phone': None,
            'id_card': None,
            'name': None,
        }

        # 检查是否包含 HTML 内容
        if check_has_html_content(msg):
            result['valid'] = False
            result['errors'].append('邮件包含 HTML 内容')
            logger.warning(f"邮件 {email_info['id']} 包含 HTML 内容，视为不合法")
            return False, result

        # 检查是否包含附件
        if check_has_attachment(msg):
            result['valid'] = False
            result['errors'].append('邮件包含附件')
            logger.warning(f"邮件 {email_info['id']} 包含附件，视为不合法")
            return False, result

        # 提取正文内容
        body = extract_text_from_email(msg)
        result['body'] = body

        # 验证邮件内容
        validation = validate_email_content(body)
        result['valid'] = validation['valid']
        result['errors'].extend(validation['errors'])
        result['mobile_phone'] = validation['mobile_phone']
        result['id_card'] = validation['id_card']
        result['name'] = validation['name']

        if not validation['valid']:
            logger.warning(f"邮件 {email_info['id']} 内容验证失败：{validation['errors']}")
        else:
            logger.info(f"邮件 {email_info['id']} 验证通过 - 姓名：{result['name']}, 手机：{result['mobile_phone']}, 身份证：{result['id_card']}")

        return validation['valid'], result

    def send_reply(self, to_address: str, in_reply_to_subject: str) -> bool:
        """
        回复邮件

        Args:
            to_address: 收件人邮箱地址
            in_reply_to_subject: 原邮件主题（会自动添加 Re:）

        Returns:
            是否发送成功
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = to_address
            msg['Subject'] = Header(f"Re: {in_reply_to_subject}", 'utf-8')
            msg.attach(MIMEText('收到', 'plain', 'utf-8'))

            smtp = self.connect_smtp()
            try:
                smtp.sendmail(self.email_address, to_address, msg.as_string())
                return True
            finally:
                smtp.quit()

        except Exception as e:
            logger.error(f"回复邮件失败：{e}")
            return False

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        """将邮件标记为已读"""
        try:
            imap = self.connect_imap()
            try:
                imap.select(folder)
                imap.store(email_id.encode(), '+FLAGS', '\\Seen')
                return True
            finally:
                imap.close()
                imap.logout()
        except Exception as e:
            logger.error(f"标记邮件为已读失败：{e}")
            return False

    def process_all_unread(self) -> Dict[str, int]:
        """
        处理所有未读的目标邮件

        Returns:
            统计结果：合法数量、不合法数量、回复成功数量
        """
        stats = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'replied': 0,
        }

        logger.info("=" * 50)
        logger.info("开始处理未读邮件...")

        # 获取目标邮件
        emails = self.fetch_target_emails()
        stats['total'] = len(emails)
        logger.info(f"找到 {len(emails)} 封主题为 '{self.required_subject}' 的未读邮件")

        if not emails:
            return stats

        for email_info in emails:
            logger.info(f"\n处理邮件 ID: {email_info['id']}, 发件人：{email_info['from']}")

            # 处理邮件
            is_valid, result = self.process_email(email_info)

            if is_valid:
                stats['valid'] += 1
                # 回复"收到"
                sender_email = email_info['from'].split('<')[-1].split('>').strip() if '<' in email_info['from'] else email_info['from']
                if self.send_reply(sender_email, email_info['subject']):
                    stats['replied'] += 1
                    logger.info(f"邮件 {email_info['id']} 回复成功")
                else:
                    logger.error(f"邮件 {email_info['id']} 回复失败")
            else:
                stats['invalid'] += 1
                logger.warning(f"邮件 {email_info['id']} 不合法，仅记录 log: {result['errors']}")

            # 所有处理过的邮件都标记为已读
            self.mark_as_read(email_info['id'])

        logger.info(f"\n处理完成 - 总计：{stats['total']}, 合法：{stats['valid']}, 不合法：{stats['invalid']}, 已回复：{stats['replied']}")
        logger.info("=" * 50)

        return stats

    def test_connection(self) -> bool:
        """测试连接是否成功"""
        try:
            imap = self.connect_imap()
            imap.select('INBOX')
            status, count = imap.search(None, 'ALL')
            if status == 'OK':
                emails = len(count[0].split()) if count[0] else 0
                logger.info(f"IMAP 连接成功！收件箱共有 {emails} 封邮件")
            imap.close()
            imap.logout()

            smtp = self.connect_smtp()
            smtp.quit()
            logger.info("SMTP 连接成功！")
            return True
        except Exception as e:
            logger.error(f"连接失败：{e}")
            return False


# ==================== 便捷函数 ====================

def process_qq_emails() -> Dict[str, int]:
    """
    便捷函数：处理 QQ 邮箱中的所有目标邮件

    Returns:
        统计结果
    """
    if not QQ_EMAIL or not QQ_AUTH_CODE:
        logger.error("请在 .env 文件中配置 QQ_EMAIL 和 QQ_AUTH_CODE")
        return {'total': 0, 'valid': 0, 'invalid': 0, 'replied': 0}

    client = QQEmailClient(QQ_EMAIL, QQ_AUTH_CODE)
    return client.process_all_unread()


# ==================== 主函数 ====================

def main():
    """主函数"""

    # 从环境变量加载配置
    if not QQ_EMAIL or not QQ_AUTH_CODE:
        print("错误：请在 .env 文件中配置 QQ_EMAIL 和 QQ_AUTH_CODE")
        print("示例:")
        print("  QQ_EMAIL=your_qq@qq.com")
        print("  QQ_AUTH_CODE=your_auth_code")
        return

    logger.info("=" * 60)
    logger.info("QQ 邮箱自动处理模块")
    logger.info(f"配置邮箱：{QQ_EMAIL}")
    logger.info("=" * 60)

    # 创建客户端
    client = QQEmailClient(QQ_EMAIL, QQ_AUTH_CODE)

    # 测试连接
    logger.info("\n测试连接...")
    if client.test_connection():
        logger.info("连接测试成功")
    else:
        logger.error("连接测试失败")
        return

    # 处理邮件
    logger.info("\n开始处理邮件...")
    stats = client.process_all_unread()

    print(f"\n处理结果:")
    print(f"  总邮件数：{stats['total']}")
    print(f"  合法邮件：{stats['valid']}")
    print(f"  不合法邮件：{stats['invalid']}")
    print(f"  已回复：{stats['replied']}")
    print(f"\n详细日志请查看：logs/qq_email_{datetime.now().strftime('%Y%m%d')}.log")


if __name__ == "__main__":
    main()
