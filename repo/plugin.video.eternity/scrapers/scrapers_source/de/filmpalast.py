# -*- coding: utf-8 -*-

# 2025-10-12
# Working urllib version + DNS Bypass

from resources.lib.utils import isBlockedHoster
import re
from resources.lib.control import getSetting
from scrapers.modules import cleantitle
import urllib.request
import urllib.error
import urllib.parse
import socket
import ssl
import json
from http.client import HTTPSConnection
from urllib.request import HTTPSHandler

SITE_IDENTIFIER = 'filmpalast'
SITE_DOMAIN = 'filmpalast.to'
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
		self.priority = 1
		self.language = ['de']
		self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
		self.base_link = 'https://' + self.domain
		self.search_link = '/search/title/%s'
		self.bypass_dns = (getSetting('bypassDNSlock', 'false') == 'true')
		self.ip_cache = None

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
			xbmc.log('[Filmpalast] DoH failed: %s' % str(e), xbmc.LOGERROR)
		
		return None

	def create_opener(self):
		"""Create urllib opener with optional DNS bypass"""
		if self.bypass_dns:
			hostname = self.domain
			ip = self.get_ip_via_doh(hostname)
			if ip:
				import xbmc
				xbmc.log('[Filmpalast] DNS Bypass: %s -> %s' % (hostname, ip), xbmc.LOGINFO)
				handler = DNSBypassHTTPSHandler(ip, hostname)
				return urllib.request.build_opener(handler)
		
		# Default opener
		return urllib.request.build_opener()

	def make_request(self, url, userAgent, referer):
		"""Make HTTP request with optional DNS bypass"""
		opener = self.create_opener()
		req = urllib.request.Request(url)
		req.add_header('User-Agent', userAgent)
		req.add_header('Referer', referer)
		response = opener.open(req, timeout=30)
		data = response.read().decode('utf-8', errors='ignore')
		response.close()
		return data

	def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
		sources = []
		try:
			import xbmc
			url = ''
			userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

			# Filter out 'none'
			titles = [t for t in titles if t and str(t).lower() != 'none']

			# Try each title
			for title in titles:
				try:
					encoded_title = urllib.parse.quote(title)
					full_url = self.base_link + self.search_link % encoded_title
					xbmc.log('[Filmpalast] Search: %s' % title, xbmc.LOGINFO)

					data = self.make_request(full_url, userAgent, self.base_link)
					xbmc.log('[Filmpalast] Response: %d bytes' % len(data), xbmc.LOGINFO)

					# Parse search results
					content_match = re.search('id="content"[^>]*>(.+?)<[^>]*id="paging"', data, re.S | re.I)
					if not content_match:
						xbmc.log('[Filmpalast] No results section', xbmc.LOGDEBUG)
						continue

					content = content_match.group(1)

					matches = re.findall(
						r'<a[^>]*href="//filmpalast\.to([^"]*)"[^>]*title="([^"]*)"[^>]*>.*?(?:<img[^>]*src=["\']([^"\']*)["\'])?',
						content, re.S | re.I
					)

					xbmc.log('[Filmpalast] Found %d matches' % len(matches), xbmc.LOGINFO)

					if not matches:
						continue

					clean_search = cleantitle.get(title)

					for match_url, match_title, match_image in matches:
						clean_match = cleantitle.get(match_title)

						if clean_search not in clean_match and clean_match not in clean_search:
							continue

						if year and season == 0:
							page_url = self.base_link + match_url
							page_data = self.make_request(page_url, userAgent, self.base_link)

							year_match = re.search(r'>Ver&ouml;ffentlicht: ([^\n<]*)', page_data, re.S | re.I)
							if year_match:
								found_year = year_match.group(1).strip().replace('false', '')
								if found_year and str(year) not in found_year:
									continue

						url = self.base_link + match_url
						xbmc.log('[Filmpalast] Match! %s' % url, xbmc.LOGINFO)
						break

					if url:
						break

				except Exception as e:
					xbmc.log('[Filmpalast] Error: %s' % str(e), xbmc.LOGERROR)
					continue

			if not url:
				return sources

			# Get streams
			xbmc.log('[Filmpalast] Getting streams from %s' % url, xbmc.LOGINFO)
			moviecontent = self.make_request(url, userAgent, self.base_link)

			quality = 'HD'
			quality_match = re.search(r'<span id="release_text"[^>]*>([^<&]*)', moviecontent, re.S | re.I)
			if quality_match:
				release_text = quality_match.group(1).strip()
				if '2160p' in release_text or '4K' in release_text:
					quality = '4K'
				elif '1080p' in release_text:
					quality = '1080p'
				elif '720p' in release_text:
					quality = '720p'

			stream_matches = re.findall(
				r'<p class="hostName">([^<]+)</p>.*?<li[^>]*class="streamPlayBtn[^"]*"[^>]*>.*?<a[^>]*(?:href|data-player-url)="([^"]+)"',
				moviecontent, re.S | re.I
			)

			for hoster, stream_url in stream_matches:
				hoster = hoster.strip()
				isBlocked, resolvedHoster, resolvedUrl, prioHoster = isBlockedHoster(stream_url)

				if isBlocked and prioHoster >= 100:
					continue

				final_hoster = resolvedHoster if resolvedHoster else hoster
				final_url = resolvedUrl if resolvedUrl else stream_url

				sources.append({
					'source': final_hoster,
					'quality': quality,
					'language': 'de',
					'url': final_url,
					'direct': False,
					'debridonly': False
				})

			xbmc.log('[Filmpalast] %d sources' % len(sources), xbmc.LOGINFO)

		except Exception as e:
			import xbmc, traceback
			xbmc.log('[Filmpalast] Error: %s' % str(e), xbmc.LOGERROR)
			xbmc.log('[Filmpalast] Trace: %s' % traceback.format_exc(), xbmc.LOGERROR)

		return sources

	def resolve(self, url):
		return url

	def get_host_and_id(self, url):
		try:
			host = re.findall(r'(?://|\.)([^/]+)\.[a-z]{2,}/', url)
			if host:
				return True, host[0]
		except:
			pass
		return False, None
