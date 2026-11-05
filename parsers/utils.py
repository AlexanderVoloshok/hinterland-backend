import time
import platform
import subprocess
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.chrome.service import Service


def get_driver():
    if platform.system() == 'Linux':
        options = Options()
        options.headless = True
        driver = webdriver.Firefox(executable_path=GeckoDriverManager().install())	
    elif platform.system() == 'Windows':
        service = Service(executable_path=ChromeDriverManager().install(), log_output=subprocess.DEVNULL)
        options = webdriver.ChromeOptions()
        #options.add_argument('--headless')
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_argument("--log-level=3")
        try:
            driver = webdriver.Chrome(service=service, options=options)
        except OSError:
            print('driver install failed. Starting a preinstalled one')
            service = Service(executable_path="C:/Python27/ArcGIS10.3/chromedriver.exe", log_output=subprocess.DEVNULL)
            driver = webdriver.Chrome(service=service, options=options)

    return driver


def retry(times: int, exceptions: tuple, timeout: int = 0):
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in ``exceptions`` are thrown
    :param times: The number of times to repeat the wrapped function/method
    :type times: Int
    :param Exceptions: Lists of exceptions that trigger a retry attempt
    :type Exceptions: Tuple of Exceptions
    """
    def decorator(func):
        def newfn(*args, **kwargs):
            attempt = 0
            while attempt < times:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    attempt += 1
                    time.sleep(timeout)
            return func(*args, **kwargs)
        return newfn
    return decorator


def skip(exceptions: tuple, expects=None):
    """
    Skip Decorator
    Skips the wrapped function/method if the exceptions listed
    in ``exceptions`` are thrown
    :param Exceptions: Lists of exceptions that trigger a retry attempt
    :type Exceptions: Tuple of Exceptions
    """
    def decorator(func):
        def newfn(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                print(f"executing function {func.__name__!r} failed due to {e}")
                return expects
        return newfn
    return decorator