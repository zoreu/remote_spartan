# -*- coding: utf-8 -*-
try:
    from helpers import *
    from dns import customdns
except ImportError:
    pass
try:
    # Python 3
    import html
    html_unescape = html.unescape
except ImportError:
    # Python 2
    from HTMLParser import HTMLParser
    html_unescape = HTMLParser().unescape
import calendar
import xml.etree.ElementTree as ET
from datetime import datetime
import time
import re
from six import PY3
import io

# =========================
# Descrições (cache)
# =========================
DESC_TTL = 7 * 24 * 3600  # 7 dias
VOD_DESC_CACHE_PATH = os.path.join(profile, 'vod_desc_cache.json')
SERIES_DESC_CACHE_PATH = os.path.join(profile, 'series_desc_cache.json')
EPG_XML_PATH = os.path.join(profile, 'epg.xml')
EPG_META_PATH = os.path.join(profile, 'epg_meta.json')
EPG_TTL = 24 * 3600  # 24h
_TAG_RE = re.compile(r'<[^>]+>')

_EPG_PARSED = None


def log_xtream(msg, level=xbmc.LOGDEBUG):
    xbmc.log("[{0}] {1}".format(addonID, msg), level)

def ensure_profile_dir():
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdir(profile)

def desc_cache_load(path):
    ensure_profile_dir()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {} 

# =========================
# Descrições (helpers + cache)
# =========================
def clean_plot(text):
    text = html_unescape(text or '')
    text = _TAG_RE.sub('', text)
    return text.strip()  

def desc_cache_get(cache, key):
    k = str(key)
    e = cache.get(k)
    if not isinstance(e, dict):
        return (False, '')
    fetched_at = e.get('fetched_at', 0)
    if not fetched_at or (time.time() - fetched_at) > DESC_TTL:
        return (False, '')
    return (True, e.get('plot', '') or '')

def desc_cache_put(cache, key, plot):
    cache[str(key)] = {'plot': plot or '', 'fetched_at': time.time()}

def safe_requests_get(url, **kw):
    try:
        customdns()
    except:
        pass
    log_xtream('acessando: {0}'.format(url))
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    HEADERS = {'User-Agent': USER_AGENT}    
    kw.setdefault('headers', HEADERS)
    kw.setdefault('timeout', 15)

    # retries leves para 429 (sem martelar)
    if 'xmltv' in url:
        retries = int(kw.pop('retries', 1))
    else:
        retries = int(kw.pop('retries', 2))
    backoff = float(kw.pop('backoff', 1.0))

    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, **kw)
            if r.status_code == 429 and attempt < retries:
                # espera curta e tenta de novo
                time.sleep(backoff * (2 ** attempt))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            log_xtream('Erro na requisicao: {0} - {1}'.format(url,e))
            last_exc = e
            # se for 429 e ainda há tentativa, cai no loop (acima)
            if isinstance(e, requests.HTTPError):
                resp = getattr(e, 'response', None)
                if resp is not None and resp.status_code == 429 and attempt < retries:
                    time.sleep(backoff * (2 ** attempt))
                    continue
            break

    raise last_exc if last_exc else requests.RequestException("Falha na requisição")    


# =========================
# EPG (cache + parsing)
# =========================
def epg_meta_load():
    if os.path.exists(EPG_META_PATH):
        try:
            with io.open(EPG_META_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def epg_meta_save(meta):
    try:
        with io.open(EPG_META_PATH, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_xtream("Falha ao salvar meta EPG: {}".format(e), xbmc.LOGERROR)

def fingerprint(dns,username,password):
    finger = '{0}|{1}|{2}'.format(dns,username,password)
    return finger

def epg_should_refresh(dns,username,password):
    meta = epg_meta_load()
    fp = fingerprint(dns,username,password)
    meta_fp = meta.get('fingerprint')
    fetched_at = meta.get('fetched_at', 0)
    if meta_fp != fp:
        log_xtream("Fingerprint mudou (host/usuário/senha). Renovando EPG.")
        return True
    if not os.path.exists(EPG_XML_PATH):
        log_xtream("EPG não existe. Baixando.")
        return True
    if (time.time() - fetched_at) >= EPG_TTL:
        log_xtream("EPG expirado. Renovando.")
        return True
    return False

def epg_download(dns,username,password):
    ensure_profile_dir()
    url = '{0}/xmltv.php?username={1}&password={2}'.format(dns.rstrip('/'),username,password)
    log_xtream("Baixando EPG: {0}".format(url))
    r = safe_requests_get(url)
    # with open(EPG_XML_PATH, 'w', encoding='utf-8') as f:
    #     f.write(r.text)
    if PY3:
        with open(EPG_XML_PATH, 'w', encoding='utf-8') as f:
            f.write(r.text)
    else:
        # Python 2: precisa escrever bytes
        with io.open(EPG_XML_PATH, 'w', encoding='utf-8') as f:
            if isinstance(r.text, unicode):
                f.write(r.text)
            else:
                f.write(r.text.decode('utf-8', 'ignore'))    
    epg_meta_save({'fingerprint': fingerprint(dns,username,password), 'fetched_at': time.time()})

def parse_xmltv_time(ts):
    if not ts:
        return int(time.time())
    ts = ts.strip()
    if len(ts) < 14 or not ts[:14].isdigit():
        log_xtream("Timestamp XMLTV inválido: {}".format(ts), xbmc.LOGERROR)
        return int(time.time())

    base = ts[:14]
    try:
        dt = datetime.strptime(base, "%Y%m%d%H%M%S")
    except Exception:
        return int(time.time())

    offset_secs = 0
    rest = ts[14:].strip()
    if rest:
        rest = rest.replace(' ', '')
        if rest.startswith(('+', '-')) and len(rest) >= 5:
            try:
                sign = 1 if rest[0] == '+' else -1
                hh = int(rest[1:3])
                mm = int(rest[3:5])
                offset_secs = sign * (hh * 3600 + mm * 60)
            except Exception:
                offset_secs = 0

    epoch = calendar.timegm(dt.timetuple()) - offset_secs
    return epoch if epoch > 0 else int(time.time())

def normalize_epg_channel_id(cid):
    if not cid:
        return ''
    return cid.strip().lower().replace('&amp;', '&')

def epg_load_parsed(dns,username,password):
    global _EPG_PARSED

    if epg_should_refresh(dns,username,password):
        try:
            epg_download(dns,username,password)
        except Exception as e:
            log_xtream("Falha ao baixar EPG: {}".format(e), xbmc.LOGERROR)
            _EPG_PARSED = {'channels': {}, 'progs': {}}
            return _EPG_PARSED

    if not os.path.exists(EPG_XML_PATH):
        _EPG_PARSED = {'channels': {}, 'progs': {}}
        return _EPG_PARSED

    try:
        tree = ET.parse(EPG_XML_PATH)
        root = tree.getroot()

        channels = {}
        progs = {}

        for c in root.findall(".//channel"):
            cid = normalize_epg_channel_id(c.get('id'))
            dn = (c.findtext('display-name') or '').strip()
            channels[cid] = dn

        for p in root.findall(".//programme"):
            cid = normalize_epg_channel_id(p.get('channel'))

            try:
                start = int(p.get('start_timestamp'))
            except (TypeError, ValueError):
                start = parse_xmltv_time(p.get('start'))

            try:
                stop = int(p.get('stop_timestamp') or p.get('end_timestamp'))
            except (TypeError, ValueError):
                stop = parse_xmltv_time(p.get('stop') or p.get('end'))

            if stop <= start:
                stop = start + 3600

            title = (p.findtext('title') or '').strip()
            desc = (p.findtext('desc') or '').strip()

            if cid not in progs:
                progs[cid] = []

            progs[cid].append({'start': start, 'end': stop, 'title': title, 'desc': desc})

        for cid, arr in progs.items():
            arr.sort(key=lambda x: x['start'])

        _EPG_PARSED = {'channels': channels, 'progs': progs}
        log_xtream("EPG carregado: canais={0}, programas={1}".format(len(channels), sum(len(v) for v in progs.values())))
    except Exception as e:
        log_xtream("Erro parseando EPG: {}".format(e), xbmc.LOGERROR)
        _EPG_PARSED = {'channels': {}, 'progs': {}}

    return _EPG_PARSED

def epg_lookup_current_next(epg_channel_id, epg):
    cid = normalize_epg_channel_id(epg_channel_id)
    now = int(time.time())

    plist = epg['progs'].get(cid, [])
    current, nextp = None, None

    for i, pr in enumerate(plist):
        start = pr.get('start') or now
        end = pr.get('end') or (start + 3600)
        if end <= start:
            end = start + 3600
        pr['start'] = start
        pr['end'] = end

        if start <= now < end:
            current = pr
            if i + 1 < len(plist):
                nextp = plist[i + 1]
            break
        if start > now:
            nextp = pr
            if i - 1 >= 0 and plist[i - 1]['end'] > now:
                current = plist[i - 1]
            break

    return current, nextp

def extract_info(url):
    # Parseia a URL
    parsed_url = urlparse(url)
    protocol = parsed_url.scheme
    # Extrai o host e a porta
    host = parsed_url.hostname
    # Define a porta padrão se não estiver especificada
    if parsed_url.port:
        port = parsed_url.port
    else:
        port = 80 if parsed_url.scheme == 'http' else 443
    
    # Extrai o username e o password dos parâmetros da query
    query_params = parse_qs(parsed_url.query)
    username = query_params.get('username', [None])[0]
    password = query_params.get('password', [None])[0]
    dns = '{0}://{1}:{2}'.format(protocol,host,port)
    
    return dns, username, password

def parselist(url):
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    HEADERS = {'User-Agent': USER_AGENT}    
    iptv = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        src = r.text
        lines = src.split('\n')
        if lines:
            for i in lines:
                i = i.replace(' ', '')
                if 'http' in i:
                    dns, username, password = extract_info(i)
                    iptv.append({'dns': dns, 'username': username, 'password': password})
    except:
        pass
    # teste iptv - tirar isso
    return iptv

# =========================
# Funções de dados
# =========================

def get_json(dns,username,password,endpoint):
    url = '{0}/player_api.php?username={1}&password={2}&{3}'.format(dns.rstrip('/'),username,password,endpoint)

    try:
        r = safe_requests_get(url)
        return r.json()
    except requests.RequestException as e:
        # se for 429, mensagem mais clara
        try:
            status = e.response.status_code if getattr(e, 'response', None) is not None else None
        except Exception:
            status = None

        if status == 429:
            log_xtream("Erro 429", "Muitas requisições para a API (rate limit).\nTente novamente em instantes.")
        else:
            log_xtream("Erro", "Falha na API: {0}".format(e))
    except ValueError:
        log_xtream("Resposta inválida (não-JSON) da API: {0}".format(url), xbmc.LOGERROR)
    return None

def get_categories(dns,username,password,endpoint):
    data = get_json(dns,username,password,endpoint)
    if not data:
        return []

    if isinstance(data, list):
        cats = data
    elif isinstance(data, dict) and 'categories' in data:
        cats = data['categories']
    else:
        cats = list(data.values()) if isinstance(data, dict) else []

    items = []
    for cat in cats:
        name = html_unescape(cat.get('category_name', 'Sem nome'))
        try:
            if 'adult' in name.lower() and getsetting('hidexxx').lower() != 'true':
                continue
        except:
            pass
        items.append({
            'title': name,
            'cid': cat.get('category_id', '')
        })
    return items

def ensure_epg_loaded(dns,username,password):
    global _EPG_PARSED
    if _EPG_PARSED is None:
        _EPG_PARSED = epg_load_parsed(dns,username,password)
    return _EPG_PARSED

def annotate_live_with_epg(dns,username,password,items_from_api):
    epg = ensure_epg_loaded(dns,username,password)
    out = []
    for s in items_from_api:
        name = s.get('title') or s.get('name') or 'Sem nome'
        epg_id = s.get('epg_channel_id')
        current, nextp = epg_lookup_current_next(epg_id, epg) if epg_id else (None, None)

        label = name
        plot = ''
        if current:
            label = "{0} - {1}".format(name, current.get('title', '').strip())
            plot += "Agora: {0}\n{1}\n\n".format(current.get('title', '').strip(), current.get('desc', '').strip())
        if nextp:
            plot += "Próximo: {0}\n{1}".format(nextp.get('title', '').strip(), nextp.get('desc', '').strip())

        s2 = dict(s)
        s2['title'] = label
        if plot.strip():
            s2['plot'] = plot.strip()
        out.append(s2)
    return out

def get_items(dns, username, password, endpoint, category_id=None):
    params = "&category_id={0}".format(category_id) if category_id else ""
    data = get_json(dns,username,password,"action={0}{1}".format(endpoint,params))
    if not data:
        return []

    items = []

    if endpoint in ['get_live_streams', 'get_vod_streams']:
        vod_cache = None
        if endpoint == 'get_vod_streams':
            vod_cache = desc_cache_load(VOD_DESC_CACHE_PATH)

        for s in data:
            url = s.get('stream_url', '')
            sid = s.get('stream_id')
            stype = s.get('stream_type', '')
            name = html_unescape(s.get('name', 'Sem nome'))
            icon = s.get('stream_icon', '')
            epg_channel_id = s.get('epg_channel_id') or None

            if sid:
                if endpoint == 'get_live_streams':
                    url = '{0}/live/{1}/{2}/{3}.m3u8'.format(dns.rstrip("/"), username, password, sid)
                else:
                    ext = 'mp4'
                    url = '{0}/live/{1}/{2}/{3}.{4}'.format(dns.rstrip("/"), username, password, sid, ext)

            item = {'title': name, 'url': url, 'icon': icon}

            if epg_channel_id:
                item['epg_channel_id'] = epg_channel_id

            # Filme: NÃO buscar vod_info aqui (evita 429). Só usa cache/lista.
            if endpoint == 'get_vod_streams' and sid:
                item['vod_id'] = sid
                plot = clean_plot(s.get('plot') or s.get('description') or '')
                if not plot and vod_cache is not None:
                    has, cached_plot = desc_cache_get(vod_cache, sid)
                    if has:
                        plot = cached_plot
                if plot:
                    item['plot'] = plot

            items.append(item)

        try:
            if endpoint == 'get_live_streams' and getsetting('epg').lower() == 'true':
                items = annotate_live_with_epg(dns,username,password,items)
        except:
            pass

    elif endpoint == 'get_series':
        series_cache = desc_cache_load(SERIES_DESC_CACHE_PATH)

        for s in data:
            icon = (s.get('info', {}) or {}).get('cover_big') or (s.get('info', {}) or {}).get('movie_image', '')
            if not icon:
                icon = s.get('cover') if s.get('cover') else s.get('backdrop_path', [''])[0]

            series_id = s.get('series_id', '')
            title = html_unescape(s.get('name', 'Sem nome'))

            # item = {
            #     'title': title,
            #     'params': f"series_id={series_id}",
            #     'icon': icon,
            #     'series_id': series_id
            # }
            item = {
                'title': title,
                'params': "series_id={0}".format(series_id),
                'icon': icon,
                'series_id': series_id
            }            

            # Série: NÃO buscar series_info aqui (evita 429). Só cache/lista.
            plot = clean_plot(
                s.get('plot')
                or (s.get('info', {}) or {}).get('plot')
                or (s.get('info', {}) or {}).get('overview')
                or ''
            )
            if not plot and series_id:
                has, cached_plot = desc_cache_get(series_cache, series_id)
                if has:
                    plot = cached_plot
            if plot:
                item['plot'] = plot

            items.append(item)

    return items
