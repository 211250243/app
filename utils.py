import json
import os
import shutil

from PySide6.QtCore import QCoreApplication, Qt, QTimer, QDateTime, QPoint, QSize
from PySide6.QtGui import QMovie, QPainter, QLinearGradient, QColor, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QLabel, QWidget, QApplication, QProgressDialog, QPushButton, QFileDialog

import config



class ProgressDialog(QProgressDialog):
    """
    基于QProgressDialog的进度展示框
    """
    def __init__(self, parent=None, msg={"title": "处理中", "text": "请稍等..."}):
        super().__init__(parent)
        self.setWindowTitle(msg["title"])
        self.setLabelText(msg["text"])
        self.setRange(0, 100)
        self.setCancelButton(None)
        self.setModal(True)
        self.setMinimumDuration(0)  # 立即显示，不等待
        self.setMinimumSize(300, 100)
        
        # 应用样式
        self.setStyleSheet("""
            QProgressDialog {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            QLabel {
                color: #333;
                font-size: 11pt;
                font-family: 'Microsoft YaHei UI';
                margin-bottom: 5px;
            }
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 3px;
                background-color: #f0f0f0;
                text-align: center;
                min-height: 12px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, 
                                              stop:0 #4da6ff, stop:1 #1e88e5);
                border-radius: 3px;
            }
        """)
    
    def showEvent(self, event):
        """当进度对话框显示时确保UI更新"""
        super().showEvent(event)
        QCoreApplication.processEvents()  # 立即处理所有挂起的UI事件

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

def show_message_box(title: str, message: str, icon_type: QMessageBox.Icon, parent=None, buttons=QMessageBox.Ok, details=None, custom_style=True):
    """
    显示一个美化的弹窗来提示用户当前的状态
    
    Args:
        title: 弹窗标题
        message: 弹窗显示的信息
        icon_type: 弹窗的图标类型，如：QMessageBox.Information、QMessageBox.Warning、QMessageBox.Critical
        parent: 父窗口
        buttons: 显示的按钮，默认为确定按钮
        details: 详细信息（可选）
        custom_style: 是否使用自定义样式，默认为True
    
    Returns:
        用户点击的按钮
    """
    msg_box = QMessageBox(parent)  # 创建一个消息框
    msg_box.setIcon(icon_type)  # 设置图标
    msg_box.setWindowTitle(title)  # 设置标题
    msg_box.setText(message)  # 设置显示的消息内容
    msg_box.setStandardButtons(buttons)  # 设置按钮
    
    # 添加详细信息（如果有）
    if details:
        msg_box.setDetailedText(details)
    
    # 应用自定义样式
    if custom_style:
        # 保留窗口边框和标题栏，不使用无边框模式
        # msg_box.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        # msg_box.setAttribute(Qt.WA_TranslucentBackground)
        
        # 自定义样式表
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #f8f9fa;
                border-radius: 5px;
                padding: 10px;
            }
            QLabel {
                color: #212529;
                font-size: 14px;
                margin-bottom: 10px;
                min-height: 32px;
                qproperty-alignment: AlignVCenter;
            }
            /* 图标和文本标签垂直居中对齐 */
            QMessageBox QLabel {
                alignment: center;
            }
            QMessageBox QLabel#qt_msgbox_label { /* 消息框中的文本标签 */
                qproperty-alignment: 'AlignVCenter | AlignLeft';
            }
            QMessageBox QLabel#qt_msgboxex_icon_label { /* 消息框中的图标标签 */
                qproperty-alignment: 'AlignVCenter | AlignCenter';
                padding-right: 10px;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #0069d9;
            }
            QPushButton:pressed {
                background-color: #0062cc;
            }
            QPushButton[text="取消"], QPushButton[text="Cancel"] {
                background-color: #6c757d;
            }
            QPushButton[text="取消"]:hover, QPushButton[text="Cancel"]:hover {
                background-color: #5a6268;
            }
            QTextEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        
        # 设置不同类型消息框的特殊样式
        for button in msg_box.findChildren(QPushButton):
            if button.text() in ["确定", "OK"]:
                if icon_type == QMessageBox.Warning:
                    # 警告消息使用黄色主题
                    button.setStyleSheet("""
                        background-color: #ffc107;
                        color: #212529;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 16px;
                        font-size: 13px;
                        min-width: 80px;
                    """)
                elif icon_type == QMessageBox.Critical:
                    # 错误消息使用红色主题
                    button.setStyleSheet("""
                        background-color: #dc3545;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 16px;
                        font-size: 13px;
                        min-width: 80px;
                    """)
    
    # 显示弹窗并返回结果
    return msg_box.exec()

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

def copy_image(file_path, dest_path):
    """
    复制图片到, 并修改权限为可读写
    """
    dest_path = join_path(dest_path, os.path.basename(file_path))
    shutil.copy(file_path, dest_path)
    os.chmod(dest_path, 0o777)

def check_sample_group():
    """
    检查是否存在样本组
    """
    if not config.SAMPLE_GROUP:
        show_message_box("错误", "请先创建或导入样本组！", QMessageBox.Critical)
        return False
    print(f"样本组存在: {config.SAMPLE_GROUP}")
    return True

def check_detect_sample_group():
    """
    检查是否存在检测样本组
    """
    if not config.DETECT_SAMPLE_GROUP:
        show_message_box("错误", "请先创建或导入检测样本组！", QMessageBox.Critical)
        return False
    print(f"检测样本组存在: {config.DETECT_SAMPLE_GROUP}")
    return True
    
def check_model_group():
    """
    检查是否存在模型组
    """
    if not config.MODEL_GROUP:
        show_message_box("错误", "请先创建或导入模型组！", QMessageBox.Critical)
        return False
    print(f"模型组存在: {config.MODEL_GROUP}")
    return True

def get_model_status(model_group):
        """
        从本地获取模型组状态
        """
        model_info_path = join_path(config.MODEL_PATH, model_group, config.MODEL_INFO_FILE)
        if os.path.exists(model_info_path):
            with open(model_info_path, 'r', encoding='utf-8') as f:
                model_info = json.load(f)
                return model_info.get("status")
        return -1

def load_metadata():
    """
    从本地加载项目的元数据
    """    
    if os.path.exists(config.PROJECT_METADATA_PATH):
        try:
            with open(config.PROJECT_METADATA_PATH, 'r', encoding='utf-8') as file:
                metadata = json.load(file)
                config.PROJECT_METADATA = metadata
                print(f"加载项目元数据: {config.PROJECT_METADATA}")
                # 同步配置信息
                config.SAMPLE_GROUP = metadata.get('sample_group')
                config.MODEL_GROUP = metadata.get('model_group')
                config.MODEL_PARAMS = metadata.get('model_params')
                config.DETECT_SAMPLE_GROUP = metadata.get('detect_sample_group')
                # 加载阈值设置
                if 'defect_threshold' in metadata:
                    config.DEFECT_THRESHOLD = metadata.get('defect_threshold')
                    print(f"加载缺陷检测阈值: {config.DEFECT_THRESHOLD}")
        except Exception as e:
            print(f"加载元数据失败: {str(e)}")
            config.PROJECT_METADATA = None
    else:
        print(f"元数据文件不存在: {config.PROJECT_METADATA_PATH}")
        config.PROJECT_METADATA = None

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

class LoadingAnimation(QWidget):
    """通用加载动画类，在UI上显示一个旋转的加载动画"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置为无边框窗口并使背景透明
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 创建半透明背景
        self.background = QWidget(self)
        self.background.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        
        # 创建加载动画标签
        self.loading_label = QLabel(self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        
        # 从资源文件加载动画GIF
        self.movie = QMovie("ui/gif/loading.gif")
        self.loading_label.setMovie(self.movie)
        
        # 设置动画大小
        self.movie.setScaledSize(QSize(50, 50))
        
        # 创建显示文本标签
        self.text_label = QLabel("加载中...", self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        
        # 创建垂直布局放置加载图标和文本
        layout = QVBoxLayout()
        layout.addWidget(self.loading_label)
        layout.addWidget(self.text_label)
        layout.setAlignment(Qt.AlignCenter)
        
        # 设置主布局
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(layout)
        main_layout.setAlignment(Qt.AlignCenter)
        self.setLayout(main_layout)
        
    def showEvent(self, event):
        """窗口显示时开始播放动画"""
        if self.parent():
            # 调整大小以匹配父窗口
            self.setGeometry(self.parent().rect())
            self.background.setGeometry(self.rect())
        
        # 开始播放动画
        self.movie.start()
        super().showEvent(event)
        QCoreApplication.processEvents() # 立即处理所有挂起的UI事件
        
    def resizeEvent(self, event):
        """调整大小时确保背景覆盖整个区域"""
        self.background.setGeometry(self.rect())
        super().resizeEvent(event)
        
    def set_text(self, text):
        """设置加载时显示的文本"""
        self.text_label.setText(text)
        
    def close_animation(self):
        """停止动画并关闭窗口"""
        self.movie.stop()
        self.close()

def create_file_dialog(title="选择文件", parent=None, is_folder=True, file_filter="", accept_mode=QFileDialog.AcceptOpen, file_mode=QFileDialog.AnyFile, default_filename=""):
    """
    创建一个居中显示的文件选择对话框
    
    Args:
        title (str): 对话框标题
        parent (QWidget): 父窗口，传入 None 则显示在系统屏幕中心
        is_folder (bool): 是否选择文件夹
        file_filter (str): 文件过滤器 如 "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp *.heic *.heif *.svg *.raw *.cr2 *.nef *.arw *.psd *.jp2 *.j2k *.dpx)"
        accept_mode (QFileDialog.AcceptMode): 接受模式
        file_mode (QFileDialog.FileMode): 文件选择模式
        default_filename (str): 默认文件名
        
    Returns:
        str | list[str] | None: 选择的文件路径或文件夹路径，取消则返回 None
    """
    # 创建静态对话框选项
    options = QFileDialog.Options()
    options |= QFileDialog.DontUseNativeDialog  # 使用 Qt 的对话框，而不是系统原生对话框
    
    # 设置对话框模式和标题
    if is_folder:
        directory = QFileDialog.getExistingDirectory(
            parent, 
            title,
            options=options
        )
        return directory
    else:
        if file_mode == QFileDialog.ExistingFiles:
            files, _ = QFileDialog.getOpenFileNames(
                parent,
                title,
                "",
                file_filter,
                options=options
            )
            return files
        else:
            if accept_mode == QFileDialog.AcceptOpen:
                file, _ = QFileDialog.getOpenFileName(
                    parent,
                    title,
                    "",
                    file_filter,
                    options=options
                )
            else:
                file, _ = QFileDialog.getSaveFileName(
                    parent,
                    title,
                    default_filename if default_filename else "",
                    file_filter,
                    options=options
                )
            return file
        

class WatermarkWidget(QWidget):

    def __init__(self, text="Watermark", angle=45, opacity=0.5, parent=None):
        super().__init__(parent)
        self.text = text
        self.angle = angle
        self.opacity = int(255 * opacity)  # 转换为0-255范围
        # 设置控件透明
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 设置半透明颜色
        color = QColor(128, 128, 128, self.opacity)
        painter.setPen(color)
        
        # 设置字体（根据控件大小自适应）
        font_size = max(min(self.width() // 15, 24), 12)
        font = QFont("Arial", font_size)
        painter.setFont(font)
        
        # 计算文本尺寸
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(self.text)
        text_height = fm.height()
        
        # 循环平铺水印
        spacing = int(text_width)  # 水印间距
        for x in range(-self.width(), self.width() * 2, spacing):
            for y in range(-self.height(), self.height() * 2, spacing):
                painter.save()
                # 移动坐标系到当前平铺位置
                painter.translate(x, y)
                # 以文本中心为旋转点
                painter.rotate(self.angle)
                # 绘制文本（居中）
                painter.drawText(
                    -text_width // 2,
                    text_height // 4,  # 微调垂直居中
                    self.text
                )
                painter.restore()