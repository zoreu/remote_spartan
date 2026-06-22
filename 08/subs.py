# -*- coding: utf-8 -*-
import requests

def get_subs(imdb,season,episode):
    subs_ = []
    if season and episode:
        url = 'https://sub.wyzie.ru/search?id={}&language=pb&season={}&episode={}'.format(imdb,season,episode)
    else:
        url = 'https://sub.wyzie.ru/search?id={}&language=pb'.format(imdb)
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'}, timeout=15)
        response.encoding = 'utf-8'
        data = response.json()
        for sub in data:
            subs_.append(sub['url'])
    except:
        pass
    return subs_

def test_subs():
    print(get_subs('tt0133093',None,None))


