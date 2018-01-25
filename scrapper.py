#!/usr/bin/env python
import os
import sys
from urllib import request
import argparse as argp

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from ebooklib import epub
from ebooklib.plugins import standard

from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import smtplib

from progress.bar import Bar

from PIL import Image

from bs4 import BeautifulSoup

parser = argp.ArgumentParser(description='Respekt digitizer')
group = parser.add_mutually_exclusive_group()
group.add_argument('-s', '--source_url', default='http://respekt.ihned.cz/aktualni-cislo/', type=str,
                   help='URL cisla, pokud neni zadany, bere se aktualni vydani')
group.add_argument('-c', '--history_filename', nargs="?", const="hist.log", default=None,
                   help='Koukne se do zadaneho souboru (default hist.log), jake bylo posledni zprocesovane cislo.'
                        ' Pokud nalezne novejsi, stahne ho, jinak exit.')
parser.add_argument('-a', '--archiv_url', help='URL archivu', type=str,
                    default="http://respekt.ihned.cz/tydenik/")
parser.add_argument('-u', '--login_name', type=str, help='Prihlasovaci jmeno')
parser.add_argument('-p', '--password', type=str, help='Prihlasovaci heslo')
parser.add_argument('-d', '--webdriver', choices=["firefox", "phantomjs", "chrome"], default="phantomjs",
                    help='Specify which selenium web driver should be used', type=str)
parser.add_argument('-g', '--png', help="Krome epub formatu vytvori take slozku s PNG obrazky clanku (pro pozdejsi spojeni do PDF)",
                    action='store_true')
parser.add_argument('-l', '--enlist', help="Vypise dostupna cisla v archivu a jejich URL", action='store_true')
parser.add_argument('-e', '--email_prijemce', type=str, help='Posle vysledny epub na uvedeny mail.')
parser.add_argument('-n', '--pocet_clanku', type=int, default=None, help='Kolik clanku se ma zpracovat')
parser.add_argument('-r', '--remove', action='store_true', help="Smaz vysledny epub (napriklad po odeslani na email)")
args = parser.parse_args()


class Issue:

    driver = None
    url_cisla = ""
    vydano = ""
    urls_clanku = []
    content = []
    nazev_ebook = ""

    def __init__(self):

        if args.webdriver == "firefox":
            self.driver = webdriver.Firefox()
        elif args.webdriver == "chrome":
            self.driver = webdriver.Chrome()
        elif args.webdriver == "phantomjs":
            self.driver = webdriver.PhantomJS()

        self.url_cisla = args.source_url

        if args.history_filename:
            so, new_issue = self.check_issue()
            if not so:
                print('Nebylo nalezeno novejsi cislo')
                sys.exit()
            elif so:
                print('Bylo nalezeno novejsi cislo {0}'.format(new_issue))
                self.url_cisla = new_issue

        if args.enlist:
            for cislo in self.get_cisla():
                print(cislo.text, "\t", cislo.get_attribute("href"))
            sys.exit()

        try:
            # pro cislo z archivu
            self.driver.get(self.url_cisla)
            vydani_text = self.driver.find_element_by_css_selector("#main > div.col12 > div.ow-enclose > b").text
            self.vydano = "_".join(vydani_text.split("/")[-2:]).split()[-1][:-1]
        except NoSuchElementException:
            # pro aktualni cislo
            self.driver.get(args.archiv_url)
            self.vydano = "_".join(args.archiv_url.split('/')[-2:])

        print("Zpracovavam cislo: ", self.vydano)

        self.get_cover()

        all_arts = self.driver.find_elements_by_xpath('//a[@class="issuedetail-categorized-item"]')
        self.urls_clanku = [art.get_attribute("href") for art in all_arts][:args.pocet_clanku]

    def check_issue(self):
        with open(args.history_filename, "r", encoding="utf8") as histfile:
            first_line_raw = histfile.readline()
        first_line_ws = first_line_raw.split('/')
        first_line = [int(i) for i in first_line_ws]
        first_issue_raw = self.get_cisla()[0]
        first_issue_s = first_issue_raw.text.split('/')
        first_issue = [int(i) for i in first_issue_s]
        href = first_issue_raw.get_attribute("href")

        if first_line == first_issue:
            return False, None
        elif first_line[1] < first_issue[1]:  # roky
            return True, href
        elif first_line[0] < first_issue[0]:  # cislo
            return True, href
        else:
            raise RuntimeError("Chyba v hledani posledniho cislo a porovnani ze souboru {0}".format(args.history_filename))

    def get_cisla(self):
        self.driver.get(args.archiv_url)
        cisla = self.driver.find_elements_by_xpath('//a[@class="catalog-itm-link"]')
        return cisla

    def parse_content(self):
        try:
            bar = Bar('Processing', max=len(self.urls_clanku), suffix='Progress: %(index)d/%(max)d | ETA: %(eta)ds')
            for url in self.urls_clanku:
                self.content.append(self.parse_art(url))
                bar.next()
            bar.finish()
        except ImportError:
            print('Pro sledování progresu (zbyvajici cas, pocet clanku...)'
                  '\nnainstalujte "progress" pomocí "pip install progress"')
            self.content = [self.parse_art(url) for url in self.urls_clanku]

    def prihlaseni_on_art(self):

        if args.login_name is None or args.password is None:
            raise RuntimeError("Musite zadat sve prihlasovaci udaje!")
        try:
            nav_toggle = self.driver.find_element_by_xpath("//button[contains(@class,'navigation-toggle')]")
            nav_toggle.click()
            jmeno = self.driver.find_element_by_xpath('//*[@id="frm-authBox-loginForm-username"]')
            jmeno.send_keys(args.login_name)
            heslo = self.driver.find_element_by_xpath('//*[@id="frm-authBox-loginForm-password"]')
            heslo.send_keys(args.password)
            heslo.submit()
        except:
            raise RuntimeError('Prihlaseni se nepodarilo!')

    def ensure_get(self, selector):
        return WebDriverWait(self.driver, 120).until(EC.presence_of_element_located(selector))

    def parse_art(self, url):
        self.driver.get(url)

        try:
            self.driver.find_element_by_xpath('//*[@id="frm-authBox-loginForm"]/input[1]')
            self.prihlaseni_on_art()
        except NoSuchElementException:
            # print( 'Uz jste prihlasen' )
            pass

        inside = self.driver.find_element_by_css_selector("#postcontent")
        try:
            author = self.driver.find_element_by_css_selector(".authorship-names").text
        except NoSuchElementException:
            try:
                survey = self.driver.find_elements_by_xpath("//span[@class='survey-respondent-name']")
                author = ", ".join([s.text for s in survey])
            except NoSuchElementException:
                class Object(object):
                    pass
                author = Object()
                author.text = ""
                author = ""
        try:
            title = self.driver.find_element_by_xpath("//h1[contains(@class,'-title')]").text
        except NoSuchElementException:
            title = self.driver.find_element_by_xpath("//h2[contains(@class,'-title')]").text
        try:
            subtitle = self.driver.find_element_by_css_selector(".post-subtitle").text
        except NoSuchElementException:
            class Object(object):
                pass
            subtitle = Object()
            subtitle.text = ""
            subtitle = ""

        soup = self.cisti_html(inside.get_attribute("innerHTML"))

        if args.png:
            pass
            # self.parse_as_png( title.text )

        try:
            os.mkdir("images")
        except FileExistsError:
            pass
        for img_el in soup.findAll("img"):
            img_url = img_el.get("srcset")
            if img_url:                
                image_sizes = {b: a for a, b in [elem.split() for elem in img_url.split(",")]}
                img_url = image_sizes.get("480w")
            else:
                img_url = img_el.get("src")            
            if img_url:
                r = request.urlopen(img_url)
                with open("images/" + img_url.split("/")[-1], "b+w") as pic:
                    pic.write(r.read())
                img_el["src"] = "images/" + img_url.split("/")[-1]

        vysl = {"title": title,
                "author": author,
                "subtitle": subtitle,
                "rawHtml": str(soup),
                }

        return vysl

    def parse_as_png(self, title):
        element = self.driver.find_element_by_css_selector("#detail")
        bottom = self.driver.find_element_by_css_selector("#detail > div.social-bottom-detail")
        topper = self.driver.find_element_by_css_selector("#heading > div.l > h1 > a")

        location = element.location
        size = element.size

        try:
            os.mkdir("outPNG")
        except FileExistsError:
            # print( "Zapisuji do existujici adresare s obrazky" )
            pass

        file_name = "outPNG/" + "_".join(title.split(" ")) + ".png"
        self.driver.save_screenshot(file_name)  # saves screenshot of entire page

        im = Image.open(file_name)  # uses PIL library to open image in memory

        left = topper.location['x']
        top = topper.location["y"]
        right = location['x'] + size['width']
        bottom = bottom.location["y"]

        im = im.crop((left, top, right, bottom))  # defines crop points
        im.save(file_name)  # saves new cropped image

    def cisti_html(self, raw_html):
        soup = BeautifulSoup(raw_html, "lxml")

        for i in soup.findAll("div"):
            try:
                if i["id"] == "text":
                    pass
                else:
                    i.extract()
            except KeyError:
                i.extract()

        return soup

    def make_epub(self):
        book = epub.EpubBook()    
        print(self.cover)    
        if self.cover:            
            book.set_cover("images/cover.jpg", open(self.cover, 'rb').read())
        book.set_identifier('respekt_{0}'.format(self.vydano))
        book.set_title("respekt_{0}".format(self.vydano))
        book.set_language("cs")
        style = """@namespace epub "http://www.idpf.org/2007/ops";
                   .detail-odstavec { margin: 10px 0; }
                   .detail-mezititulek { margin-top: 10px !important; font: bold 18px Arial; }
                """
        book.add_author("Respekt")

        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        stylesheet = epub.EpubItem(uid="style_stylesheet", file_name="style/stylesheet.css", media_type="text/css", content=style)
        book.add_item(nav_css)
        book.add_item(stylesheet)

        ftoc = []
        for ix, art in enumerate(self.content):
            c = epub.EpubHtml(title=art["title"], file_name="{0}.xhtml".format(ix),
                              media_type="application/xhtml+xml")
            c.content = r"""<h2>{title}</h2>
                            <strong>{subtitle}</strong><br />
                            <emph>{author}</emph><br />""".format(title=art["title"],
                                                                      subtitle=art["subtitle"],
                                                                      author=art["author"]) \
                        + art["rawHtml"]
            c.add_item(stylesheet)
            book.add_item(c)
            ftoc.append(c)

        book.toc = ftoc

        for img in os.listdir("images"):
            pathe = "images/{0}".format(img)
            im = epub.EpubItem(file_name=pathe, media_type="image/jpeg")
            with open(pathe, "b+r") as ifile:
                im.content = ifile.read()
            book.add_item(im)

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # basic spine
        book.spine = ['cover', 'nav'] + ftoc

        nazev = "respekt_{0}.epub".format(self.vydano)
        self.nazev_ebook = nazev
        epub.write_epub(nazev, book, {'plugins': [standard.SyntaxPlugin()]})

        if args.email_prijemce:
            self.send_book()

        csl = self.vydano.replace("_", "/")
        if args.history_filename:
            print('Zapisuji do {0} na prvni radku, ze cislo {1} bylo zpracovano.'.format(args.history_filename, csl))
            with open(args.history_filename, "w", encoding="utf8") as histf:
                histf.write(csl + "\n")

        # ## Cleaning
        os.system("rm -rf images ghostdriver.log")
        if args.remove:
            os.system("rm -rf {0}".format(nazev))

    def send_book(self):
        print('Posilam email...')

        msg = MIMEMultipart()
        with open(self.nazev_ebook, "rb") as ebook:
            book = MIMEApplication(ebook.read())
            book.add_header('Content-Disposition', 'attachment', filename=self.nazev_ebook)

        msg.attach(book)

        msg["Subject"] = "Nove vydani respektu: {}".format(self.vydano)

        username = "eraschecker"
        password = "smecpi123"
        fromaddr = "eraschecker@gmail.com"
        toaddr = args.email_prijemce

        # The actual mail send
        server = smtplib.SMTP('smtp.gmail.com:587')
        server.starttls()
        server.login(username, password)
        server.sendmail(fromaddr, toaddr, msg.as_string())
        server.quit()

    def get_cover(self):
        #self.driver.get("http://respekt.ihned.cz/archiv/")
        cover_image = self.driver.find_element_by_css_selector(".heroissue-cover")
        img_path = cover_image.get_attribute("data-src")
           
        path = "images/" + img_path.split("/")[-1]
        try:
            os.mkdir("images")
        except FileExistsError:
            pass
        if img_path:
            response = request.urlopen(img_path)
            with open(path, "b+w") as pic:
                pic.write(response.read())        
            self.cover = path


if __name__ == '__main__':

    if not ((args.login_name and args.password) or args.enlist):
        parser.print_help()
        sys.exit()

    issue = Issue()
    issue.parse_content()
    issue.make_epub()

    issue.driver.quit()
