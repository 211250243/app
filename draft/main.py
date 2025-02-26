from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from draft.monitor import RemoteFileMonitor
from draft.ui import DetectWidget


def start_detection(host, user, pwd, path, widget):
    # 创建监控对象
    print("创建监控对象")
    monitor = RemoteFileMonitor(host, user, pwd, path)
    thread = QThread()
    monitor.moveToThread(thread)

    # 连接信号
    monitor.new_image_detected.connect(widget.add_image)

    # 线程管理
    thread.started.connect(monitor.start_monitoring)
    thread.finished.connect(monitor.stop_monitoring)
    thread.start()

    return thread  # 返回线程对象以便管理


# 使用示例
if __name__ == "__main__":
    app = QApplication([])

    # 创建展示组件
    detect_ui = DetectWidget()
    detect_ui.show()

    # 启动监控线程
    ssh_thread = start_detection(
        host="10.160.22.114",
        user="nieercong",
        pwd="NAec19216800.",
        path="data/samples",
        widget=detect_ui
    )

    app.exec()
    ssh_thread.quit()  # 安全退出线程