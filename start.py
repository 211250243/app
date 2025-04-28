import json
import os
from pathlib import Path  # 用于处理文件路径
from PySide6.QtCore import QDateTime, Signal, Qt, QSize, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow, QDialog, QMessageBox, 
                              QLabel, QListWidgetItem, QWidget, QHBoxLayout, QVBoxLayout)
from PySide6.QtUiTools import QUiLoader

import config
from main import MainWindow
from utils import join_path, show_message_box, check_and_create_path, FloatingTimer, create_file_dialog

# 在程序启动时设置工作目录为应用程序所在目录!!!
os.chdir(os.path.dirname(os.path.realpath(__file__)))

class NewProjectDialog(QDialog):
    """
    新建项目对话框 - 使用UI文件加载
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui/new_project.ui')
        
        # 设置主窗口属性和窗口标题
        self.setWindowTitle(self.ui.windowTitle())
        self.setFixedSize(self.ui.width(), self.ui.height())

        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.ui)

        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.create_new_project)
        self.ui.pathButton.clicked.connect(self.select_path)
        self.ui.cancelButton.clicked.connect(self.reject)
        
        # 添加快捷键
        self.shortcut_create = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.shortcut_create.activated.connect(self.create_new_project)
        
        self.shortcut_cancel = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.shortcut_cancel.activated.connect(self.reject)

        self.path = ""  # 用于保存项目的路径
        
        # 设置焦点到名称输入框
        self.ui.nameEdit.setFocus()

    def create_new_project(self):
        """
        创建新项目并保存到指定路径
        """
        # 检查项目名称是否合法
        project_name = self.ui.nameEdit.text()
        if not project_name:
            show_message_box("错误", "项目名称不能为空！", QMessageBox.Critical)
            return
        if not project_name.isidentifier():  # 判断是否是合法的标识符
            show_message_box("错误", "项目名称不合法！只能包含字母、数字和下划线，且不能以数字开头", QMessageBox.Critical)
            return

        # 检查路径是否存在
        self.path = self.ui.pathEdit.text()
        if not check_and_create_path(self.path):
            return  # 如果没有指定路径或路径非法，返回

        # 在指定路径下创建一个名为 project_name 的文件夹
        project_folder = join_path(self.path, project_name)
        # 检查该文件夹是否已经存在，如果不存在则创建，如果存在则提示用户
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
            print(f"创建文件夹: {project_folder}")
        else:
            show_message_box("错误", "项目已存在，请选择其他路径！", QMessageBox.Critical)
            return

        # 生成项目的元数据
        metadata = {
            "project_name": project_name,
            "project_path": str(project_folder),
            "description": self.ui.descriptionEdit.toPlainText(),
            "create_time": QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        }

        # 保存到 metadata.json
        metadata_file_path = join_path(project_folder, "metadata.json")
        with open(metadata_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

        # 添加到最近项目列表
        self.add_to_recent_projects(project_folder)

        # 保存项目路径，供父窗口访问
        self.project_folder = project_folder
        
        # 接受对话框
        self.accept()

    def add_to_recent_projects(self, project_path):
        """将项目添加到最近项目列表"""
        recent_file = join_path(os.path.expanduser("~"), ".visioCraft", "recent_projects.json")
        os.makedirs(os.path.dirname(recent_file), exist_ok=True)
        
        recent_projects = []
        if os.path.exists(recent_file):
            try:
                with open(recent_file, "r", encoding="utf-8") as f:
                    recent_projects = json.load(f)
            except:
                recent_projects = []
        
        # 确保列表格式正确
        if not isinstance(recent_projects, list):
            recent_projects = []
            
        # 将当前项目添加到列表开头
        if project_path in recent_projects:
            recent_projects.remove(project_path)
        recent_projects.insert(0, project_path)
        
        # 限制最近项目数量
        recent_projects = recent_projects[:10]
        
        # 保存更新后的列表
        with open(recent_file, "w", encoding="utf-8") as f:
            json.dump(recent_projects, f, ensure_ascii=False)

    def select_path(self):
        """
        让用户选择保存路径
        """
        folder = create_file_dialog(title="选择项目保存路径", is_folder=True)
        if folder:
            self.path = folder
            self.ui.pathEdit.setText(self.path)
            
    def get_project_folder(self):
        """
        获取创建的项目文件夹路径
        """
        return getattr(self, 'project_folder', None)


# 开始界面窗口
class StartWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 创建UI对象并设置界面
        self.ui = QUiLoader().load(r'ui/start.ui')
        
        # 初始化界面
        self.init_ui()
        
        # 拖放设置（拖动文件夹到窗口）
        self.ui.setAcceptDrops(True) # 允许接收拖放事件
        self.ui.installEventFilter(self) # 安装事件过滤器

        # 创建悬浮计时器
        self.floating_timer = FloatingTimer(self.ui)
        self.floating_timer.show()
        
        # 加载最近项目列表
        self.load_recent_projects()
        
    def init_ui(self):
        """初始化界面和事件连接"""
        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.create_new_archive)
        self.ui.openButton.clicked.connect(self.open_existing_archive)
        
        # 设置最近项目列表双击事件
        self.ui.recentList.itemDoubleClicked.connect(self.on_recent_item_clicked)
        
        # 添加快捷键
        self.shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self.ui)
        self.shortcut_new.activated.connect(self.create_new_archive)
        
        self.shortcut_open = QShortcut(QKeySequence("Ctrl+O"), self.ui)
        self.shortcut_open.activated.connect(self.open_existing_archive)
        
        # 更新按钮提示
        self.ui.newButton.setToolTip("创建新的项目 (Ctrl+N)")
        self.ui.openButton.setToolTip("从磁盘中打开现有项目 (Ctrl+O)")
    
    def load_recent_projects(self):
        """加载最近项目列表到UI中"""
        self.ui.recentList.clear()
        recent_file = join_path(os.path.expanduser("~"), ".visioCraft", "recent_projects.json")
        if not os.path.exists(recent_file):
            self.ui.recentLabel.setVisible(False)
            self.ui.recentList.setVisible(False)
            return
        try:
            with open(recent_file, "r", encoding="utf-8") as f:
                recent_projects = json.load(f)
            # 如果最近项目列表为空，隐藏最近项目区域
            if not recent_projects:
                self.ui.recentLabel.setVisible(False)
                self.ui.recentList.setVisible(False)
                return
            # 遍历最近项目列表
            for project_path in recent_projects:
                metadata_path = join_path(project_path, "metadata.json")
                project_name = os.path.basename(project_path)
                create_time = ""
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                        project_name = metadata.get("project_name", project_name)
                        create_time = metadata.get("create_time", "")
                    except:
                        pass
                # 创建一个自定义的 widget 来显示项目名称和创建时间
                item_widget = QWidget()
                layout = QHBoxLayout(item_widget)
                layout.setContentsMargins(16, 0, 16, 0) # 依次为左、上、右、下                
                name_label = QLabel(project_name)
                name_label.setStyleSheet("color: rgba(51, 51, 51, 180);")
                name_label.setAlignment(Qt.AlignVCenter) # 垂直居中
                layout.addWidget(name_label)
                
                time_label = QLabel(create_time)
                time_label.setStyleSheet("color: rgba(128, 128, 128, 150); font-size: 9pt;")
                time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                layout.addWidget(time_label)
                
                item = QListWidgetItem()
                item.setSizeHint(QSize(item_widget.sizeHint().width(), 22))
                item.setData(Qt.UserRole, project_path)
                
                self.ui.recentList.addItem(item)
                self.ui.recentList.setItemWidget(item, item_widget)
                
        except Exception as e:
            print(f"加载最近项目失败: {str(e)}")
            self.ui.recentLabel.setVisible(False)
            self.ui.recentList.setVisible(False)
    
    def on_recent_item_clicked(self, item):
        """当最近项目被点击时"""
        project_path = item.data(Qt.UserRole)
        if not os.path.exists(project_path):
            # 从界面列表中移除
            row = self.ui.recentList.row(item)
            self.ui.recentList.takeItem(row)
            # 从本地存储中移除
            self.remove_from_recent_projects(project_path)
            # 如果列表为空，隐藏最近项目区域
            if self.ui.recentList.count() == 0:
                self.ui.recentLabel.setVisible(False)
                self.ui.recentList.setVisible(False)
            # 显示提示信息
            show_message_box("提示", "该项目已被移除或路径不存在，已从最近项目列表中删除", QMessageBox.Information)
            return
            
        self.open_existing_archive(project_path)

    def remove_from_recent_projects(self, project_path):
        """从最近项目列表中移除指定项目"""
        recent_file = join_path(os.path.expanduser("~"), ".visioCraft", "recent_projects.json")
        if os.path.exists(recent_file):
            try:
                with open(recent_file, "r", encoding="utf-8") as f:
                    recent_projects = json.load(f)
                if project_path in recent_projects:
                    recent_projects.remove(project_path)
                    # 保存更新后的列表
                    with open(recent_file, "w", encoding="utf-8") as f:
                        json.dump(recent_projects, f, ensure_ascii=False)
            except Exception as e:
                print(f"移除最近项目失败: {str(e)}")

    def eventFilter(self, obj, event):
        """事件过滤器，处理拖放事件"""
        if obj == self.ui:
            if event.type() == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return True
            elif event.type() == QEvent.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(obj, event)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        """当拖动进入窗口时的处理"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        """当放下拖动项时的处理"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                folder_path = urls[0].toLocalFile()
                if os.path.isdir(folder_path):
                    self.check_and_open_project(folder_path)
    
    def check_and_open_project(self, folder_path):
        """检查并打开项目文件夹"""
        metadata_path = join_path(folder_path, config.PROJECT_METADATA_FILE)
        if os.path.exists(metadata_path):
            self.open_existing_archive(folder_path)
        else:
            show_message_box("错误", "选择的文件夹不是有效的项目文件夹，没有找到 metadata.json 文件", QMessageBox.Critical)

    def create_new_archive(self):
        """
        打开新建项目窗口
        """
        # 创建新建项目窗口
        new_project_dialog = NewProjectDialog(self.ui)
        
        # 显示对话框
        if new_project_dialog.exec() == QDialog.Accepted:
            # 获取项目文件夹路径
            project_folder = new_project_dialog.get_project_folder()
            if project_folder:
                print("新建项目成功，项目路径：", project_folder)
                # 打开项目
                self.open_existing_archive(project_folder)
        else:
            print("取消新建项目")

    def open_existing_archive(self, folder=None):
        """
        点击打开归档按钮，弹出文件选择对话框
        """
        if not folder:
            folder = create_file_dialog(title="选择项目文件夹", is_folder=True)
        if folder:
            # 检查项目文件夹是否存在
            if not os.path.exists(folder):
                show_message_box("错误", "项目文件夹不存在", QMessageBox.Critical)
                return
                
            # 检查文件夹中是否存在 metadata.json
            metadata_path = config.PROJECT_METADATA_PATH = join_path(folder, config.PROJECT_METADATA_FILE)
            if os.path.exists(metadata_path):
                try:
                    # 读取 metadata.json
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        config.PROJECT_METADATA = json.load(f)
                        print("项目信息：", config.PROJECT_METADATA)
                    
                    # 添加到最近项目列表
                    self.add_to_recent_projects(folder)
                    
                    # 显示读取的项目信息
                    self.open_main_window()
                except Exception as e:
                    show_message_box("错误", f"读取项目元数据失败: {str(e)}", QMessageBox.Critical)
            else:
                show_message_box("错误", "选择的文件夹没有找到 metadata.json 文件", QMessageBox.Critical)
    
    def add_to_recent_projects(self, project_path):
        """将项目添加到最近项目列表"""
        recent_file = join_path(os.path.expanduser("~"), ".visioCraft", "recent_projects.json")
        os.makedirs(os.path.dirname(recent_file), exist_ok=True)
        
        recent_projects = []
        if os.path.exists(recent_file):
            try:
                with open(recent_file, "r", encoding="utf-8") as f:
                    recent_projects = json.load(f)
            except:
                recent_projects = []
        
        # 确保列表格式正确
        if not isinstance(recent_projects, list):
            recent_projects = []
            
        # 将当前项目添加到列表开头
        if project_path in recent_projects:
            recent_projects.remove(project_path)
        recent_projects.insert(0, project_path)
        
        # 限制最近项目数量
        recent_projects = recent_projects[:10]
        
        # 保存更新后的列表
        with open(recent_file, "w", encoding="utf-8") as f:
            json.dump(recent_projects, f, ensure_ascii=False)

    def open_main_window(self):
        """
        跳转到主窗口，显示项目的详细信息
        """
        # 创建主窗口并传递计时器
        self.main_window = MainWindow(floating_timer=self.floating_timer)
        self.main_window.ui.show()  # 显示主窗口
        self.ui.close()  # 关闭开始窗口


if __name__ == "__main__":
    app = QApplication([])

    window = StartWindow()
    window.ui.show()

    app.exec()