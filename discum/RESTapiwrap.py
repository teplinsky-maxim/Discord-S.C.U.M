import json
import inspect
import time
import requests

from .logger import LogLevel, Logger

# functions for REST requests in Wrapper class
from .utils.captcha import solveCaptchaWithLib
from .utils.exceptions import CaptchaException


class Wrapper:
    # returns formatted log string and color for REST requests
    @staticmethod
    def logFormatter(function, data, part):
        # [+] (<class->function) Method -> url
        if part == "url":
            text = "{} -> {}".format(data[0].title(), data[1])
            color = LogLevel.SEND
        # [+] (<class->function) body
        elif part == "body":
            try:
                text = json.dumps(data)
            except:
                text = str(data)
            color = LogLevel.SEND
        # [+] (<class->function) Response <- response.text
        elif part == "response":
            text = "Response <- {}".format(data.encode('utf-8'))
            color = LogLevel.RECEIVE
        formatted = " [+] {} {}".format(function, text)
        return formatted, color

    # decompression for brotli
    @staticmethod
    def brdecompress(payload, log):
        try:
            import brotli
            data = brotli.decompress(payload)
            return data
        except:
            return payload

    # header modifications, like endpoints that don't need auth, superproperties, etc; also for updating headers like xfingerprint
    @staticmethod
    def editedReqSession(reqsession, headerModifications):
        edited = requests.Session()
        edited.headers.update(reqsession.headers.copy())
        edited.proxies.update(reqsession.proxies.copy())
        edited.cookies.update(reqsession.cookies.copy())
        if headerModifications not in ({}, None):
            if "update" in headerModifications:
                edited.headers.update(headerModifications["update"])
            if "remove" in headerModifications:
                for header in headerModifications["remove"]:
                    if header in edited.headers:
                        del edited.headers[header]
        return edited

    # only for "Connection reset by peer" errors. Influenced by praw's retry code
    @staticmethod
    def retryLogic(reqMethod, url, data, log):
        remaining_attempts = 3
        while True:
            try:
                return reqMethod(url=url, **data)
            except requests.exceptions.ConnectionError:
                if log:
                    Logger.log("Connection reset by peer. Retrying...", None, log)
                    time.sleep(0.3)
                remaining_attempts -= 1
                if remaining_attempts == 0:
                    break
            except Exception:
                break
        return None

    @staticmethod
    def sendRequestBypassingCaptcha(reqsession, method, url, body=None, headerModifications=None, timeout=None, log=None):
        try:
            answer = Wrapper.sendRequest(reqsession, method, url, body, headerModifications, timeout, log, checkForCaptcha=True)
            return answer
        except CaptchaException as ex:
            sitekey = str(ex)
            captcha = solveCaptchaWithLib(sitekey, url)
            body['captcha_key'] = captcha
            answer = Wrapper.sendRequest(reqsession, method, url, body, headerModifications, timeout, log, checkForCaptcha=True)
            return answer

    # headerModifications = {"update":{}, "remove":[]}
    @staticmethod
    def sendRequest(reqsession, method, url, body=None, headerModifications=None, timeout=None, log=None, checkForCaptcha=False):
        # https://stackoverflow.com/a/6794329/14776493 + ty dolfies
        if headerModifications is None:
            headerModifications = {}
        if log is None:
            log = {"console": True, "file": False}
        # rest of stuff
        if hasattr(reqsession, method):  # just checks if post, get, whatever is a valid requests method
            # 1. find function
            stack = inspect.stack()
            try:
                function_name = "({}->{})".format(str(stack[1][0].f_locals['self']).split(' ')[0], stack[1][3])
            except KeyError:
                function_name = "({}->{})".format(str(stack[2][0].f_locals['self']).split(' ')[0], stack[2][3])
            # 2. edit request session if needed
            if body is None:
                if headerModifications.get('remove', None) is None:
                    headerModifications['remove'] = ['Content-Type']
                elif 'Content-Type' not in headerModifications['remove']:
                    headerModifications['remove'].append('Content-Type')

            s = Wrapper.editedReqSession(reqsession, headerModifications)
            # 3. log url
            text, color = Wrapper.logFormatter(function_name, [method, url], part="url")
            Logger.log(text, color, log)
            # 4. format body and log
            data = {}  # now onto the body (if exists)
            if body is not None:
                if isinstance(body, dict):
                    data = {'data': json.dumps(body)}
                else:
                    data = {'data': body}
                if log:
                    text, color = Wrapper.logFormatter(function_name, body, part="body")
                    Logger.log(text, color, log)
            # 5. put timeout in data if needed (when we don't want to wait for a response from discord)
            if timeout is not None:
                data['timeout'] = timeout
            # 6. the request
            response = Wrapper.retryLogic(getattr(s, method), url, data, log)
            # 7. brotli decompression of response
            if response and response.headers.get('Content-Encoding') == "br":  # decompression; gzip/deflate is automatically handled by requests module
                response._content = Wrapper.brdecompress(response.content, log)
            # 8. log response
            if response is not None:
                text, color = Wrapper.logFormatter(function_name, response.text, part="response")
                Logger.log(text, color, log)
                # 9. update cookies
                reqsession.cookies.update(response.cookies)
                if checkForCaptcha:
                    decodedAnswer = response.json()
                    if all(item in decodedAnswer for item in ('captcha_key', 'captcha_sitekey', 'captcha_service')):
                        raise CaptchaException(decodedAnswer['captcha_sitekey'])
            # 10. return response object with decompressed content
            return response
        else:
            Logger.log('Invalid request method.', None, log)
