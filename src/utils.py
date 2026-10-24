import sys
import time
import logging
from functools import wraps
from src.config import CONFIG


class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO

class ErrorFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.ERROR

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Хендлер для INFO
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(InfoFilter())
    formatter = logging.Formatter('[%(name)s] %(asctime)s %(levelname)-8s %(message)s')
    info_handler.setFormatter(formatter)

    # Хендлер для EXCEPTION / ERROR
    error_handler = logging.StreamHandler(sys.stdout)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(ErrorFilter())
    error_handler.setFormatter(logging.Formatter('%(asctime)s - ERROR - %(message)s'))

    # Добавляем хендлеры к логгеру
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    return logger


def timeit(func):
    """Декоратор для замера времени выполнения функции."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        print(f"Функция {func.__name__} выполнена за {elapsed_time:.4f} сек.")
        return result
    return wrapper


def valid_city(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        city = kwargs.get('city', '')
        if city not in CONFIG.ALLOWED_CITIES:
            return "city not available", 403
        res = function(*args, **kwargs)
        return res
    return wrapped