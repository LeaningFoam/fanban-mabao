"""日志模块:控制台 + 滚动文件,两级输出。"""
import logging
import os
from logging.handlers import RotatingFileHandler

from . import DATA_DIR

_LOGGER = None


def setup_logger(name="fanban_mabao", log_dir=None):
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    if log_dir is None:
        log_dir = os.path.join(DATA_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "fanban_mabao.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    _LOGGER = logger
    return logger


def get_logger():
    if _LOGGER is None:
        return setup_logger()
    return _LOGGER
