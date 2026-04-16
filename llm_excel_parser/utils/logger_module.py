#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2025/6/25 11:26
#   @FileRole: 通用日志管理模块 - 适用于任何程序的日志系统

import json
import time
import logging
import threading
import multiprocessing
import traceback
import atexit
import asyncio
import contextvars
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler, SMTPHandler

# 配置文件支持（可选依赖）
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

# 日志级别常量
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

# 自定义日志级别
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

# 默认格式常量
DEFAULT_CONSOLE_FMT = '%(asctime)s - %(levelname)s - %(message)s'
DEFAULT_FILE_FMT = '%(asctime)s - %(processName)s - %(threadName)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_DATE_FMT = '%Y-%m-%d %H:%M:%S'


class JSONFormatter(logging.Formatter):
    """JSON格式的日志格式化器，用于结构化日志输出"""

    def __init__(self, fields: Dict[str, str] = None):
        super().__init__()
        self.fields = fields or {
            "timestamp": "asctime",
            "logger": "name",
            "level": "levelname",
            "message": "message",
            "module": "module",
            "thread": "threadName",
            "process": "processName"
        }

    def format(self, record):
        log_data = {}
        for json_key, record_attr in self.fields.items():
            if hasattr(record, record_attr):
                log_data[json_key] = getattr(record, record_attr)

        # 特殊处理时间戳
        if "timestamp" in log_data:
            log_data["timestamp"] = self.formatTime(record)

        # 特殊处理消息
        if "message" in log_data:
            log_data["message"] = record.getMessage()

        return json.dumps(log_data, ensure_ascii=False)


class LoggerManager:
    """
    通用日志管理器类，提供集中式、可配置的日志处理系统
    
    特点:
    - 完全解耦，不依赖任何业务配置
    - 支持多种处理器（Console, File, Rotating, SMTP等）
    - 线程安全和多进程安全
    - 支持异步日志记录
    - 灵活的配置接口
    - 支持JSON结构化日志
    """

    # 单例模式实现
    _instance = None
    _initialized = False
    _lock = threading.RLock()  # 使用递归锁提高安全性

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LoggerManager, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        """初始化日志管理器"""
        with self._lock:
            if not self._initialized:
                self.log_queue = None
                self.log_listener = None
                self.root_logger = None
                self.loggers = {}
                self.handlers = []
                self.is_setup = False
                self._show_shutdown_message = True  # 正式初始化关闭消息属性
                self._initialized = True

    def setup(self,
              handlers: List[logging.Handler] = None,
              level: Union[int, str] = INFO,
              root_formatter: str = None,
              use_queue: bool = None,
              **kwargs):
        """
        高级日志系统设置接口
        """
        with self._lock:
            # 允许重复setup以更新配置 (移除 self.is_setup 的拦截，或者保留拦截但允许强制刷新)
            # 这里如果不移除拦截，后续的重新配置将无效。建议允许重新配置。
            # 为了安全，我们先根据新的参数重新初始化组件。
            # 处理日志级别
            if isinstance(level, str):
                level = getattr(logging, level.upper(), INFO)
            # 自动判断是否需要使用队列
            if use_queue is None:
                use_queue = (
                        multiprocessing.current_process().name != 'MainProcess' or
                        (handlers and len(handlers) > 1)
                )
            # 停止旧的监听器（如果存在）
            if self.log_listener:
                self.log_listener.stop()
                self.log_listener = None
            # 创建新的日志队列（如果启用）
            if use_queue:
                # 重新创建一个新的队列
                self.log_queue = multiprocessing.Queue(-1)
            else:
                self.log_queue = None
            # 配置根日志记录器
            self.root_logger = logging.getLogger()
            self.root_logger.setLevel(level)
            # 清除已有的处理器
            for handler in self.root_logger.handlers[:]:
                self.root_logger.removeHandler(handler)
            # 使用提供的处理器或创建默认处理器
            if handlers is None:
                handlers = [logging.StreamHandler()]
            self.handlers = handlers
            # 设置格式化器
            if root_formatter:
                formatter = logging.Formatter(root_formatter)
                for handler in handlers:
                    if not handler.formatter:
                        handler.setFormatter(formatter)
            # 启动队列监听器（如果启用队列）
            if use_queue and self.log_queue:
                self.log_listener = QueueListener(self.log_queue, *handlers, respect_handler_level=True)
                self.log_listener.start()
            else:
                # 直接添加处理器到根日志记录器
                for handler in handlers:
                    self.root_logger.addHandler(handler)
            # --- 🔥 关键修复：更新所有已存在的 Logger 实例 🔥 ---
            # 遍历缓存的 logger，将它们的 handler 更新为新的 QueueHandler
            for logger_name, logger in self.loggers.items():
                logger.setLevel(DEBUG)  # 确保 logger 自身级别足够低，由 handler 过滤

                # 移除旧的 handler (指向旧队列的 handler)
                for h in logger.handlers[:]:
                    logger.removeHandler(h)

                # 添加新的 handler
                if self.log_queue:
                    queue_handler = QueueHandler(self.log_queue)
                    queue_handler.setLevel(DEBUG)
                    logger.addHandler(queue_handler)
                    logger.propagate = False
                else:
                    logger.propagate = True
            # --------------------------------------------------
            # 注册程序退出时关闭日志监听器
            if not getattr(self, '_atexit_registered', False):
                atexit.register(self.shutdown)
                self._atexit_registered = True
            self.is_setup = True
            return self

    def get_logger(self, name: str):
        """
        获取指定名称的日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            配置好的日志记录器
        """
        with self._lock:
            # 确保日志系统已初始化
            if not self.is_setup:
                self.setup()

            # 检查是否已经创建了该名称的日志记录器
            if name in self.loggers:
                return self.loggers[name]

            # 获取日志记录器
            logger = logging.getLogger(name)
            logger.setLevel(DEBUG)  # 确保记录器级别足够低

            # 清除已有的处理器
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)

            # 如果使用队列，添加QueueHandler
            if self.log_queue:
                queue_handler = QueueHandler(self.log_queue)
                queue_handler.setLevel(DEBUG)
                logger.addHandler(queue_handler)
                logger.propagate = False
            else:
                # 直接使用根日志记录器的处理器
                logger.propagate = True

            # 缓存日志记录器
            self.loggers[name] = logger

            return logger

    def add_handler(self, handler: logging.Handler, dynamic_update: bool = True):
        """动态添加处理器
        
        Args:
            handler: 要添加的日志处理器
            dynamic_update: 是否使用动态更新机制（避免重启监听器）
        """
        with self._lock:
            self.handlers.append(handler)

            if self.log_listener:
                if dynamic_update and hasattr(self.log_listener, 'handlers'):
                    # Python 3.7+ 支持动态添加处理器
                    try:
                        # 尝试动态添加处理器到现有监听器
                        self.log_listener.handlers = self.handlers
                    except (AttributeError, TypeError):
                        # 回退到重启机制
                        self._restart_listener()
                else:
                    # 使用重启机制
                    self._restart_listener()
            else:
                # 直接添加到根日志记录器
                self.root_logger.addHandler(handler)

    def _restart_listener(self):
        """重启日志监听器"""
        if self.log_listener:
            try:
                self.log_listener.stop()
            except Exception as e:
                logging.getLogger(__name__).warning(f"停止日志监听器时出错: {e}")

        if self.log_queue:
            self.log_listener = QueueListener(self.log_queue, *self.handlers, respect_handler_level=True)
            try:
                self.log_listener.start()
            except Exception as e:
                logging.getLogger(__name__).error(f"启动日志监听器时出错: {e}")

    def remove_handler(self, handler: logging.Handler):
        """动态移除处理器"""
        with self._lock:
            if handler in self.handlers:
                self.handlers.remove(handler)

                if self.log_listener:
                    self._restart_listener()
                else:
                    self.root_logger.removeHandler(handler)

    def reset(self):
        """重置日志系统，允许重新初始化"""
        with self._lock:
            self.shutdown()
            self.log_queue = None
            self.log_listener = None
            self.root_logger = None
            self.loggers.clear()
            self.handlers.clear()
            self.is_setup = False

    def shutdown(self, grace_period: float = 0.5, force: bool = False):
        """
        关闭日志系统，确保所有日志消息都被处理
        
        Args:
            grace_period: 优雅关闭等待时间
            force: 是否强制关闭
        """
        with self._lock:
            if self.log_listener is not None:
                try:
                    # 确保所有日志消息都被处理
                    if self.log_queue is not None:
                        try:
                            # 检查队列大小或强制关闭
                            if self.log_queue.qsize() > 0 or force:
                                # 添加结束标记
                                end_marker = logging.LogRecord(
                                    name="END", level=INFO,
                                    pathname="", lineno=0,
                                    msg="End of logging", args=(), exc_info=None
                                )
                                self.log_queue.put(end_marker)

                                # 等待处理完成
                                time.sleep(grace_period)
                        except Exception as e:
                            logging.getLogger(__name__).error(f"处理日志队列关闭时出错: {e}")

                    # 保存处理器列表的副本
                    handlers = list(self.log_listener.handlers) if hasattr(self.log_listener, 'handlers') else []

                    # 停止监听器
                    try:
                        self.log_listener.stop()
                    except Exception as e:
                        logging.getLogger(__name__).error(f"停止日志监听器时出错: {e}")

                    # 手动刷新和关闭所有处理器
                    for handler in handlers:
                        try:
                            if hasattr(handler, 'flush') and callable(handler.flush):
                                handler.flush()
                            if hasattr(handler, 'close') and callable(handler.close):
                                handler.close()
                        except Exception as e:
                            logging.getLogger(__name__).error(f"关闭日志处理器时出错: {e}")

                    self.log_listener = None

                except Exception as e:
                    logging.getLogger(__name__).error(f"关闭日志监听器时出错: {e}")
                    logging.getLogger(__name__).error(traceback.format_exc())

            # 安全关闭日志队列
            if self.log_queue is not None:
                try:
                    if hasattr(self.log_queue, 'close'):
                        self.log_queue.close()
                    if hasattr(self.log_queue, 'join_thread'):
                        self.log_queue.join_thread()
                    self.log_queue = None
                except Exception as e:
                    logging.getLogger(__name__).error(f"关闭日志队列时出错: {e}")


# 上下文变量支持
_request_id_var = contextvars.ContextVar('request_id', default=None)
_user_id_var = contextvars.ContextVar('user_id', default=None)

# 创建全局日志管理器实例
_logger_manager = LoggerManager()


# 基础接口（便于CLI程序快速调用）
def setup_logging(
        log_file: str = None,
        console_output: bool = True,
        level: Union[str, int] = "INFO",
        console_level: Union[str, int] = "INFO",
        file_level: Union[str, int] = "DEBUG",
        console_format: str = DEFAULT_CONSOLE_FMT,
        file_format: str = DEFAULT_FILE_FMT,
        rotate_maxBytes: int = 10 * 1024 * 1024,  # 10MB
        rotate_backupCount: int = 3,
        use_json_formatter: bool = False,
        show_shutdown_message: bool = True
):
    """
    基础日志系统设置接口
    
    Args:
        log_file: 日志文件路径
        console_output: 是否输出到控制台
        level: 根日志级别
        console_level: 控制台日志级别
        file_level: 文件日志级别
        console_format: 控制台日志格式
        file_format: 文件日志格式
        rotate_maxBytes: 日志文件最大大小
        rotate_backupCount: 日志文件备份数量
        use_json_formatter: 是否使用JSON格式化器
        show_shutdown_message: 是否显示关闭消息
    """
    # 处理日志级别
    if isinstance(level, str):
        level = getattr(logging, level.upper(), INFO)
    if isinstance(console_level, str):
        console_level = getattr(logging, console_level.upper(), INFO)
    if isinstance(file_level, str):
        file_level = getattr(logging, file_level.upper(), DEBUG)

    handlers = []

    # 创建控制台处理器
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)

        if use_json_formatter:
            console_formatter = JSONFormatter()
        else:
            console_formatter = logging.Formatter(console_format)

        console_handler.setFormatter(console_formatter)
        handlers.append(console_handler)

    # 创建文件处理器
    if log_file:
        try:
            # 确保日志文件目录存在
            log_file_path = Path(log_file)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)

            # 创建旋转文件处理器
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=rotate_maxBytes,
                backupCount=rotate_backupCount,
                encoding='utf-8'
            )
            file_handler.setLevel(file_level)

            if use_json_formatter:
                file_formatter = JSONFormatter()
            else:
                file_formatter = logging.Formatter(file_format)

            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)

            # if console_output:
            #     logging.getLogger(__name__).info(f"日志将被记录到文件: {log_file}")

        except Exception as e:
            logging.getLogger(__name__).error(f"创建日志文件失败: {e}")

    # 存储关闭消息配置
    _logger_manager._show_shutdown_message = show_shutdown_message

    return _logger_manager.setup(
        handlers=handlers,
        level=level,
        use_queue=True
    )


# 高级接口（用于开发网络服务、线程系统等核心服务）
def advanced_logging_setup(
        handlers: List[logging.Handler],
        level: Union[int, str] = DEBUG,
        root_formatter: str = None,
        use_queue: bool = True,
        **kwargs
):
    """
    高级日志系统设置接口
    
    Args:
        handlers: 自定义处理器列表
        level: 根日志级别
        root_formatter: 根格式化器
        use_queue: 是否使用队列处理
        **kwargs: 其他配置参数
    """
    return _logger_manager.setup(
        handlers=handlers,
        level=level,
        root_formatter=root_formatter,
        use_queue=use_queue,
        **kwargs
    )


def get_logger(name: str = "default"):
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称，默认为"default"
        
    Returns:
        配置好的日志记录器
    """
    return _logger_manager.get_logger(name)


def shutdown_logging(grace_period: float = 0.5, force: bool = False):
    """
    关闭日志系统，确保所有日志消息都被处理
    
    Args:
        grace_period: 优雅关闭等待时间
        force: 是否强制关闭
    """
    # 显示关闭消息（如果配置允许）
    if hasattr(_logger_manager, '_show_shutdown_message') and _logger_manager._show_shutdown_message:
        logging.getLogger(__name__).info("日志系统已关闭")

    _logger_manager.shutdown(grace_period=grace_period, force=force)


def reset_logging():
    """重置日志系统，允许重新初始化"""
    _logger_manager.reset()


# 异步日志支持
async def async_log(logger, level: str, message: str, *args, loop=None, extra: Dict[str, Any] = None, **kwargs):
    """
    异步日志记录函数，适用于异步环境
    
    Args:
        logger: 日志记录器实例
        level: 日志级别 ('debug', 'info', 'warning', 'error', 'critical')
        message: 日志消息
        *args: 消息格式化参数
        loop: 事件循环（可选）
        extra: 额外上下文信息，如 {'request_id': 'xxx', 'user_id': 'xxx'}
        **kwargs: 其他参数
    
    示例:
        await async_log(logger, "info", "用户请求处理完成", 
                       extra={'request_id': 'req-123', 'user_id': 'user-456'})
    """
    # 获取事件循环
    if loop is None:
        loop = asyncio.get_event_loop()

    # 构建上下文信息
    context_info = {
        'request_id': _request_id_var.get(),
        'user_id': _user_id_var.get()
    }

    # 合并用户提供的额外信息
    if extra:
        context_info.update(extra)

    def _log_sync():
        log_func = getattr(logger, level.lower())
        log_func(message, *args, extra=context_info)

    await loop.run_in_executor(None, _log_sync)


def get_async_logger(name: str = "async_default"):
    """
    获取适用于异步环境的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        配置好的异步日志记录器
    """
    return _logger_manager.get_logger(name)


def set_request_context(request_id: str, user_id: str = None):
    """
    设置请求上下文信息
    
    Args:
        request_id: 请求ID
        user_id: 用户ID
    """
    _request_id_var.set(request_id)
    if user_id:
        _user_id_var.set(user_id)


def clear_request_context():
    """清除请求上下文信息"""
    _request_id_var.set(None)
    _user_id_var.set(None)


class LoggingContext:
    """上下文管理器，用于自动设置和清除日志上下文"""

    def __init__(self, request_id: str = None, user_id: str = None):
        self.request_id = request_id
        self.user_id = user_id
        self._token1 = None
        self._token2 = None

    def __enter__(self):
        if self.request_id:
            self._token1 = _request_id_var.set(self.request_id)
        if self.user_id:
            self._token2 = _user_id_var.set(self.user_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token1:
            _request_id_var.reset(self._token1)
        if self._token2:
            _user_id_var.reset(self._token2)


# 便捷函数：创建常用处理器
def create_console_handler(level=INFO, format_str=DEFAULT_CONSOLE_FMT):
    """创建控制台处理器"""
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(format_str))
    return handler


def create_file_handler(filename, level=DEBUG, format_str=DEFAULT_FILE_FMT):
    """创建文件处理器"""
    # 确保目录存在
    Path(filename).parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(filename, encoding='utf-8')
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(format_str))
    return handler


def create_rotating_handler(filename, maxBytes=10 * 1024 * 1024, backupCount=3,
                            level=DEBUG, format_str=DEFAULT_FILE_FMT):
    """创建旋转文件处理器"""
    # 确保目录存在
    Path(filename).parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(filename, maxBytes=maxBytes, backupCount=backupCount, encoding='utf-8')
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(format_str))
    return handler


def create_json_handler(filename=None, level=INFO):
    """创建JSON格式处理器"""
    if filename:
        # 确保目录存在
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(filename, encoding='utf-8')
    else:
        handler = logging.StreamHandler()

    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    return handler


def create_smtp_handler(
        mailhost: str,
        fromaddr: str,
        toaddrs: List[str],
        subject: str,
        credentials: tuple = None,
        secure: tuple = None,
        level: int = ERROR,
        format_str: str = DEFAULT_FILE_FMT
) -> SMTPHandler:
    """
    创建SMTP邮件处理器
    
    Args:
        mailhost: SMTP服务器地址，如 'smtp.example.com:587'
        fromaddr: 发件人邮箱
        toaddrs: 收件人邮箱列表
        subject: 邮件主题
        credentials: 认证信息 (username, password)
        secure: 安全连接设置，如 () 或 ('username', 'password')
        level: 日志级别，默认只发送ERROR及以上
        format_str: 日志格式
    
    Returns:
        SMTPHandler实例
    
    示例:
        smtp_handler = create_smtp_handler(
            mailhost='smtp.gmail.com:587',
            fromaddr='sender@example.com',
            toaddrs=['admin@example.com'],
            subject='系统错误告警',
            credentials=('username', 'password'),
            secure=()
        )
    """
    handler = SMTPHandler(
        mailhost=mailhost,
        fromaddr=fromaddr,
        toaddrs=toaddrs,
        subject=subject,
        credentials=credentials,
        secure=secure
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(format_str))
    return handler


# 添加SUCCESS级别的便捷方法
def add_success_level():
    """为所有日志记录器添加SUCCESS级别"""

    def success(self, message, *args, **kwargs):
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, message, args, **kwargs)

    logging.Logger.success = success


# 自动添加SUCCESS级别
add_success_level()


def load_config_from_json(config_path: str) -> Dict[str, Any]:
    """
    从JSON文件加载日志配置
    
    Args:
        config_path: JSON配置文件路径
    
    Returns:
        配置参数字典
    
    示例配置 (config.json):
    {
        "log_file": "logs/app.log",
        "console_output": true,
        "level": "INFO",
        "console_level": "WARNING",
        "file_level": "DEBUG",
        "rotate_maxBytes": 10485760,
        "rotate_backupCount": 5,
        "use_json_formatter": false
    }
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"加载JSON配置文件失败: {e}")


def load_config_from_yaml(config_path: str) -> Dict[str, Any]:
    """
    从YAML文件加载日志配置
    
    Args:
        config_path: YAML配置文件路径
    
    Returns:
        配置参数字典
    
    示例配置 (config.yaml):
    log_file: logs/app.log
    console_output: true
    level: INFO
    console_level: WARNING
    file_level: DEBUG
    rotate_maxBytes: 10485760
    rotate_backupCount: 5
    use_json_formatter: false
    """
    if not YAML_AVAILABLE:
        raise ImportError("需要安装PyYAML: pip install PyYAML")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"加载YAML配置文件失败: {e}")


def setup_from_config(config: Dict[str, Any], config_type: str = "dict"):
    """
    从配置字典设置日志系统
    
    Args:
        config: 配置参数字典
        config_type: 配置类型，用于日志标识
    
    支持的配置项:
        log_file: 日志文件路径
        console_output: 是否输出到控制台
        level: 根日志级别
        console_level: 控制台日志级别
        file_level: 文件日志级别
        console_format: 控制台格式
        file_format: 文件格式
        rotate_maxBytes: 旋转文件最大大小
        rotate_backupCount: 备份文件数量
        use_json_formatter: 是否使用JSON格式
        show_shutdown_message: 是否显示关闭消息
    """
    logger = get_logger("config_loader")
    logger.info(f"从{config_type}配置加载日志设置")

    return setup_logging(**config)


def setup_from_json(config_path: str):
    """从JSON文件设置日志系统"""
    config = load_config_from_json(config_path)
    return setup_from_config(config, "JSON")


def setup_from_yaml(config_path: str):
    """从YAML文件设置日志系统"""
    config = load_config_from_yaml(config_path)
    return setup_from_config(config, "YAML")

# 示例用法和测试
# if __name__ == "__main__":
#     # 创建示例日志记录器用于测试
#     example_logger = logging.getLogger("example")
#     example_logger.setLevel(logging.INFO)
#
#     # 添加临时控制台处理器用于示例输出
#     console_handler = logging.StreamHandler()
#     console_handler.setFormatter(logging.Formatter('%(message)s'))
#     example_logger.addHandler(console_handler)
#
#     # 示例1：基础使用
#     example_logger.info("=== 基础使用示例 ===")
#     setup_logging(log_file="logs/example.log", console_output=True, level="INFO")
#
#     logger = get_logger("example")
#     logger.debug("这是一条调试日志")
#     logger.info("这是一条信息日志")
#     logger.warning("这是一条警告日志")
#     logger.error("这是一条错误日志")
#     logger.critical("这是一条严重错误日志")
#     logger.success("这是一条成功日志")
#
#     # 示例2：高级配置
#     example_logger.info("\n=== 高级配置示例 ===")
#     reset_logging()
#
#     handlers = [
#         create_console_handler(level=INFO),
#         create_rotating_handler("logs/advanced.log", maxBytes=1024*1024, backupCount=5),
#         create_json_handler("logs/structured.log")
#     ]
#
#     advanced_logging_setup(handlers=handlers, level=DEBUG)
#
#     advanced_logger = get_logger("advanced")
#     advanced_logger.info("高级配置日志测试")
#
#     # 示例3：多线程测试
#     example_logger.info("\n=== 多线程测试 ===")
#     def worker_function(worker_id):
#         worker_logger = get_logger(f"worker-{worker_id}")
#         worker_logger.info(f"工作线程 {worker_id} 开始工作")
#         time.sleep(0.1)
#         worker_logger.info(f"工作线程 {worker_id} 完成工作")
#
#     threads = []
#     for i in range(3):
#         t = threading.Thread(target=worker_function, args=(i,))
#         t.start()
#         threads.append(t)
#
#     for t in threads:
#         t.join()
#
#     logger.info("所有工作线程已完成")
#
#     # 示例4：异步日志测试
#     example_logger.info("\n=== 异步日志测试 ===")
#     async def async_example():
#         async_logger = get_async_logger("async_test")
#
#         # 使用上下文信息
#         set_request_context("req-123", "user-456")
#         await async_log(async_logger, "info", "异步日志消息")
#         await async_log(async_logger, "warning", "异步警告消息",
#                        extra={'endpoint': '/api/test'})
#
#         # 使用上下文管理器
#         with LoggingContext("req-789", "user-012"):
#             await async_log(async_logger, "info", "上下文管理器测试")
#
#     # 运行异步示例
#     asyncio.run(async_example())
#
#     # 示例5：配置文件加载
#     example_logger.info("\n=== 配置文件加载测试 ===")
#
#     # 创建示例配置文件
#     config_data = {
#         "log_file": "logs/config_test.log",
#         "console_output": True,
#         "level": "DEBUG",
#         "use_json_formatter": False
#     }
#
#     with open("logs/test_config.json", "w", encoding="utf-8") as f:
#         json.dump(config_data, f, ensure_ascii=False, indent=2)
#
#     setup_from_json("logs/test_config.json")
#     config_logger = get_logger("config_test")
#     config_logger.info("配置文件加载测试成功")
#
#     # 示例6：SMTP处理器测试（需要配置SMTP服务器）
#     example_logger.info("\n=== SMTP处理器示例 ===")
#     example_logger.info("# 示例代码，需要真实SMTP服务器配置")
#     example_logger.info("""
#     smtp_handler = create_smtp_handler(
#         mailhost='smtp.gmail.com:587',
#         fromaddr='sender@example.com',
#         toaddrs=['admin@example.com'],
#         subject='系统错误告警',
#         credentials=('username', 'password'),
#         secure=()
#     )
#     logger = get_logger('smtp_test')
#     logger.addHandler(smtp_handler)
#     logger.error("测试邮件告警")
#     """)
#
#     # 关闭日志系统
#     example_logger.info("\n=== 关闭日志系统 ===")
#     shutdown_logging()
#
#     # 清理临时处理器
#     example_logger.removeHandler(console_handler)
#     console_handler.close()
