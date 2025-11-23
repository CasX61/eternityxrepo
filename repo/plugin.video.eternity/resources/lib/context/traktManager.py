# -*- coding: utf-8 -*-
"""
Eternity Trakt Manager - Context Menu
Based on Umbrella's traktManager.py
CLAUDE.md Phase 1.2 requirement
"""

import sys
from xbmc import getInfoLabel, executebuiltin
from urllib.parse import parse_qsl, quote_plus

if __name__ == '__main__':
	item = sys.listitem
	path = item.getPath()

	plugin = 'plugin://plugin.video.eternity/'
	args = path.split(plugin, 1)

	if len(args) < 2:
		# Not an Eternity plugin path
		sys.exit()

	params = dict(parse_qsl(args[1].replace('?', '')))

	# Get name (TV show title or movie title)
	name = params.get('tvshowtitle') if 'tvshowtitle' in params else params.get('title', '')
	sysname = quote_plus(name)

	# Get IDs
	imdb = params.get('imdb', '')
	tvdb = params.get('tvdb', '')
	season = params.get('season', '')
	episode = params.get('episode', '')

	# Get watched status
	playcount = getInfoLabel('ListItem.Playcount')
	watched = (int(playcount) >= 1) if playcount else False

	# Get unfinished status
	unfinished = item.getProperty('unfinished') == 'true'

	# Build RunPlugin path
	path = 'RunPlugin(%s?action=tools_traktManager&name=%s&imdb=%s&tvdb=%s&season=%s&episode=%s&watched=%s&unfinished=%s)' % (
				plugin, sysname, imdb, tvdb, season, episode, watched, unfinished)

	executebuiltin(path)
