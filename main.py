import os

from PySide6.QtWidgets import QMainWindow, QApplication, QMessageBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Qt, QTimer

import config
from detect_handler import DetectHandler
from model_handler import ModelHandler
from sample_handler import SampleHandler
from utils import FloatingTimer, check_sample_group, join_path, show_message_box
from http_server import HttpServer


class MainWindow(QMainWindow):
    def __init__(self, floating_timer=None):
        super().__init__()
        # 加载 UI
        self.ui = QUiLoader().load(r'ui\main.ui')
        # 将项目元数据保存为实例属性，便于使用
        config.SAMPLE_PATH = join_path(config.PROJECT_METADATA['project_path'], config.SAMPLE_FOLDER)
        config.MODEL_PATH = join_path(config.PROJECT_METADATA['project_path'], config.MODEL_FOLDER)
        config.DETECT_PATH = join_path(config.PROJECT_METADATA['project_path'], config.DETECT_FOLDER)

        # 处理悬浮计时器
        if floating_timer:
            # 从StartWindow继承计时器
            self.floating_timer = floating_timer
            # 确保计时器使用当前窗口
            QTimer.singleShot(200, self.reset_timer_parent)
        else:
            # 创建新的计时器
            self.floating_timer = FloatingTimer(self.ui)
            self.floating_timer.show()

        # 添加按钮点击事件
        self.ui.startNextButton.clicked.connect(self.switch_to_page_1)
        self.ui.sampleButton.clicked.connect(self.switch_to_page_1)
        self.ui.sampleNextButton.clicked.connect(self.switch_to_page_2)
        self.ui.quickNextButton.clicked.connect(self.switch_to_page_3)
        self.ui.quickDetectButton.clicked.connect(self.switch_to_page_3)
        self.ui.modelNextButton.clicked.connect(self.switch_to_page_3)

        # 设置 SampleWidget
        self.ui.sampleWidget.optionGroup = self.ui.optionGroup # 将 optionGroup 传递给 SampleWidget
        self.sample_handler = SampleHandler(self.ui.sampleWidget)
        # 设置 ModelWidget
        self.model_handler = ModelHandler(self.ui.modelWidget)
        # 设置 DetectWidget    
        self.detect_handler = DetectHandler(self.ui.detectWidget)
        # 连接标签页切换信号
        self.ui.tabWidget.currentChanged.connect(self.on_tab_changed)
        # self.cur_index = self.ui.tabWidget.currentIndex()
        # self.to_next = False # 用于判断是否点击下一步按钮

    def on_tab_changed(self, index):
        """
        标签页切换时，更新样本组
        """
        if index == 1: # 样本标签页
            self.sample_handler.update_sample_group()
        elif index == 2: # 模型标签页
            self.model_handler.update_sample_group()
    def switch_to_page_1(self):
        self.ui.tabWidget.setCurrentIndex(1)
    def switch_to_page_2(self):
        # 检查是否有样本组
        if not check_sample_group():
            return
        # 对接 http_server: 检查样本组是否上传到服务器
        try:
            # 连接服务器，检查样本组是否上传（样本数量是否相等）
            http_server = HttpServer()
            group_id = http_server.get_group_id(config.SAMPLE_GROUP)
            sample_list = http_server.get_sample_list(group_id)
            if len(sample_list) < self.sample_handler.image_count():
                result = show_message_box("提示", "样本组未上传到服务器，是否立即上传？", 
                                         QMessageBox.Question, self.ui, 
                                         buttons=QMessageBox.Yes | QMessageBox.No)
                # 选择是否上传样本组
                if result == QMessageBox.Yes:
                    self.sample_handler.upload_sample_group()
                else:
                    return
        except Exception as e:
            show_message_box("错误", f"连接服务器失败：{str(e)}", QMessageBox.Critical, self.ui)
            return
        # 验证通过，跳转到下一页
        self.ui.tabWidget.setCurrentIndex(2)
    def switch_to_page_3(self):
        self.ui.tabWidget.setCurrentIndex(3)
    # def on_tab_changed(self, index):
        # if index < self.cur_index:
        #     self.ui.tabWidget.setCurrentIndex(self.cur_index)
        #     show_message_box("警告", "请按顺序操作！", QMessageBox.Warning)
        # else:
        #     self.cur_index = index

        # if self.to_next: # 如果是点击下一步按钮，可切换 Tab 页
        #     self.cur_index = index
        # else: # 如果是直接点击 Tab 栏，不可切换 Tab 页
        #     self.ui.tabWidget.setCurrentIndex(self.cur_index)

    # 切换 Tab 页
    # def switch_to_page(self, page_index):
    #     self.to_next = True
    #     self.ui.tabWidget.setCurrentIndex(page_index)
    #     self.to_next = False

    def reset_timer_parent(self):
        """重设计时器父窗口并显示"""
        if hasattr(self, 'floating_timer') and self.floating_timer:
            self.floating_timer.setParent(self.ui)
            self.floating_timer.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.floating_timer.show()
            # 重新定位
            self.floating_timer.set_initial_position()


if __name__ == "__main__":
    # 模拟项目元数据
    config.PROJECT_METADATA = {
        "project_name": "test",
        "project_path": "B:\\Development\\GraduationDesign\\app\\test",
        "description": "",
        "create_time": "2024-12-20 19:47:57",
        "sample_group": "test",
        "model_group": "test"
    }

    config.PROJECT_METADATA_PATH = join_path(config.PROJECT_METADATA['project_path'], config.PROJECT_METADATA_FILE)
    app = QApplication([])
    window = MainWindow()
    window.ui.show()
    app.exec()
