import asyncio
import requests
import sys
import json
from fake_useragent import UserAgent
from logger import Logger


class WebClient:
    def __init__(self, proxy_manager):
        self.proxy_manager = proxy_manager
        self.ua = UserAgent()

    def __get_internal(self, url, session, proxy):
        headers={
            'User-Agent':  session['UA']
        }
        return asyncio.get_running_loop().run_in_executor(None, lambda: session['SESSION'].get(url, headers=headers, proxies=proxy))

    def __post_internal(self, url, ad):
        def task():
            response = requests.post(url,
                          data=json.dumps({'order': ad}),
                          headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
            return response
        return asyncio.get_running_loop().run_in_executor(None, task)

    def get_session(self):
        session = {}
        session['UA'] = self.ua.random
        session['SESSION'] = requests.Session()
        return session

    def close_session(self, session):
        session['SESSION'].close()

    async def get(self, url, session):
        # get proxy
        proxy = self.proxy_manager.get_random_proxy()
        Logger.info('Using proxy {}'.format(proxy))
        # try to get a page
        response = await self.__get_internal(url, session, proxy)
        # if response is not valid
        if not response.ok:
            # switch proxy
            Logger.info('Response completed with {} error, switching proxy...'.format(response.status_code))
            check_proxy = self.proxy_manager.get_random_proxy([proxy])
            response = await  self.__get_internal(url, proxies=check_proxy)
            if not response.ok:
                Logger.error('Unable to get {}, status code {}'.format(url, response.status_code))
                return None
            Logger.info('Removing proxy {}'.format(proxy))
            self.proxy_manager.delete_proxy(proxy)
        return response.text

    async def post_ad(self, url, ad):
        ad['placed_at'] = str(ad['placed_at'])
        ad['link'] = ad['link'].replace('m.avito', 'www.avito')
        response = await self.__post_internal(url, ad)
        if not response.ok:
            Logger.info('Push {} failed, resulted with {}] {}'.format(url, response.status_code, response.text))
        else:
            Logger.info('{} has been pushed'.format(ad['link']))
