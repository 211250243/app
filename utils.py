import json
import os

from PySide6.QtCore import Signal, Qt, QTimer, QDateTime, QPoint
from PySide6.QtGui import QMovie, QPainter, QLinearGradient, QColor, QPen, QFont
from PySide6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QProgressBar, QLabel, QWidget, QApplication, QProgressDialog

import config




class ProgressDialog(QProgressDialog):
    """
    基于QProgressDialog的进度展示框
    """
    def __init__(self, parent=None, msg="请稍等..."):
        super().__init__(parent)
        self.setWindowTitle(msg["title"])
        self.setLabelText(msg["text"])
        self.setRange(0, 100)
        self.setCancelButton(None)

# class ProgressDialog(QDialog):
#     """
#     进度展示框
#     """
#     def __init__(self, parent=None, msg="请稍等..."):
#         super().__init__(parent)
#         self.setWindowTitle("Upload Progress")
#         self.setModal(True)
#         self.setFixedSize(300, 100)

#         layout = QVBoxLayout()
#         self.label = QLabel(msg, self)
#         self.progress_bar = QProgressBar(self)
#         self.progress_bar.setRange(0, 100)
#         self.progress_bar.setValue(0)
#         self.progress_bar.setTextVisible(True) # 显示进度值

#         layout.addWidget(self.label)
#         layout.addWidget(self.progress_bar)
#         self.setLayout(layout)

#     def setValue(self, value):
#         print(f"设置进度值：{value}")
#         self.progress_bar.setValue(value)

def show_message_box(title: str, message: str, icon_type: QMessageBox.Icon, parent=None):
    """
    显示一个弹窗来提示用户当前的状态
    :param title: 弹窗标题
    :param message: 弹窗显示的信息
    :param icon_type: 弹窗的图标类型，如：QMessageBox.Information、QMessageBox.Warning、QMessageBox.Critical
    """
    msg_box = QMessageBox(parent)  # 创建一个消息框
    msg_box.setIcon(icon_type)  # 设置图标
    msg_box.setWindowTitle(title)  # 设置标题
    msg_box.setText(message)  # 设置显示的消息内容
    msg_box.exec()  # 显示弹窗

def check_and_create_path(path: str) -> bool:
    """
    检查路径是否合法，如果路径不存在则创建该路径
    :param path: 要检查或创建的路径
    :return: 如果路径有效（存在或创建成功），返回 True；否则返回 False
    """
    # 检查路径是否为空
    if not path:
        show_message_box("错误", "路径不能为空！", QMessageBox.Critical)
        return False
    # 如果路径存在并且是有效的目录
    if os.path.isdir(path):
        return True
    # 检查路径是否为合法（绝对路径）
    if not os.path.isabs(path):
        show_message_box("错误", "路径非法！", QMessageBox.Critical)
        return False
    # 如果路径不存在，尝试创建该路径
    try:
        os.makedirs(path)  # 尝试递归创建路径
        print(f"创建路径：{path}")
        return True
    except Exception as e:
        show_message_box("错误", "无法创建该路径！", QMessageBox.Critical)
        return False

def is_image(file_name: str) -> bool:
    """
    判断文件是否为图片文件
    """
    return file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'))

def join_path(*args) -> str:
    """
    拼接跨平台路径，强制args之中及其之间的分隔符为 /
    """
    return os.path.join(*args).replace("\\", "/")

def update_metadata(key, value):
    """
    更新项目元数据
    """
    metadata_path = config.PROJECT_METADATA_PATH
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        metadata[key] = value
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
    config.PROJECT_METADATA = metadata

class FloatingTimer(QWidget):
    """悬浮计时器，显示应用运行时间"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置窗口属性
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(70, 70)
        
        # 初始化时间计时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.start_time = QDateTime.currentDateTime()
        self.time_str = "00:00:00"
        
        # 拖动相关变量
        self.dragging = False
        self.offset = QPoint()
        
        # 位置跟踪（每100ms检查一次窗口位置变化）
        self.track_timer = QTimer(self)
        self.track_timer.timeout.connect(self.track_window_position)
        self.track_timer.start(100)
        self.last_window_pos = QPoint(0, 0)
        
        # 初始定位
        QTimer.singleShot(100, self.set_initial_position)
    
    def set_initial_position(self):
        """设置初始位置（窗口右上角）"""
        if self.parent() and self.parent().window():
            # 获取父窗口
            parent_window = self.parent().window()
            parent_pos = parent_window.pos()
            
            # 计算右上角位置
            x = parent_pos.x() + parent_window.width() - self.width() - 8
            y = parent_pos.y() + 36
            
            # 移动到计算位置
            self.move(x, y)
            self.last_window_pos = parent_pos
        else:
            # 无父窗口时，移动到屏幕右上角
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.width() - self.width() - 20, 20)
    
    def track_window_position(self):
        """跟踪窗口位置变化"""
        if not self.dragging and self.parent() and self.parent().window():
            parent_window = self.parent().window()
            current_pos = parent_window.pos()
            
            # 窗口位置变化时，同步移动悬浮球
            if current_pos != self.last_window_pos:
                delta_x = current_pos.x() - self.last_window_pos.x()
                delta_y = current_pos.y() - self.last_window_pos.y()
                self.move(self.pos().x() + delta_x, self.pos().y() + delta_y)
                self.last_window_pos = current_pos
    
    def update_time(self):
        """更新显示的时间"""
        current_time = QDateTime.currentDateTime()
        elapsed = self.start_time.msecsTo(current_time)
        hours = elapsed // (1000 * 60 * 60)
        minutes = (elapsed % (1000 * 60 * 60)) // (1000 * 60)
        seconds = (elapsed % (1000 * 60)) // 1000
        self.time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self.update()
        
    def paintEvent(self, event):
        """绘制悬浮球"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制圆形背景
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(52, 152, 219, 200))
        gradient.setColorAt(1, QColor(41, 128, 185, 200))
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(2, 2, self.width()-4, self.height()-4)
        
        # 绘制时间文本
        painter.setPen(QPen(Qt.white, 1))
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, self.time_str)
        
    def mousePressEvent(self, event):
        """开始拖动"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()
            
    def mouseMoveEvent(self, event):
        """拖动悬浮球"""
        if self.dragging:
            self.move(self.mapToGlobal(event.pos() - self.offset))
            
    def mouseReleaseEvent(self, event):
        """结束拖动"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
    
    def mouseDoubleClickEvent(self, event):
        """双击重置计时器"""
        if event.button() == Qt.LeftButton:
            self.start_time = QDateTime.currentDateTime()
            self.update_time()