# -*- coding: utf-8 -*-

#2023-03-20
# edit 2025-06-14
# edit 2025-11-21 - DNS Bypass Implementation

import re
import datetime
import urllib.request
import urllib.error
import urllib.parse
import socket
import ssl
import json
from http.client import HTTPSConnection
from urllib.request import HTTPSHandler
from resources.lib.control import getSetting, urljoin, setSetting
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle, dom_parser
from resources.lib.utils import isBlockedHoster

try:
    from scrapers.modules.jsnprotect import cHelper
except:
    pass

SITE_IDENTIFIER = 'serienstream'
SITE_DOMAIN = 's.to'
SITE_NAME = SITE_IDENTIFIER.upper()

# Custom HTTPS Connection that connects to IP instead of hostname
class IPHTTPSConnection(HTTPSConnection):
    def __init__(self, ip_address, original_host, *args, **kwargs):
        self.ip_address = ip_address
        self.original_host = original_host
        super().__init__(ip_address, *args, **kwargs)

    def connect(self):
        # Connect to IP
        self.sock = socket.create_connection((self.ip_address, self.port), self.timeout)
        # Wrap with SSL using original hostname for SNI
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.original_host)

# Custom HTTPS Handler that uses IPHTTPSConnection
class DNSBypassHTTPSHandler(HTTPSHandler):
    def __init__(self, ip_address, original_host):
        self.ip_address = ip_address
        self.original_host = original_host
        super().__init__()

    def https_open(self, req):
        def connection_factory(host, *args, **kwargs):
            return IPHTTPSConnection(self.ip_address, self.original_host, *args, **kwargs)
        return self.do_open(connection_factory, req)

class source:
    def __init__(self):
        self.priority = 2
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain
        self.search_link = '/serien'
        self.bypass_dns = (getSetting('bypassDNSlock', 'false') == 'true')
        self.ip_cache = None
        self.sources = []

    def get_ip_via_doh(self, hostname):
        """Get IP address via DNS-over-HTTPS (Cloudflare 1.1.1.1)"""
        if self.ip_cache:
            return self.ip_cache

        try:
            doh_url = f"https://cloudflare-dns.com/dns-query?name={hostname}&type=A"
            req = urllib.request.Request(doh_url)
            req.add_header("Accept", "application/dns-json")
            response = urllib.request.urlopen(req, timeout=5)
            dns_data = json.loads(response.read().decode('utf-8'))

            if "Answer" in dns_data and len(dns_data["Answer"]) > 0:
                ip = dns_data["Answer"][0]["data"]
                self.ip_cache = ip
                return ip
        except Exception as e:
            import xbmc
            xbmc.log('[Serienstream] DoH failed: %s' % str(e), xbmc.LOGERROR)

        return None

    def create_opener(self):
        """Create urllib opener with optional DNS bypass"""
        if self.bypass_dns:
            hostname = self.domain
            ip = self.get_ip_via_doh(hostname)
            if ip:
                import xbmc
                xbmc.log('[Serienstream] DNS Bypass: %s -> %s' % (hostname, ip), xbmc.LOGINFO)
                handler = DNSBypassHTTPSHandler(ip, hostname)
                return urllib.request.build_opener(handler)

        # Default opener
        return urllib.request.build_opener()

    def make_request(self, url):
        """Make HTTP request with optional DNS bypass"""
        try:
            import xbmc
            xbmc.log('[Serienstream] Making request to: %s' % url, xbmc.LOGINFO)

            opener = self.create_opener()
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
            req.add_header('Accept-Language', 'de-DE,de;q=0.9,en;q=0.8')

            response = opener.open(req, timeout=30)
            data = response.read().decode('utf-8')

            xbmc.log('[Serienstream] Response received: %d bytes' % len(data), xbmc.LOGINFO)
            return data
        except Exception as e:
            import xbmc, traceback
            xbmc.log('[Serienstream] Request failed: %s' % str(e), xbmc.LOGERROR)
            xbmc.log('[Serienstream] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return None

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        aLinks = []
        if season == 0: return self.sources
        try:
            t = [cleantitle.get(i) for i in titles if i]
            url = urljoin(self.base_link, self.search_link)

            # Use DNS Bypass if enabled, otherwise use cRequestHandler
            if self.bypass_dns:
                sHtmlContent = self.make_request(url)
                if not sHtmlContent:
                    return self.sources
            else:
                oRequest = cRequestHandler(url)
                oRequest.cacheTime = 60*60*24*7
                sHtmlContent = oRequest.request()

            links = dom_parser.parse_dom(sHtmlContent, "div", attrs={"class": "genre"})
            links = dom_parser.parse_dom(links, "a")
            links = [(i.attrs["href"], i.content) for i in links]
            for i in links:
                for a in t:
                    try:
                        if any([a in cleantitle.get(i[1])]):
                            aLinks.append({'source': i[0]})
                            break
                    except:
                        pass
            if len(aLinks) == 0: return self.sources
            for i in aLinks:
                url = i['source']
                self.run2(url, year, season=season, episode=episode, hostDict=hostDict, imdb=imdb)
        except:
            return self.sources
        return self.sources

    def run2(self, url, year, season=0, episode=0, hostDict=None, imdb=None):
        try:
            url = url[:-1] if url.endswith('/') else url
            if "staffel" in url:
                url = re.findall("(.*?)staffel", url)[0]
            url += '/staffel-%d/episode-%d' % (int(season), int(episode))
            url = urljoin(self.base_link, url)

            # Use DNS Bypass if enabled, otherwise use cRequestHandler
            if self.bypass_dns:
                sHtmlContent = self.make_request(url)
                if not sHtmlContent:
                    return self.sources
            else:
                sHtmlContent = cRequestHandler(url).request()

            import xbmc
            xbmc.log('[Serienstream] Parsing episode page for IMDb', xbmc.LOGINFO)

            a = dom_parser.parse_dom(sHtmlContent, 'a', attrs={'class': 'imdb-link'}, req='href')
            foundImdb = a[0].attrs["data-imdb"]
            xbmc.log('[Serienstream] Found IMDb: %s, Expected: %s' % (foundImdb, imdb), xbmc.LOGINFO)
            if not foundImdb == imdb:
                xbmc.log('[Serienstream] IMDb mismatch, skipping', xbmc.LOGINFO)
                return

            xbmc.log('[Serienstream] Parsing hosters', xbmc.LOGINFO)
            lr = dom_parser.parse_dom(sHtmlContent, 'div', attrs={'class': 'hosterSiteVideo'})
            r = dom_parser.parse_dom(lr, 'li', attrs={'data-lang-key': re.compile('[1]')}) #- only german
            if r == []: r = dom_parser.parse_dom(lr, 'li', attrs={'data-lang-key': re.compile('[1|2|3]')})

            xbmc.log('[Serienstream] Found %d hosters' % len(r), xbmc.LOGINFO)

            r = [(i.attrs['data-link-target'], dom_parser.parse_dom(i, 'h4'),
                  'subbed' if i.attrs['data-lang-key'] == '3' else '' if i.attrs['data-lang-key'] == '1' else 'English/OV' if i.attrs['data-lang-key'] == '2' else '') for i
                 in r]
            r = [(i[0], re.sub('\s(.*)', '', i[1][0].content), 'HD' if 'hd' in i[1][0][1].lower() else 'SD', i[2]) for i in r]

            xbmc.log('[Serienstream] Getting login credentials', xbmc.LOGINFO)
            login, password = self._getLogin()
            xbmc.log('[Serienstream] Login credentials obtained', xbmc.LOGINFO)

            import requests
            requests.packages.urllib3.disable_warnings()
            s = requests.Session()

            # IMPORTANT: Use hardcoded IP from backup for login!
            # DoH IP (186.2.163.237) might be different server without login support
            ip = '186.2.175.5'  # Same IP as backup - login server!

            xbmc.log('[Serienstream] Using IP for login: %s' % ip, xbmc.LOGINFO)
            URL_LOGIN = 'https://%s/login' % ip
            payload = {'email': login, 'password': password}

            xbmc.log('[Serienstream] Logging in to s.to', xbmc.LOGINFO)
            res = requests.get(URL_LOGIN, verify=False)
            s.post(URL_LOGIN, data=payload, cookies=res.cookies, verify=False)
            xbmc.log('[Serienstream] Login completed', xbmc.LOGINFO)

            xbmc.log('[Serienstream] Processing %d hosters' % len(r), xbmc.LOGINFO)
            for url, host, quality, info in r:
                # Get final URL after redirect (requires login session!)
                # Same logic as backup - use session to follow redirects
                try:
                    xbmc.log('[Serienstream] Getting redirect URL: https://%s%s' % (ip, url), xbmc.LOGINFO)
                    sUrl = s.get('https://%s' % ip + url, verify=False).url
                    xbmc.log('[Serienstream] Got final URL: %s' % sUrl, xbmc.LOGINFO)
                except Exception as e:
                    xbmc.log('[Serienstream] Failed to get redirect: %s' % str(e), xbmc.LOGERROR)
                    sUrl = 'https://%s' % ip

                quality = 'HD' # temp
                isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl, isResolve=True)
                xbmc.log('[Serienstream] isBlocked=%s, hoster=%s, prioHoster=%s' % (isBlocked, hoster, prioHoster), xbmc.LOGINFO)
                if isBlocked:
                    xbmc.log('[Serienstream] ❌ Blocked hoster: %s' % hoster, xbmc.LOGINFO)
                    continue

                xbmc.log('[Serienstream] ✅ Adding source: %s (%s)' % (host, quality), xbmc.LOGINFO)
                self.sources.append(
                    {'source': host, 'quality': quality, 'language': 'de', 'url': url , 'info': info, 'direct': True, 'priority': self.priority, 'prioHoster': prioHoster})

            xbmc.log('[Serienstream] Total sources found: %d' % len(self.sources), xbmc.LOGINFO)
            return self.sources
        except Exception as e:
            import xbmc, traceback
            xbmc.log('[Serienstream] Exception in run2(): %s' % str(e), xbmc.LOGERROR)
            xbmc.log('[Serienstream] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return self.sources

    def resolve(self, url):
        return url

    @staticmethod
    def _getLogin():
        login = ''
        password = ''
        try:
            login = cHelper.UserName
            password = cHelper.PassWord
            setSetting('serienstream.user', login)
            setSetting('serienstream.pass', password)
        except:
            login = getSetting(SITE_IDENTIFIER + '.user')
            password = getSetting(SITE_IDENTIFIER + '.pass')
        finally:
            if login == '' or password == '':
                import xbmcgui, xbmcaddon
                AddonName = xbmcaddon.Addon().getAddonInfo('name')
                xbmcgui.Dialog().ok(AddonName,
                                    "In den Einstellungen die Kontodaten (Login) für %s eintragen / überprüfen\nBis dahin wird %s von der Suche ausgeschlossen. Es erfolgt kein erneuter Hinweis!" % (
                                    SITE_NAME, SITE_NAME))
                setSetting('provider.' + SITE_IDENTIFIER, 'false')
                exit()
            else:
                return login, password
