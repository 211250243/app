"""
LoadingAnimation类使用示例
"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer

from loading_text_animation import LoadingAnimation


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("加载动画示例")
        self.setGeometry(100, 100, 500, 400)
        
        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 添加按钮
        self.start_button = QPushButton("显示加载动画 (3秒)")
        self.start_button.clicked.connect(self.show_loading)
        layout.addWidget(self.start_button)
        
        self.start_button2 = QPushButton("显示加载动画 (5秒，自定义文本)")
        self.start_button2.clicked.connect(self.show_loading_with_text)
        layout.addWidget(self.start_button2)
        
        # 初始化加载动画
        self.loading = LoadingAnimation(self)
        
    def show_loading(self):
        """显示加载动画3秒"""
        self.loading.show()
        # 3秒后关闭动画
        QTimer.singleShot(3000, self.loading.close_animation)
        
    def show_loading_with_text(self):
        """显示自定义文本的加载动画5秒"""
        self.loading.set_text("正在处理数据，请稍候...")
        self.loading.show()
        # 5秒后关闭动画
        QTimer.singleShot(5000, self.loading.close_animation)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec()) 