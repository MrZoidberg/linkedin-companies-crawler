# -*- coding: utf-8 -*-
"""
Simple Linkedin crawler to collect companies's  profile data.

@author: MrZoidberg

Inspired by @idwaker's work: https://github.com/idwaker/linkedin

To use this you need linkedin account, all search is done through your account

Requirements:
    python-selenium
    python-click
    python-keyring

Tested on Python 3 not sure how Python 2 behaves
"""

import sys
import csv
import time
import click
import getpass
import keyring
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (WebDriverException,
                                        NoSuchElementException)
from selenium.webdriver.chrome.options import Options


LINKEDIN_URL = 'https://www.linkedin.com'
GOOGLE_URL = 'https://www.google.com'

class UnknownUserException(Exception):
    pass


class UnknownBrowserException(Exception):
    pass


class WebBus:
    """
    context manager to handle webdriver part
    """

    def __init__(self, browser):
        self.browser = browser
        self.driver = None

    def __enter__(self):
        # XXX: This is not so elegant
        # should be written in better way
        if self.browser.lower() == 'firefox':
            self.driver = webdriver.Firefox()
        elif self.browser.lower() == 'chrome':
            chrome_options = Options()
            chrome_options.add_argument("--lang=es")
            self.driver = webdriver.Chrome('./chromedriver', chrome_options=chrome_options)
        elif self.browser.lower() == 'phantomjs':
            self.driver = webdriver.PhantomJS()
        else:
            raise UnknownBrowserException("Unknown Browser")

        return self

    def __exit__(self, _type, value, traceback):
        if _type is OSError or _type is WebDriverException:
            click.echo("Please make sure you have this browser")
            return False
        if _type is UnknownBrowserException:
            click.echo("Please use either Firefox, PhantomJS or Chrome")
            return False

        self.driver.close()


def get_password(username):
    """
    get password from stored keychain service
    """
    password = keyring.get_password('linkedinpy', username)
    if not password:
        raise UnknownUserException("""You need to store password for this user
                                        first.""")

    return password


def login_into_linkedin(driver, username):
    """
    Just login to linkedin if it is not already loggedin
    """
    userfield = driver.find_element_by_id('login-email')
    passfield = driver.find_element_by_id('login-password')

    submit_form = driver.find_element_by_class_name('login-form')

    password = get_password(username)

    # If we have login page we get these fields
    # I know it's a hack but it works
    if userfield and passfield:
        userfield.send_keys(username)
        passfield.send_keys(password)
        submit_form.submit()
        click.echo("Logging in")


def collect_names(filepath):
    """
    collect names from the file given
    """
    names = []
    with open(filepath, 'r') as _file:
        names = [line.strip() for line in _file.readlines()]
    return names


@click.group()
def cli():
    """
    First store password

    $ python linkedin store username@example.com
    Password: **

    Then crawl linkedin for users

    $ python linkedin crawl username@example.com with_names output.csv --browser=firefox
    """
    pass


@click.command()
@click.option('--browser', default='phantomjs', help='Browser to run with')
@click.argument('username')
@click.argument('infile')
@click.argument('outfile')
def crawl(browser, username, infile, outfile):
    """
    Run this crawler with specified username
    """

    # first check and read the input file
    all_names = collect_names(infile)

    fieldnames = ['search-text', 'company-name', 'company-industries', 'company-size', 'description',
                  'company-page-url', 'company-type']
    # then check we can write the output file
    # we don't want to complete process and show error about not
    # able to write outputs
    with open(outfile, 'w') as csvfile:
        # just write headers now
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

    # now open the browser
    with WebBus(browser) as bus:
        bus.driver.get(LINKEDIN_URL)

        login_into_linkedin(bus.driver, username)

        for name in all_names:
            click.echo("Searching for " + name)

            bus.driver.get(GOOGLE_URL)
            try:
                search_input = bus.driver.find_element_by_id('lst-ib')
            except NoSuchElementException:
                continue
            search_input.send_keys('{0} LinkedIn'.format(name))
            search_input.send_keys(Keys.RETURN)

            WebDriverWait(bus.driver, 10).until(EC.presence_of_element_located((By.ID, "resultStats")))
            sleep(0.1)

            profiles = []

            # collect all the profile links
            results = None
            try:
                results = bus.driver.find_element_by_xpath('.//div[@id="ires"]')
            except NoSuchElementException:
                click.echo("No google results found")
                data = [{
                    'search-text' : name,
                    'company-name': 'not found',
                    'company-industries': '',
                    'company-size': '',
                    'description': '',
                    'company-page-url': '',
                    'company-type': '',
                }]
                with open(outfile, 'a+') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writerows(data)
                continue

            links = results.find_elements_by_xpath('.//a')
            # get all the links before going through each page
            resultLinks = []
            for link in links:
                href = link.get_attribute('href')
                if href.find('www.linkedin.com') != -1 and href.find('translate.google.com') == -1:
                    resultLinks.append(href)
            i = 0
            for link in resultLinks:

                i += 1
                if i == 5:
                    break

                # XXX: This whole section should be separated from this method
                # XXX: move try-except to context managers
                click.echo(link)
                bus.driver.get(link)
                if bus.driver.current_url.find('company-beta') != -1:
                    click.echo("Beta page")

                    overview = None
                    overview_xpath = '//div[@class="top-card-data"]'
                    try:
                        overview = bus.driver.find_element_by_xpath(overview_xpath)
                    except NoSuchElementException:
                        click.echo("No overview section")

                    if overview is not None:
                        company_name = None
                        company_name_xpath = './/h1[contains(@class,"company-main-info-company-name")]'
                        try:
                            company_name = overview.find_element_by_xpath(company_name_xpath)
                        except NoSuchElementException:
                            # we store empty fullname : notsure for this
                            company_name = ''
                        else:
                            company_name = company_name.text.strip()

                        company_industries = None
                        try:
                            company_industries = overview.find_element_by_class_name('company-industries')
                        except NoSuchElementException:
                            company_industries = ''
                        else:
                            company_industries = company_industries.text.strip()

                        company_size = None
                        try:
                            company_size = overview.find_element_by_class_name('company-size')
                        except NoSuchElementException:
                            company_size = ''
                        else:
                            company_size = company_size.text.strip()

                    details_button = None
                    try:
                        details_button = bus.driver.find_element_by_xpath('.//*[contains(@class,"about-company-module")]/div/div/button')
                    except NoSuchElementException:
                        click.echo("No details button")
                    else:
                        details_button.click()

                    csummary = None
                    csummary_xpath = './/div[contains(@class,"company-meta-text")]'
                    try:
                        csummary = bus.driver.find_element_by_xpath(csummary_xpath)
                    except NoSuchElementException:
                        click.echo("No summary section")

                    if csummary is not None:
                        description = None
                        try:
                            description = csummary.find_element_by_xpath('.//div[contains(@class, "about-us-organization-description")]/p')
                        except NoSuchElementException:
                            description = ''
                        else:
                            description = description.text.strip()

                        company_page_url = None
                        try:
                            company_page_url = csummary.find_element_by_xpath('.//*[contains(@class,"company-page-url")]/a')
                        except NoSuchElementException:
                            company_page_url = ''
                        else:
                            company_page_url = company_page_url.get_attribute('href')

                        company_type = None
                        try:
                            company_type = csummary.find_element_by_xpath('.//*[contains(@class,"company-type")]')
                        except NoSuchElementException:
                            company_type = ''
                        else:
                            company_type = company_type.text.strip()
                else:
                    click.echo("Old page")

                    overview = None
                    overview_xpath = '//div[@class="header"]'
                    try:
                        overview = bus.driver.find_element_by_xpath(overview_xpath)
                    except NoSuchElementException:
                        click.echo("No overview section")

                    if overview is not None:
                        # every xpath below here are relative
                        company_name = None
                        company_name_xpath = './/h1[@class="name"]'
                        try:
                            company_name = overview.find_element_by_xpath(company_name_xpath)
                        except NoSuchElementException:
                            # we store empty fullname : notsure for this
                            company_name = ''
                        else:
                            company_name = company_name.text.strip()

                        company_industries = None
                        try:
                            company_industries = overview.find_element_by_class_name('industry')
                        except NoSuchElementException:
                            company_industries = ''
                        else:
                            company_industries = company_industries.text.strip()

                        company_size = None
                        try:
                            company_size = overview.find_element_by_class_name('company-size')
                        except NoSuchElementException:
                            company_size = ''
                        else:
                            company_size = company_size.text.strip()

                    csummary = None
                    csummary_xpath = './/div[contains(@class,"basic-info")]'
                    try:
                        csummary = bus.driver.find_element_by_xpath(csummary_xpath)
                    except NoSuchElementException:
                        click.echo("No summary section")

                    if csummary is not None:
                        description = None
                        try:
                            description = csummary.find_element_by_class_name('basic-info-description')
                        except NoSuchElementException:
                            description = ''
                        else:
                            description = description.text.strip()

                        company_page_url = None
                        try:
                            company_page_url = csummary.find_element_by_class_name('website')
                        except NoSuchElementException:
                            company_page_url = ''
                        else:
                            company_page_url = company_page_url.text.strip()

                        company_type = None
                        try:
                            company_type = csummary.find_element_by_xpath('.//li[@class="type"]/p')
                        except NoSuchElementException:
                            company_type = ''
                        else:
                            company_type = company_type.text.strip()

                data = {
                    'search-text' : name,
                    'company-name': company_name,
                    'company-industries': company_industries,
                    'company-size': company_size,
                    'description': description,
                    'company-page-url': company_page_url,
                    'company-type': company_type,
                }
                profiles.append(data)
                break

            with open(outfile, 'a+') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerows(profiles)

            click.echo("Obtained ..." + name)


@click.command()
@click.argument('username')
def store(username):
    """
    Store given password for this username to keystore
    """
    passwd = getpass.getpass()
    keyring.set_password('linkedinpy', username, passwd)
    click.echo("Password updated successfully")


cli.add_command(crawl)
cli.add_command(store)


if __name__ == '__main__':
    cli()
