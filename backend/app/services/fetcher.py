import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin
import httpx
from app.services.text_cleaner import clean_html
from app.services.jsonld_parser import parse_jsonld


def normalize_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path,urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','trk','refid'}]),''))


async def safe_target(url):
    p = urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password: raise ValueError('Only public http/https job URLs are allowed')
    try:
        port = p.port or (443 if p.scheme=='https' else 80)
        if port not in {80,443}: raise ValueError('Only standard web ports are allowed')
        addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(p.hostname,port,type=socket.SOCK_STREAM),timeout=5)
    except (OSError,ValueError,TimeoutError): raise ValueError('Cannot resolve a public job URL') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError('Private, loopback and link-local addresses are not allowed')
    address = addresses[0][4][0]
    host = f'[{address}]' if ':' in address else address
    return urlunsplit((p.scheme,host,p.path or '/',p.query,'')), p.hostname


def acceptable(text):
    words = {'responsibilities','requirements','skills','apply','qualification','experience','role','eligibility','stipend','salary'}
    return len(text)>=600 and sum(w in text.lower() for w in words)>=2


async def fetch_url(url):
    current = normalize_url(url)
    async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
        for _ in range(6):
            pinned, hostname = await safe_target(current)
            async with client.stream('GET',pinned,headers={'Host':hostname,'User-Agent':'Mozilla/5.0 JobPortal personal intake'},extensions={'sni_hostname':hostname}) as response:
                if response.status_code in {301,302,303,307,308}:
                    current = urljoin(current,response.headers.get('location',''))
                    continue
                if response.status_code>=400: raise ValueError('This page needs login or blocks automated reading. Paste the text or upload a screenshot.')
                if 'text/' not in response.headers.get('content-type','') and 'html' not in response.headers.get('content-type',''): raise ValueError('The URL is not a readable job page. Upload the PDF or paste text.')
                chunks=[];size=0
                async for chunk in response.aiter_bytes():
                    size+=len(chunk)
                    if size>5*1024*1024: raise ValueError('Job page exceeds the 5 MB limit')
                    chunks.append(chunk)
                html=b''.join(chunks).decode(response.encoding or 'utf-8',errors='replace')
            structured=parse_jsonld(html);text=clean_html(html)
            if structured:
                import json
                text+='\n'+clean_html(structured['description'])+'\n'+json.dumps(structured,ensure_ascii=False)
                return text,'jsonld',structured
            if acceptable(text): return text,'http',None
            # Rendering is isolated and all browser requests are pinned through the same safe fetcher.
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser=await pw.chromium.launch(headless=True,args=['--no-sandbox'])
                context=await browser.new_context(service_workers='block')
                async def route_request(route):
                    try:
                        target,host=await safe_target(route.request.url)
                        if route.request.resource_type in {'image','media','font','websocket'}: return await route.abort()
                        # Fetch pinned addresses to prevent a DNS-rebinding window in Chromium.
                        async with client.stream('GET',target,headers={'Host':host,'User-Agent':'Mozilla/5.0'},extensions={'sni_hostname':host}) as r:
                            if 300<=r.status_code<400: return await route.abort()
                            payload=bytearray()
                            async for chunk in r.aiter_bytes():
                                payload.extend(chunk)
                                if len(payload)>5*1024*1024: return await route.abort()
                            await route.fulfill(status=r.status_code,headers={'content-type':r.headers.get('content-type','text/plain')},body=bytes(payload))
                    except Exception: await route.abort()
                await context.route('**/*',route_request)
                page=await context.new_page()
                try:
                    await page.goto(current,wait_until='networkidle',timeout=25000)
                    await page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
                    text=clean_html(await page.content())
                finally: await browser.close()
            if acceptable(text): return text,'playwright',None
            raise ValueError('This page needs login or blocks automated reading. Paste the text or upload a screenshot.')
    raise ValueError('Too many redirects. Paste the job text instead.')
