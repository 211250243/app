# 远程服务器配置
SERVER_HOSTNAME = '10.160.22.114'
SERVER_PORT = 20045
SERVER_USERNAME = 'nieercong'
SERVER_PASSWORD = 'NAec19216800.'
SERVER_SAMPLE_PATH = 'data/sample_groups'
SERVER_DOWNLOAD_PATH = 'patchcore/evaluated_results/2025_1_9'

HOSTNAME = '10.160.22.114'
PORT = 20060

# 项目配置
"""
PROJECT_METADATA = {
    "project_name":
    "project_path":
    "description":
    "create_time": "2024-12-20 19:47:57"
}
"""
PROJECT_METADATA = None
PROJECT_METADATA_FILE = 'metadata.json'
PROJECT_METADATA_PATH = None
SAMPLE_FOLDER = 'sample_groups'
SAMPLE_GROUP = None
SAMPLE_PATH = None
SAMPLE_LABEL_TRAIN_GOOD = 'train/good'
SAMPLE_LABEL_TEST = 'test'
SAMPLE_LABEL_TEST_GOOD = 'test/good'
MODEL_FOLDER = 'models'
MODEL_PATH = None
MODEL_GROUP = None
MODEL_PARAMS = None
MODEL_INFO_FILE = 'model.json'
DETECT_FOLDER = 'detect'
DETECT_PATH = None
DETECT_SAMPLE_GROUP = None
DETECT_LIST = None

# 检测阈值设置
DEFECT_THRESHOLD = 0.5  # 默认阈值为0.5，高于此值判断为异常

# 参数配置
TEST_RATIO = 0.1