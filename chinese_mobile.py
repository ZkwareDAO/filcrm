  import re


  def find_chinese_mobile_numbers(text):
      """
      在输入文本中搜索中国大陆有效手机号码
   
      条件:
      1. 11 位数字
      2. 以 1 开头
      3. 符合中国大陆手机号格式 (1[3-9]\d{9})
   
      Args:
          text: 输入的文本字符串
   
      Returns:
          list: 匹配的手机号码列表
      """
      # 正则表达式解释:
      # 1[3-9]\d{9} - 以 1 开头，第二位是 3-9，后面跟 9 位任意数字
      # \b - 单词边界，确保匹配完整的号码
      pattern = r'\b1[3-9]\d{9}\b'

      matches = re.findall(pattern, text)
      return matches


  # 测试示例
  if __name__ == "__main__":
      sample_text = """
      请联系张经理，手机号：13812345678
      或者联系李小姐，15987654321
      无效号码：12345678901, 21234567890, 11111111111
      还有一个号码：19900001111
      """

      mobile_numbers = find_chinese_mobile_numbers(sample_text)
      print("找到的手机号码:")
      for num in mobile_numbers:
          print(f"  {num}")
