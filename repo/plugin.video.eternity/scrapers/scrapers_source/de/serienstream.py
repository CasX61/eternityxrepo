# -*- coding: utf-8 -*-

#2023-03-20
# edit 2025-06-14
# edit 2025-11-21 - DNS Bypass Implementation
# edit 2026-01-30 - FIX Serienstream
# edit 2026-02-24 -by neires - eindeutige Serien Suche mit IMDB-Nummer

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
        self.search_link = '/suche?term='  # NEU: Echte Suche statt komplette Liste
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

    def generate_series_urls(self, title):
        """Generiert verschiedene mögliche Series-URLs aus dem Titel"""
        import re
        
        # Basis-URLs sammeln
        urls = []
        
        # 1. Normale Bereinigung (Standard) - OHNE Apostroph
        def clean_title(t):
            # Alles in Kleinbuchstaben
            url = t.lower()
            
            # Entferne Klammern und ihren Inhalt (wie (2019))
            url = re.sub(r'\([^)]*\)', '', url)
            
            # Ersetze ":" durch nichts
            url = url.replace(':', '')
            
            # Ersetze "&" durch "-"
            url = url.replace('&', '-')
            
            # Entferne Apostroph komplett für die Basis-Version
            url = url.replace("'", "").replace("’", "")
            
            # Entferne alle anderen nicht-alphanumerischen Zeichen (außer Leerzeichen)
            url = re.sub(r'[^a-z0-9\s-]', '', url)
            
            # Mehrfache Leerzeichen entfernen
            url = re.sub(r'\s+', ' ', url)
            
            # Leerzeichen durch Bindestriche ersetzen
            url = url.strip().replace(' ', '-')
            
            # Mehrfache Bindestriche entfernen
            url = re.sub(r'-+', '-', url)
            
            # Bindestriche am Anfang und Ende entfernen
            url = url.strip('-')
            
            return url
        
        # Standard-URL (Apostroph entfernt)
        standard_url = clean_title(title)
        urls.append(standard_url)
        
        # 2. Apostroph durch Bindestrich ersetzen (z.B. "da-vinci-s-demons")
        # Prüfe ob der originale Titel einen Apostroph enthält
        if "'" in title or "’" in title:
            # Für die Version mit Bindestrich müssen wir den Apostroph durch - ersetzen
            # Aber wir müssen sicherstellen, dass wir nicht doppelte Bindestriche bekommen
            
            # Erstelle eine Version wo Apostroph durch - ersetzt wird
            title_with_hyphen = title.replace("'", "-").replace("’", "-")
            hyphen_url = clean_title(title_with_hyphen)
            
            # Nur hinzufügen wenn unterschiedlich zur Standard-URL
            if hyphen_url != standard_url:
                urls.append(hyphen_url)
        
        # Entferne Duplikate
        unique_urls = []
        for url in urls:
            if url not in unique_urls and url:
                unique_urls.append(url)
        
        # Erstelle die finalen /serie/ URLs
        result = ['/serie/' + url for url in unique_urls]
        
        return result
		

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        if season == 0: 
            return self.sources
        try:
            import xbmc
            t = [cleantitle.get(i) for i in titles if i]
            
            xbmc.log('[Serienstream] ===== SCRAPER GESTARTET =====', xbmc.LOGINFO)
            xbmc.log('[Serienstream] Titel: %s' % str(titles), xbmc.LOGINFO)
            xbmc.log('[Serienstream] Staffel: %s, Episode: %s' % (season, episode), xbmc.LOGINFO)
            xbmc.log('[Serienstream] IMDb: %s' % imdb, xbmc.LOGINFO)

            # 1. Suche mit IMDb-Nummer (falls vorhanden)
            if imdb and imdb.startswith('tt'):
                xbmc.log('[Serienstream] Suche mit IMDb-Nummer: %s' % imdb, xbmc.LOGINFO)
                
                search_term = urllib.parse.quote(imdb)
                url = urljoin(self.base_link, self.search_link + search_term)
                
                if self.bypass_dns:
                    sHtmlContent = self.make_request(url)
                else:
                    oRequest = cRequestHandler(url)
                    sHtmlContent = oRequest.request()
                
                if sHtmlContent:
                    # Extrahiere den Serien-Link aus den Suchergebnissen
                    patterns = [
                        r'href="([^"]*?/serie/[^"]*?)"',
                        r'href=\'([^\']*?/serie/[^\']*?)\'',
                    ]
                    
                    all_serie_hrefs = []
                    for pattern in patterns:
                        matches = re.findall(pattern, sHtmlContent, re.IGNORECASE)
                        all_serie_hrefs.extend(matches)
                    
                    all_serie_hrefs = list(set(all_serie_hrefs))
                    
                    if all_serie_hrefs:
                        # Nimm den ersten gefundenen Link (sollte der richtige sein)
                        serie_url = all_serie_hrefs[0]
                        xbmc.log('[Serienstream] IMDb-Suche erfolgreich: %s' % serie_url, xbmc.LOGINFO)
                        
                        # Verarbeite den gefundenen Link
                        self.run2(serie_url, year, season=season, episode=episode, hostDict=hostDict, imdb=imdb)
                        
                        if len(self.sources) > 0:
                            xbmc.log('[Serienstream] Quellen gefunden via IMDb-Suche!', xbmc.LOGINFO)
                            return self.sources
                    else:
                        xbmc.log('[Serienstream] Keine Treffer bei IMDb-Suche', xbmc.LOGINFO)
                else:
                    xbmc.log('[Serienstream] Keine Antwort bei IMDb-Suche', xbmc.LOGINFO)

            # 2. Fallback: Direkte Links basierend auf Titeln (wie gehabt)
            xbmc.log('[Serienstream] Starte Titel-basierte Suche als Fallback', xbmc.LOGINFO)
            
            for title in titles:
                if not title:
                    continue
                    
                # Generiere mögliche URLs für diesen Titel
                possible_urls = self.generate_series_urls(title)
                
                xbmc.log('[Serienstream] Mögliche URLs für "%s": %s' % (title, str(possible_urls)), xbmc.LOGINFO)
                
                for direct_url in possible_urls:
                    xbmc.log('[Serienstream] Versuche direkten Link: %s' % direct_url, xbmc.LOGINFO)
                    
                    test_url = urljoin(self.base_link, direct_url)
                    
                    try:
                        if self.bypass_dns:
                            test_html = self.make_request(test_url)
                        else:
                            test_html = cRequestHandler(test_url).request()
                        
                        if test_html and len(test_html) > 1000 and '404 - Not Found' not in test_html:
                            xbmc.log('[Serienstream] Direkter Link funktioniert: %s' % direct_url, xbmc.LOGINFO)
                            self.run2(direct_url, year, season=season, episode=episode, hostDict=hostDict, imdb=imdb)
                            if len(self.sources) > 0:
                                xbmc.log('[Serienstream] Quellen gefunden bei direktem Link!', xbmc.LOGINFO)
                                return self.sources
                    except Exception as e:
                        xbmc.log('[Serienstream] Direkter Link fehlgeschlagen: %s' % str(e), xbmc.LOGINFO)

            # 3. Letzter Fallback: Normale Suche
            xbmc.log('[Serienstream] Starte normale Suche als letzten Fallback', xbmc.LOGINFO)
            
            all_potential_matches = []

            for title in titles:
                if not title:
                    continue

                xbmc.log('[Serienstream] Suche nach: %s' % title, xbmc.LOGINFO)
                
                search_term = urllib.parse.quote(title)
                url = urljoin(self.base_link, self.search_link + search_term)
                
                if self.bypass_dns:
                    sHtmlContent = self.make_request(url)
                    if not sHtmlContent:
                        continue
                else:
                    oRequest = cRequestHandler(url)
                    sHtmlContent = oRequest.request()

                # Links extrahieren
                patterns = [
                    r'href="([^"]*?/serie/[^"]*?)"',
                    r'href=\'([^\']*?/serie/[^\']*?)\'',
                ]
                
                all_serie_hrefs = []
                for pattern in patterns:
                    matches = re.findall(pattern, sHtmlContent, re.IGNORECASE)
                    all_serie_hrefs.extend(matches)
                
                all_serie_hrefs = list(set(all_serie_hrefs))

                # Teiltreffer sammeln
                for href in all_serie_hrefs:
                    series_title = href.split('/')[-1].replace('-', ' ')
                    cleaned_series_title = cleantitle.get(series_title)
                    
                    for clean_title in t:
                        try:
                            if clean_title in cleaned_series_title or cleaned_series_title in clean_title:
                                if href not in all_potential_matches:
                                    all_potential_matches.append(href)
                                    xbmc.log('[Serienstream] Teiltreffer: %s -> %s' % (href, series_title), xbmc.LOGINFO)
                                break
                        except:
                            pass

            # Teiltreffer verarbeiten
            if len(all_potential_matches) > 0:
                xbmc.log('[Serienstream] Verarbeite %d Teiltreffer' % len(all_potential_matches), xbmc.LOGINFO)
                
                for href in all_potential_matches:
                    xbmc.log('[Serienstream] Versuche: %s' % href, xbmc.LOGINFO)
                    self.run2(href, year, season=season, episode=episode, hostDict=hostDict, imdb=imdb)
                    if len(self.sources) > 0:
                        xbmc.log('[Serienstream] Erfolg bei: %s' % href, xbmc.LOGINFO)
                        break

        except Exception as e:
            xbmc.log('[Serienstream] Fehler: %s' % str(e), xbmc.LOGERROR)
            import traceback
            traceback.print_exc()
            
        xbmc.log('[Serienstream] ===== SCRAPER BEENDET mit %d Quellen =====' % len(self.sources), xbmc.LOGINFO)
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
            xbmc.log('[Serienstream] Parsing episode page', xbmc.LOGINFO)

            # IMDB Check - optional, mit Absicherung falls Element nicht existiert
            if imdb:
                a = dom_parser.parse_dom(sHtmlContent, 'a', attrs={'class': 'imdb-link'}, req='href')
                if a:
                    foundImdb = a[0].attrs.get("data-imdb", '')
                    xbmc.log('[Serienstream] Found IMDb: %s, Expected: %s' % (foundImdb, imdb), xbmc.LOGINFO)
                    if foundImdb and not foundImdb == imdb:
                        xbmc.log('[Serienstream] IMDb mismatch, skipping', xbmc.LOGINFO)
                        return

            xbmc.log('[Serienstream] Parsing hosters', xbmc.LOGINFO)
            # NEU: Hoster-Pattern für neue Website-Struktur
            # Attribute können auf verschiedenen Zeilen stehen, daher [\s\S]*? verwenden
            pattern = r'data-link-id="([^"]+)"[\s\S]*?data-play-url="([^"]+)"[\s\S]*?data-provider-name="([^"]+)"[\s\S]*?data-language-id="([^"]+)"'
            matches = re.findall(pattern, sHtmlContent)

            xbmc.log('[Serienstream] Found %d hosters' % len(matches), xbmc.LOGINFO)

            # Erst Deutsch sammeln, dann Englisch als Fallback
            r_german = []
            r_english = []
            r_subbed = []
            for link_id, play_url, provider_name, language_id in matches:
                if language_id == '1':  # Deutsch
                    r_german.append((play_url, provider_name, 'HD', ''))
                elif language_id == '2':  # Englisch
                    r_english.append((play_url, provider_name, 'HD', 'English/OV'))
                elif language_id == '3':  # Subbed
                    r_subbed.append((play_url, provider_name, 'HD', 'subbed'))

            # Deutsch bevorzugen, sonst Englisch, sonst Subbed als Fallback
            if r_german:
                r = r_german
                xbmc.log('[Serienstream] Using %d German streams' % len(r), xbmc.LOGINFO)
            elif r_english:
                r = r_english
                xbmc.log('[Serienstream] No German, using %d English streams as fallback' % len(r), xbmc.LOGINFO)
            elif r_subbed:
                r = r_subbed
                xbmc.log('[Serienstream] No German/English, using %d subbed streams as fallback' % len(r), xbmc.LOGINFO)
            else:
                r = []

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
