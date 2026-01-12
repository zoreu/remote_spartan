# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import requests
from six.moves.urllib.parse import quote
from six import text_type
import sys
try:
    from kodi_six import xbmc
except ImportError:
    import xbmc  # Added for debug logging
try:
    from dns import customdns
except:
    pass


API_KEY = "92c1507cc18d85290e7a0b96abb37316"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

def get_json_tmdb(url):
    try:
        customdns()
    except:
        pass    
    try:
        response = requests.get(url)
        response.encoding = 'utf-8'  # Ensure UTF-8 encoding
        return response.json()
    except:
        return {}

def get_items_tmdb(type_, category, page=1):
    if category == 'trending':
        url = TMDB_BASE_URL + "/trending/{}/week?api_key={}&language=pt-BR&page={}".format(
            'tv' if type_ == 'series' else 'movie', API_KEY, page)
    elif category == 'top':
        url = TMDB_BASE_URL + "/{}/top_rated?api_key={}&language=pt-BR&page={}".format(
            'tv' if type_ == 'series' else 'movie', API_KEY, page)
    elif category == 'latest':
        url = TMDB_BASE_URL + "/{}/now_playing?api_key={}&language=pt-BR&page={}".format(
            'tv' if type_ == 'series' else 'movie', API_KEY, page)
    else:
        url = TMDB_BASE_URL + "/discover/{}?api_key={}&language=pt-BR&page={}".format(
            'tv' if type_ == 'series' else 'movie', API_KEY, page)

    data = get_json_tmdb(url)
    items = []

    for item in data.get("results", []):
        title = item.get("title") or item.get("name")
        if not isinstance(title, text_type):
            title = title.decode('utf-8') if sys.version_info[0] == 2 else title
        poster = "https://image.tmdb.org/t/p/w500{}".format(item["poster_path"]) if item.get("poster_path") else None
        background = "https://image.tmdb.org/t/p/original{}".format(item["backdrop_path"]) if item.get("backdrop_path") else None
        description = item.get('overview', '')
        if not isinstance(description, text_type):
            description = description.decode('utf-8') if sys.version_info[0] == 2 else description
        year = item.get('release_date' if type_ == 'movie' else 'first_air_date', '')
        year = year[:4] if year else ''
        items.append({
            'id': str(item['id']),
            'title': title,
            'poster': poster,
            'background': background,
            'description': description,
            'year': year
        })
    return items

def get_meta_tmdb(type_, tmdb_id):
    url = TMDB_BASE_URL + "/{}/{}?api_key={}&language=pt-BR".format(
        'tv' if type_ == 'series' else 'movie', tmdb_id, API_KEY)
    data = get_json_tmdb(url)

    name = data.get('name') if type_ == 'series' else data.get('title')
    if not isinstance(name, text_type):
        name = name.decode('utf-8') if sys.version_info[0] == 2 else name
    description = data.get('overview', '')
    if not isinstance(description, text_type):
        description = description.decode('utf-8') if sys.version_info[0] == 2 else description
    year = data.get('first_air_date' if type_ == 'series' else 'release_date', '')
    year = year[:4] if year else ''

    meta = {
        'name': name,
        'description': description,
        'poster': "https://image.tmdb.org/t/p/w500{}".format(data['poster_path']) if data.get('poster_path') else None,
        'background': "https://image.tmdb.org/t/p/original{}".format(data['backdrop_path']) if data.get('backdrop_path') else None,
        'year': year
    }
    return meta

def get_seasons(type_, tmdb_id):
    if type_ != 'series':
        return []
    url = TMDB_BASE_URL + "/tv/{}?api_key={}&language=pt-BR".format(tmdb_id, API_KEY)
    data = get_json_tmdb(url)
    seasons = []
    for season in data.get("seasons", []):
        if season.get("season_number") is not None:
            name = season.get('name', 'Temporada {}'.format(season['season_number']))
            if not isinstance(name, text_type):
                name = name.decode('utf-8') if sys.version_info[0] == 2 else name
            description = season.get('overview', '')
            if not isinstance(description, text_type):
                description = description.decode('utf-8') if sys.version_info[0] == 2 else description
            year = season.get('air_date', '')
            year = year[:4] if year else ''
            seasons.append({
                'season_number': season['season_number'],
                'name': name,
                'poster': "https://image.tmdb.org/t/p/w500{}".format(season['poster_path']) if season.get('poster_path') else None,
                'description': description,
                'episode_count': season.get('episode_count', 0),
                'year': year
            })
    return seasons

def get_episodes(type_, tmdb_id, season_number):
    if type_ != 'series':
        return []
    url = TMDB_BASE_URL + "/tv/{}/season/{}?api_key={}&language=pt-BR".format(tmdb_id, season_number, API_KEY)
    data = get_json_tmdb(url)
    episodes = []
    for episode in data.get("episodes", []):
        name = episode.get('name', 'Episódio {}'.format(episode['episode_number']))
        if not isinstance(name, text_type):
            name = name.decode('utf-8') if sys.version_info[0] == 2 else name
        description = episode.get('overview', '')
        if not isinstance(description, text_type):
            description = description.decode('utf-8') if sys.version_info[0] == 2 else description
        year = episode.get('air_date', '')
        year = year[:4] if year else ''
        episodes.append({
            'episode_number': episode['episode_number'],
            'name': name,
            'poster': "https://image.tmdb.org/t/p/w500{}".format(episode['still_path']) if episode.get('still_path') else None,
            'description': description,
            'id': text_type(episode['id']),
            'year': year
        })
    return episodes

def search_tmdb(type_, query, page=1):
    if not query or not isinstance(query, text_type):  # Handle None or empty query
        return []
    xbmc.log("TMDB Search query: {}".format(repr(query)), level=xbmc.LOGDEBUG)  # Debug log
    q = quote(query.encode('utf-8'))  # Always encode to bytes for quote
    xbmc.log("TMDB Search encoded query: {}".format(q), level=xbmc.LOGDEBUG)  # Debug log
    url = TMDB_BASE_URL + "/search/{}?api_key={}&language=pt-BR&query={}&page={}".format(
        'tv' if type_ == 'series' else 'movie', API_KEY, q, page)
    xbmc.log("TMDB Search URL: {}".format(url), level=xbmc.LOGDEBUG)  # Debug log
    data = get_json_tmdb(url)
    results = []
    for item in data.get("results", []):
        title = item.get("title") or item.get("name")
        if not isinstance(title, text_type):
            title = title.decode('utf-8') if sys.version_info[0] == 2 else title
        description = item.get('overview', '')
        if not isinstance(description, text_type):
            description = description.decode('utf-8') if sys.version_info[0] == 2 else description
        year = item.get('release_date' if type_ == 'movie' else 'first_air_date', '')
        year = year[:4] if year else ''
        results.append({
            'id': str(item['id']),
            'title': title,
            'poster': "https://image.tmdb.org/t/p/w500{}".format(item["poster_path"]) if item.get("poster_path") else None,
            'background': "https://image.tmdb.org/t/p/original{}".format(item["backdrop_path"]) if item.get("backdrop_path") else None,
            'description': description,
            'year': year
        })
    return results

def get_imdb_id_tmdb(tmdb_id, media_type):
    try:
        customdns()
    except:
        pass    
    if media_type == 'series':
        media_type = 'tv'
    url = "https://api.themoviedb.org/3/{}/{}/external_ids?api_key={}".format(
        text_type(media_type), text_type(tmdb_id), text_type(API_KEY)
    )
    try:
        response = requests.get(url)
        response.encoding = 'utf-8'  # Ensure UTF-8 encoding for response
        if response.status_code == 200:
            data = response.json()
            return data.get("imdb_id")
        return None
    except:
        return None