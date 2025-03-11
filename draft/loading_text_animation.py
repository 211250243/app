"""
纯文本动画：使用Unicode字符（⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏）创建旋转动画，不需要额外的GIF文件。

美观的界面：
    半透明黑色背景覆盖整个父窗口
    带圆角的深色容器放置动画和文本
    清晰的白色文字显示状态信息

易于使用：
   # 创建加载动画
   loading = LoadingAnimation(parent_widget)
   # 设置显示文本（可选）
   loading.set_text("正在处理数据...")
   # 显示动画
   loading.show()
   # 在合适的时机关闭动画
   loading.close_animation()

自动适应：会自动调整大小以匹配父窗口，确保覆盖整个UI区域。
可自定义：提供了set_text方法更改显示的文本。
使用示例：创建了loading_example.py，演示如何在实际应用中使用这个类。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer

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
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建一个容器窗口放置动画和文本
        container = QWidget()
        container.setStyleSheet("""
            background-color: rgba(40, 40, 40, 200);
            border-radius: 10px;
            padding: 20px;
        """)
        container_layout = QVBoxLayout(container)
        
        # 创建文本式动画标签
        self.loading_label = QLabel(self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setMinimumSize(50, 50)
        self.loading_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
        """)
        
        # 创建显示文本标签
        self.text_label = QLabel("加载中...", self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("color: white; font-size: 14px; margin-top: 10px;")
        
        # 添加到容器布局
        container_layout.addWidget(self.loading_label)
        container_layout.addWidget(self.text_label)
        container_layout.setAlignment(Qt.AlignCenter)
        
        # 添加容器到主布局
        main_layout.addWidget(container, 0, Qt.AlignCenter)
        
        # 动画计时器
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_frame = 0
        self.animation_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        
    def showEvent(self, event):
        """窗口显示时开始播放动画"""
        if self.parent():
            # 调整大小以匹配父窗口
            self.setGeometry(self.parent().rect())
            self.background.setGeometry(self.rect())
        
        # 开始播放动画
        self.animation_timer.start(100)
        super().showEvent(event)
        
    def update_animation(self):
        """更新动画帧"""
        self.loading_label.setText(self.animation_chars[self.animation_frame])
        self.animation_frame = (self.animation_frame + 1) % len(self.animation_chars)
        
    def resizeEvent(self, event):
        """调整大小时确保背景覆盖整个区域"""
        self.background.setGeometry(self.rect())
        super().resizeEvent(event)
        
    def set_text(self, text):
        """设置加载时显示的文本"""
        self.text_label.setText(text)
        
    def close_animation(self):
        """停止动画并关闭窗口"""
        self.animation_timer.stop()
        self.close()