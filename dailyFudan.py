import time
from json import loads as json_loads
from os import path as os_path
from sys import exit as sys_exit
from sys import argv as sys_argv

from lxml import etree
from requests import session
from PIL import Image
import logging
import numpy
import easyocr
import io
import ssl

ssl._create_default_https_context = ssl._create_unverified_context



logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')


class Fudan:
    """
    建立与复旦服务器的会话，执行登录/登出操作
    """
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:76.0) Gecko/20100101 Firefox/76.0"

    # 初始化会话
    def __init__(self,
                 uid, psw,
                 url_login='https://uis.fudan.edu.cn/authserver/login', 
                 url_code='https://zlapp.fudan.edu.cn/backend/default/code',
                 url_auth_captcha='https://uis.fudan.edu.cn/authserver/captcha.html'):
        """
        初始化一个session，及登录信息
        :param uid: 学号
        :param psw: 密码
        :param url_login: 登录页，默认服务为空
        """
        self.session = session()
        self.session.headers['User-Agent'] = self.UA
        self.url_login = url_login
        self.url_code = url_code
        self.url_auth_captcha = url_auth_captcha

        self.uid = uid
        self.psw = psw

    def _page_init(self):
        """
        检查是否能打开登录页面
        :return: 登录页page source
        """
        logging.debug("Initiating——")
        page_login = self.session.get(self.url_login)

        logging.debug("return status code " + str(page_login.status_code))

        if page_login.status_code == 200:
            logging.debug("Initiated——")
            return page_login.text
        else:
            logging.debug("Fail to open Login Page, Check your Internet connection\n")
            self.close()

    def validate_code(self, url):
        img = self.session.get(url).content
        image = numpy.array(Image.open(io.BytesIO(img)))
        reader = easyocr.Reader(['en'])
        result = reader.readtext(image, detail = 0)
        return result[0]

    def login(self):
        """
        执行登录
        """
        page_login = self._page_init()

        logging.debug("parsing Login page——")
        html = etree.HTML(page_login, etree.HTMLParser())

        logging.debug("getting tokens")
        data = {
            "username": self.uid,
            "password": self.psw,
            "service" : "https://zlapp.fudan.edu.cn/site/ncov/fudanDaily"
        }

        # 获取登录页上的令牌
        data.update(
                zip(
                        html.xpath("/html/body/form/input/@name"),
                        html.xpath("/html/body/form/input/@value")
                )
        )

        headers = {
            "Host"      : "uis.fudan.edu.cn",
            "Origin"    : "https://uis.fudan.edu.cn",
            "Referer"   : self.url_login,
            "User-Agent": self.UA
        }

        logging.debug("Logging in——")
        # logging.debug(data)
        post = self.session.post(
                self.url_login,
                data=data,
                headers=headers,
                allow_redirects=False)

        logging.debug("return status code %d" % post.status_code)
        
        retry = 10
        while post.status_code != 302 and retry > 0:
            logging.debug("登录失败，请检查账号信息 " + str(post.status_code))
            if "验证码" in post.text:
                logging.debug("验证码失败")
                code = self.validate_code(self.url_auth_captcha)
                data.update({"captchaResponse": code})
                post = self.session.post(
                        self.url_login,
                        data=data,
                        headers=headers,
                        allow_redirects=False)


        if post.status_code == 302:
            logging.debug("登录成功")
        else:
            logging.debug("登录失败，请检查账号信息")
            if post.text.contains("请输入验证码"):
                code = self.validate_code(self.url_auth_captcha)
            self.close()

    def logout(self):
        """
        执行登出
        """
        exit_url = 'https://uis.fudan.edu.cn/authserver/logout?service=/authserver/login'
        expire = self.session.get(exit_url).headers.get('Set-Cookie')

        if '01-Jan-1970' in expire:
            logging.debug("登出完毕")
        else:
            logging.debug("登出异常")

    def close(self):
        """
        执行登出并关闭会话
        """
        self.logout()
        self.session.close()
        logging.debug("关闭会话")
        sys_exit()

class Zlapp(Fudan):
    last_info = ''

    def check(self):
        """
        检查
        """
        logging.debug("检测是否已提交")
        get_info = self.session.get(
                'https://zlapp.fudan.edu.cn/ncov/wap/fudan/get-info')
        last_info = get_info.json()

        logging.info("上一次提交日期为: %s " % last_info["d"]["info"]["date"])

        position = last_info["d"]["info"]['geo_api_info']
        position = json_loads(position)

        logging.info("上一次提交地址为: %s" % position['formattedAddress'])
        # logging.debug("上一次提交GPS为", position["position"])
        self.last_info = last_info["d"]["info"]
        self.old_info = last_info["d"]["oldInfo"]
        self.u_info = last_info["d"]["uinfo"]
        logging.debug(self.last_info)

        today = time.strftime("%Y%m%d", time.localtime())

        if last_info["d"]["info"]["date"] == today:
            logging.info("今日已提交")
            #self.close()
        else:
            logging.info("未提交")
            # self.last_info = last_info["d"]["info"]

    def checkin(self):
        """
        提交
        """
        headers = {
            "Host"      : "zlapp.fudan.edu.cn",
            "Referer"   : "https://zlapp.fudan.edu.cn/site/ncov/fudanDaily?from=history",
            "DNT"       : "1",
            "TE"        : "Trailers",
            "User-Agent": self.UA
        }

        logging.debug("提交中")

        save_msg = "验证码错误"
        while "验证码错误" in save_msg:
            logging.info("准备识别验证码")
            code = self.validate_code(self.url_code)
            logging.info("识别验证码成功，验证码为: %s", code)

            # geo_api_info = json_loads(self.last_info["geo_api_info"])
            # province = geo_api_info["addressComponent"].get("province", "")
            # city = geo_api_info["addressComponent"].get("city", "") or province
            # district = geo_api_info["addressComponent"].get("district", "")
            self.last_info.update(
                    {
                        "tw"      : "13",
                        "province": self.old_info["province"],
                        "city"    : self.old_info["city"],
                        "area"    : self.old_info["area"],
                        "sfzx"    : self.old_info["sfzx"],
                        "ismoved" : 0,
                        "realname": self.u_info["realname"],
                        "number"  : self.u_info["role"]["number"],
                        "now_time": int(round(time.time() * 1000)),
                        "code": code
                    }
            )
            logging.info(self.last_info)

            save = self.session.post(
                    'https://zlapp.fudan.edu.cn/ncov/wap/fudan/save',
                    data=self.last_info,
                    headers=headers,
                    allow_redirects=False)

            save_msg = json_loads(save.text)["m"]
            logging.info(save_msg)
    


def get_account():
    """
    获取账号信息
    """
    uid, psw = sys_argv[1].strip().split(' ')
    return uid, psw

if __name__ == '__main__':
    uid, psw = get_account()
    # logging.debug("ACCOUNT：" + uid + psw)
    zlapp_login = 'https://uis.fudan.edu.cn/authserver/login?' \
                  'service=https://zlapp.fudan.edu.cn/site/ncov/fudanDaily'
    daily_fudan = Zlapp(uid, psw, url_login=zlapp_login)
    daily_fudan.login()

    daily_fudan.check()
    daily_fudan.checkin()
    # 再检查一遍
    daily_fudan.check()

    daily_fudan.close()
