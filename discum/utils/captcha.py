import os

from python_rucaptcha.HCaptcha import HCaptcha

URL = 'http://rucaptcha.com/in.php'
KEY = os.getenv('RUCAPTCHA_KEY')


def solveCaptchaWithLib(captchaSitekey, pageUrl):
    client = HCaptcha(rucaptcha_key=KEY)
    result = client.captcha_handler(site_key=captchaSitekey, page_url=pageUrl)
    return result['captchaSolve']
