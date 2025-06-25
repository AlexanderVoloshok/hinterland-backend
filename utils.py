import logging
from functools import wraps
from config import Config


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
    info_handler = logging.FileHandler('action.log', mode='a')
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(InfoFilter())
    formatter = logging.Formatter('[%(name)s] %(asctime)s %(levelname)-8s %(message)s')
    info_handler.setFormatter(formatter)

    # Хендлер для EXCEPTION / ERROR
    error_handler = logging.FileHandler('error.log', mode='a')
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(ErrorFilter())
    error_handler.setFormatter(logging.Formatter('%(asctime)s - ERROR - %(message)s'))

    # Добавляем хендлеры к логгеру
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    return logger


def valid_city(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        city = kwargs.get('city', '')
        if city not in Config.ALLOWED_CITIES:
            return "city not available", 403
        res = function(*args, **kwargs)
        return res
    return wrapped