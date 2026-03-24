from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import datetime
import random
import json
import os
import re


class OptimizedTicketGrabber:
    def __init__(self, config_file='ticket_config.json'):
        """初始化抢票机器人"""
        # 加载配置
        self.config = self.load_config(config_file)

        # 浏览器设置
        self.setup_browser()

        # 等待对象
        self.wait = WebDriverWait(self.driver, self.config['timeout'])

        # 登录状态
        self.logged_in = False

        # 车站代码缓存
        self.station_codes = {}

        # 抢票记录
        self.ticket_records = []

        # 查询计数器
        self.query_count = 0

        # 缓存元素
        self.from_input = None
        self.to_input = None
        self.date_input = None
        self.query_btn = None

    def load_config(self, config_file):
        """加载配置文件"""
        default_config = {
            # 登录信息
            'username': '15512744457',  # 需要用户填写
            'password': 'zhang1363664436',  # 需要用户填写

            # 车票信息
            'from_station': '大连北',
            'to_station': '邯郸东',
            'train_date': "2025-01-14",
            'train_numbers': ['G1', 'G2', 'G3'],  # 优先车次
            'seat_type': '二等座',  # 席别：二等座、一等座、商务座

            # 乘车人信息（需在12306账号中添加）
            'passengers': ['张嘉柠'],  # 乘客姓名

            # 浏览器设置
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'headless': False,
            'timeout': 30,

            # 优化后的抢票策略
            'max_query_times': 100,  # 最大查询次数
            'base_refresh_interval': 3,  # 基础刷新间隔
            'human_delay_range': (0.1, 0.5),  # 优化延迟范围
            'random_query_variation': 0.3,  # 查询时间随机变化

            # 缓存策略
            'cache_station_codes': True,
            'use_cookies': True,

            # 通知设置
            'enable_notification': True
        }

        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)

        return default_config

    def setup_browser(self):
        """设置浏览器选项"""
        edge_options = Options()
        edge_options.add_argument(f'user-agent={self.config["user_agent"]}')
        edge_options.add_argument('--disable-blink-features=AutomationControlled')
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option('useAutomationExtension', False)
        edge_options.add_argument('--no-sandbox')

        if self.config['headless']:
            edge_options.add_argument('--headless')

        try:
            # 启用缓存（减少重复加载）
            edge_options.add_argument("--disable-application-cache")

            self.driver = webdriver.Edge(options=edge_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            print("✓ 浏览器启动成功")
        except Exception as e:
            print(f"✗ 浏览器启动失败: {e}")
            raise

    def human_like_delay(self, min_delay=0.1, max_delay=0.5):
        """优化的随机延迟"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    def setup_query_page(self):
        """设置查询页面（只需执行一次）"""
        print("正在初始化查询页面...")

        try:
            # 直接访问查询页面（避免经过首页）
            self.driver.get('https://kyfw.12306.cn/otn/leftTicket/init')
            time.sleep(2)

            # 等待页面完全加载
            self.wait.until(EC.presence_of_element_located((By.ID, 'fromStationText')))

            # 一次性输入出发站
            self.from_input = self.driver.find_element(By.ID, 'fromStationText')
            self.from_input.click()
            self.from_input.clear()

            print(f"输入出发站: {self.config['from_station']}")
            for char in self.config['from_station']:
                self.from_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            self.human_like_delay()

            # 触发下拉选择（按回车选择第一个匹配项）
            self.from_input.send_keys(Keys.ENTER)

            # 等待下拉列表消失
            time.sleep(0.5)

            # 一次性输入到达站
            self.to_input = self.driver.find_element(By.ID, 'toStationText')
            self.to_input.click()
            self.to_input.clear()

            print(f"输入到达站: {self.config['to_station']}")
            for char in self.config['to_station']:
                self.to_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            self.human_like_delay()
            self.to_input.send_keys(Keys.ENTER)

            # 设置日期（使用JavaScript直接设置值，避免点击日期控件）
            self.date_input = self.driver.find_element(By.ID, 'train_date')
            self.driver.execute_script(
                f"arguments[0].value = '{self.config['train_date']}';",
                self.date_input
            )

            # 获取查询按钮
            self.query_btn = self.driver.find_element(By.ID, 'query_ticket')

            # 点击一次查询按钮，确保车站代码已设置
            self.query_btn.click()
            print("✓ 查询页面初始化完成")
            time.sleep(2)  # 等待首次查询结果

            return True

        except Exception as e:
            print(f"✗ 查询页面初始化失败: {e}")
            return False

    def smart_query_tickets(self):
        """智能查询车票（无需重新输入站名）"""
        self.query_count += 1

        try:
            # 随机化查询间隔（避免规律请求）
            base_interval = self.config['base_refresh_interval']
            variation = self.config['random_query_variation']
            actual_interval = base_interval * random.uniform(1 - variation, 1 + variation)

            # 显示查询状态
            status_msg = f"第 {self.query_count} 次查询"
            if self.query_count > 1:
                status_msg += f" (等待{actual_interval:.1f}秒)"
            print(status_msg, end="\r")

            # 使用JavaScript直接触发查询（比点击按钮更快）
            query_script = """
                document.getElementById('query_ticket').click();
                return true;
            """
            self.driver.execute_script(query_script)

            # 随机等待查询结果
            time.sleep(random.uniform(0.5, 1.5))

            return True

        except Exception as e:
            # 如果JavaScript查询失败，回退到传统方式
            try:
                if self.query_btn:
                    self.query_btn.click()
                    time.sleep(1)
                    return True
            except:
                print(f"\n✗ 第{self.query_count}次查询失败: {e}")
                return False

    def fast_find_available_trains(self):
        """快速查找可用车次"""
        try:
            # 等待车次表格出现
            time.sleep(0.5)  # 减少等待时间

            # 使用更高效的选择器
            train_rows = self.driver.find_elements(
                By.CSS_SELECTOR, '#queryLeftTable tr[class]:not([style*="display: none"])'
            )

            if not train_rows:
                return []

            available_trains = []

            # 预编译正则表达式（提高匹配速度）
            seat_type_pattern = re.compile(r'商务座|一等座|二等座')

            for row in train_rows[:20]:  # 只检查前20行（通常足够）
                try:
                    # 快速获取车次信息
                    train_number_elem = row.find_element(By.CSS_SELECTOR, 'td:nth-child(1) a')
                    train_number = train_number_elem.text.strip()

                    # 如果设置了优先车次，先检查是否符合
                    if self.config['train_numbers'] and train_number not in self.config['train_numbers']:
                        continue

                    # 根据席别类型选择对应的单元格
                    seat_type = self.config['seat_type']

                    # 确定列索引
                    if seat_type == '商务座':
                        col_index = 1  # 第2列（0-based）
                    elif seat_type == '一等座':
                        col_index = 2  # 第3列
                    else:  # 二等座
                        col_index = 3  # 第4列

                    # 查找余票单元格
                    seat_cell = row.find_elements(By.CSS_SELECTOR, 'td.yes')
                    if len(seat_cell) > col_index:
                        ticket_status = seat_cell[col_index].text.strip()

                        # 检查是否有票
                        if ticket_status and ticket_status not in ['无', '--', '*']:
                            # 快速获取其他信息
                            from_to = row.find_element(By.CSS_SELECTOR, 'td:nth-child(2)').text
                            departure = row.find_element(By.CSS_SELECTOR, 'td:nth-child(3)').text
                            arrival = row.find_element(By.CSS_SELECTOR, 'td:nth-child(4)').text

                            available_trains.append({
                                'train_number': train_number,
                                'from_to': from_to,
                                'departure': departure,
                                'arrival': arrival,
                                'seat_status': ticket_status,
                                'priority': train_number in self.config['train_numbers']
                            })

                except Exception:
                    continue

            return available_trains

        except Exception as e:
            print(f"\n✗ 查找车次失败: {e}")
            return []

    def optimized_monitor_and_grab(self):
        """优化的监控和抢票主循环"""
        print("=" * 60)
        print("🚄 12306智能抢票脚本启动")
        print("=" * 60)
        print(f"出发站: {self.config['from_station']}")
        print(f"到达站: {self.config['to_station']}")
        print(f"出行日期: {self.config['train_date']}")
        print(f"目标席别: {self.config['seat_type']}")
        print(f"优先车次: {', '.join(self.config['train_numbers']) if self.config['train_numbers'] else '无'}")
        print(f"最大查询次数: {self.config['max_query_times']}")
        print("=" * 60)

        # 登录（如果未登录）
        if not self.logged_in:
            if not self.login_12306():
                print("✗ 登录失败，程序退出")
                return

        # 设置查询页面（只需一次）
        if not self.setup_query_page():
            print("✗ 查询页面设置失败")
            return

        # 主查询循环
        start_time = time.time()
        found_trains = []
        success = False

        print("\n🎯 开始监控余票...")
        print("按 Ctrl+C 可随时中断程序")
        print("-" * 60)

        try:
            while (self.query_count < self.config['max_query_times']
                   and not success):

                # 智能查询
                if not self.smart_query_tickets():
                    # 查询失败时短暂等待后继续
                    time.sleep(2)
                    continue

                # 快速查找可用车次
                available_trains = self.fast_find_available_trains()

                if available_trains:
                    # 按优先级排序（优先车次在前）
                    available_trains.sort(key=lambda x: (not x['priority'], x['train_number']))

                    # 显示找到的车次
                    if not found_trains or available_trains[0]['train_number'] != found_trains[0]['train_number']:
                        found_trains = available_trains
                        print(f"\n✅ 发现可用车次 ({len(available_trains)}个):")
                        for i, train in enumerate(available_trains[:3], 1):
                            priority = "⭐" if train['priority'] else "  "
                            print(f"   {priority} {train['train_number']} "
                                  f"({train['departure']}→{train['arrival']}) "
                                  f"{self.config['seat_type']}: {train['seat_status']}")

                        # 尝试预订第一个车次
                        if self.book_ticket_by_number(available_trains[0]['train_number']):
                            success = True
                            break

                # 计算进度
                progress = (self.query_count / self.config['max_query_times']) * 100

                # 每10次查询显示一次状态
                if self.query_count % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"\n📊 进度: {self.query_count}/{self.config['max_query_times']}次 "
                          f"({progress:.1f}%) | 用时: {elapsed:.0f}秒")

                # 动态调整查询间隔
                actual_interval = self.config['base_refresh_interval']
                if self.query_count % 30 == 0:
                    # 每30次查询稍微延长间隔，避免被限流
                    actual_interval += random.uniform(1, 3)

                time.sleep(actual_interval)

        except KeyboardInterrupt:
            print("\n\n⚠️ 用户中断监控")
        except Exception as e:
            print(f"\n✗ 监控过程中出现错误: {e}")

        # 显示统计信息
        elapsed_time = time.time() - start_time
        print("\n" + "=" * 60)
        print("📈 查询统计")
        print("-" * 60)
        print(f"总查询次数: {self.query_count}次")
        print(f"总用时: {elapsed_time:.1f}秒")
        print(f"平均查询间隔: {elapsed_time / max(self.query_count, 1):.1f}秒/次")

        if success:
            print("🎉 抢票成功！请尽快完成支付！")
        elif found_trains:
            print(f"⚠️ 发现{len(found_trains)}个车次但预订失败")
            print("请尝试手动预订或调整设置重试")
        else:
            print("❌ 未找到符合条件的车次")

        print("=" * 60)

    def book_ticket_by_number(self, train_number):
        """根据车次号预订车票"""
        print(f"\n🔥 尝试预订: {train_number}")

        try:
            # 查找该车次的预订按钮
            book_buttons = self.driver.find_elements(
                By.XPATH, f"//a[contains(@onclick, '{train_number}')]"
            )

            if not book_buttons:
                book_buttons = self.driver.find_elements(
                    By.XPATH, f"//a[contains(text(), '{train_number}')]/../following-sibling::td/a"
                )

            if book_buttons:
                # 使用JavaScript点击，避免元素遮挡等问题
                self.driver.execute_script("arguments[0].click();", book_buttons[0])
                print(f"✓ 已点击预订按钮: {train_number}")

                # 等待跳转
                time.sleep(2)

                # 这里可以添加后续的乘客选择和订单提交逻辑
                print("⚠️ 预订流程已启动，请根据实际情况完善后续步骤")

                return True
            else:
                print(f"✗ 未找到车次 {train_number} 的预订按钮")
                return False

        except Exception as e:
            print(f"✗ 预订失败: {e}")
            return False

    # 保留原有的login_12306方法和其他必要方法...
    def login_12306(self):
        """简化登录方法"""
        print("正在登录...")
        try:
            self.driver.get('https://kyfw.12306.cn/otn/resources/login.html')
            time.sleep(2)

            # 这里简化登录流程，实际需要根据12306页面调整
            # 建议第一次使用时手动登录，然后保存cookies
            print("请手动完成登录...")
            input("登录完成后按回车继续...")

            self.logged_in = True
            return True

        except Exception as e:
            print(f"登录失败: {e}")
            return False


def main():
    """主函数"""
    # 检查配置文件
    config_file = 'ticket_config.json'
    if not os.path.exists(config_file):
        print("请先创建配置文件并填写相关信息")
        return

    # 创建抢票实例
    grabber = OptimizedTicketGrabber(config_file)

    try:
        # 运行优化后的抢票程序
        grabber.optimized_monitor_and_grab()

    except Exception as e:
        print(f"程序运行出错: {e}")
    finally:
        # 清理资源
        if hasattr(grabber, 'driver'):
            grabber.driver.quit()


if __name__ == "__main__":
    main()