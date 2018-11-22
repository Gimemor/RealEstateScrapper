# -*- coding: utf-8 -*-
import scrapy
import logging
import traceback
import datetime
import re
from scrapy.loader import ItemLoader
from ..items import Ad
from ..order_types import OrderTypes, month_format
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from PIL import Image
import base64
import pytesseract
import io
import selenium.webdriver.support.expected_conditions as expected_condition
from ..logger import Logger


class AvitoRuSpider(scrapy.Spider):
    name = 'avito.ru'
    allowed_domains = ['avito.ru']
    start_urls = ['https://www.avito.ru/penza/kvartiry?view=list&user=1&s=104']
    item_selector = '//div[contains(@class, \'item_list\')]'
    date_regex = re.compile(r"размещено\s*(\d+\s*\w+|сегодня|вчера)", re.I)
    outdate_treshold = 30
    custom_settings = {
        'ROBOTSTXT_OBEY': True,
        'DOWNLOAD_DELAY': 21.1
    }

    def __init__(self):
        scrapy.Spider.__init__(self)
        self.driver_options = Options()
        self.driver_options.headless = True
        self.driver = webdriver.Chrome(executable_path='/usr/bin/chromedriver',
                                        options=self.driver_options)

    # noinspection PyMethodMayBeStatic
    def get_date_from_description(self, raw_data):
        date = AvitoRuSpider.date_regex.findall(raw_data)
        if not date:
            return datetime.datetime.today()
        first = date[0].lower()
        if first == 'сегодня':
            return datetime.datetime.today()
        if first == 'вчера':
            return datetime.date.today() - datetime.timedelta(1)
        result = month_format(first)
        return datetime.datetime.strptime(result, '%d %m %Y')

    def get_ad_data_from_category(self, item):
        return {
            'url': item.xpath('.//a[contains(@class, \'description-title-link\')]/@href').extract_first(),
            'scrapping_eligible': self.check_ad_scrapping_eligible(item)
        }

    # noinspection PyMethodMayBeStatic
    def check_ad_scrapping_eligible(self, item):
        raw_date = item.xpath('.//span[contains(@class, \'date\')]/text()').extract_first()
        date = self.get_date_from_description(raw_date)
        return (datetime.datetime.today() - date).days < AvitoRuSpider.outdate_treshold

    # noinspection PyMethodMayBeStatic
    def get_address(self, response):
        district = response.xpath(
            '//span[contains(@class, \'item-map-address\')]/span/text()').extract_first().strip()
        # address = response.xpath(
        #    '//span[contains(@class, \'item-map-address\')]/span/span/text()').extract_first().strip()
        return district  # + address

    # noinspection PyMethodMayBeStatic
    def get_description(self, response):
        descriptions = response.xpath('//div[contains(@class, \'item-description\')]/p/text()').extract()
        return '\r\n'.join(descriptions)

    def get_phone(self, response):
        try:
            self.driver.get(response.url)
            wait = WebDriverWait(self.driver, 30)
            button_xpath = "//div[contains(@class, \'item-phone-number\')]/a"
            wait.until(
                expected_condition.presence_of_element_located(
                    (By.XPATH, button_xpath)))
            button = self.driver.find_element_by_xpath(button_xpath)
            webdriver.ActionChains(self.driver).move_to_element(button).click(button).perform()
            img_xpath = '//div[contains(@class, \'item-phone-big-number\')]/img'
            wait.until(
                expected_condition.presence_of_element_located(
                    (By.XPATH, img_xpath)))
            img_element = self.driver.find_element_by_xpath(img_xpath)
            raw_img_string = img_element.get_attribute("src")
            raw_img_string = raw_img_string.split('base64,')[-1].strip()
            with io.BytesIO() as pic,\
                    io.BytesIO(base64.b64decode(raw_img_string)) as image_string:
                image = Image.open(image_string)
                image.save(pic, image.format, quality=100)
                return pytesseract.image_to_string(image)
        except Exception:
            logging.error(traceback.format_exc())
            Logger.log('Error',
                       'Error has occurred during the phone recognition:\n{}'.format(traceback.format_exc()))
            return None

    # noinspection PyMethodMayBeStatic
    def get_room_count(self, response):
        data = response.xpath('//li[contains(@class, \'item-params-list-item\')\
         and contains(./span/text(), \'Количество комнат\')]/text()').extract()
        if data is None:
            return None
        return ' '.join(data).strip()

    # noinspection PyMethodMayBeStatic
    def get_total_square(self, response):
        data = response.xpath('//li[contains(@class, \'item-params-list-item\')\
         and contains(./span/text(), \'Общая площадь\')]/text()').extract()
        if data is None:
            return None
        return ' '.join(data).strip()

    # noinspection PyMethodMayBeStatic
    def get_floor(self, response):
        data = response.xpath('//li[contains(@class, \'item-params-list-item\')\
         and contains(./span/text(), \'Этаж:\')]/text()').extract()
        if data is None:
            return None
        return ' '.join(data).strip()

    # noinspection PyMethodMayBeStatic
    def get_floor_count(self, response):
        data = response.xpath('//li[contains(@class, \'item-params-list-item\')\
         and contains(./span/text(), \'Этажей в доме:\')]/text()').extract()
        if data is None:
            return None
        return ' '.join(data).strip()

    # noinspection PyMethodMayBeStatic
    def get_contact_name(self, response):
        data = response.xpath('(//div[@class = \'seller-info-name\']/a/text())[1]')
        if data is None:
            Logger.log('Warning', 'Contact name not found')
            return None
        return data.extract_first().strip()

    # noinspection PyMethodMayBeStatic
    def get_image_list(self, response):
        data = response.xpath('//div[contains(@class, \'gallery-img-wrapper\')]//img/@src')
        if data is None:
            Logger.log('Warning', 'Image list not found')
            return None
        return data.extract()

    # noinspection PyMethodMayBeStatic
    def get_cost(self, response):
        data = response.xpath('(//span[contains(@class, \'js-item-price\')])[1]/@content').extract_first()
        if data is None:
            Logger.log('Warning', 'Price not found')
            return None
        return int(data)

    def get_category(self, response):
        data = [x.lower() for x in
                response.xpath("//a[contains(@class, 'js-breadcrumbs-link-interaction')]/text()").extract()]
        if not data:
            return self.get_room_count(repsonse)
        for i in data:
            if 'комнат' in i:
                return i
        return self.get_room_count(response)

    # noinspection PyMethodMayBeStatic
    def get_ad_date(self, response):
        raw_data = response.xpath("//div[contains(@class, 'title-info-metadata-item')]/text()").extract_first()
        return  self.get_date_from_description(raw_data)

    # noinspection PyMethodMayBeStatic
    def get_order_type(self, response):
        data = [x.lower() for x in response.xpath("//a[contains(@class, 'js-breadcrumbs-link-interaction')]/text()").extract()]
        if not data:
            Logger.log('Warning', 'Order type is not found')
            return 0
        if 'куплю' in data:
            return OrderTypes['BUY']
        if 'продам' in data:
            return OrderTypes['SALE']
        if 'сниму' in data:
            return OrderTypes['RENT']
        if 'сдам' in data:
            return OrderTypes['RENT_OUT']
        Logger.log('Warning', 'Order type is unknown')
        return 0

    def get_city(self, response):
        address = self.get_address(response)
        items = address.split(',')
        return items[0] if items else 'Пенза'

    def parse_ad(self, response):
        """
        @url https://www.avito.ru/penza/kvartiry/studiya_17_m_89_et._1631035614
        """
        ad_loader = ItemLoader(item=Ad(), response=response)
        ad_loader.add_xpath('title', '//span[contains(@class, \'title-info-title-text\')]/text()')
        ad_loader.add_value('source', 1)
        ad_loader.add_value('link', response.url)
        ad_loader.add_value('order_type', self.get_order_type(response))
        ad_loader.add_value('placed_at', self.get_ad_date(response))
        ad_loader.add_value('city', self.get_city(response))
        ad_loader.add_value('floor', self.get_floor(response))
        ad_loader.add_value('flat_area', self.get_total_square(response))
        # plot_size
        # ad_loader.add_value('plot_size', self.get_total_square(response))
        ad_loader.add_value('cost', self.get_cost(response))
        ad_loader.add_value('phone', self.get_phone(response))
        ad_loader.add_value('address', self.get_address(response))
        ad_loader.add_value('description', self.get_description(response))
        ad_loader.add_value('category', self.get_category(response))
        ad_loader.add_value('floor_count', self.get_floor_count(response))
        ad_loader.add_value('contact_name', self.get_contact_name(response))
        ad_loader.add_value('image_list', self.get_image_list(response))
        return ad_loader.load_item()

    def parse(self, response):
        last_reached = False
        for item in response.xpath(self.item_selector):
            ad = self.get_ad_data_from_category(item)
            if ad['scrapping_eligible']:
                yield response.follow(ad['url'], callback=self.parse_ad)

        if not last_reached:
            url = response.xpath('//a[contains(@class,\'js-pagination-next\')]/@href')\
                .extract_first()
            yield response.follow(url, callback=self.parse)

    def closed(self, reason):
        self.driver.close()
