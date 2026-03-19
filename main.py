import os
import json
import re
import requests
import feedparser
from groq import Groq
from datetime import datetime
from google.oauth2 import service_account
from google.auth.transport.requests import Request

GROQ_API_KEY          = os.environ['GROQ_API_KEY']
BLOGGER_BLOG_ID       = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN  = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID      = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET  = os.environ['GOOGLE_CLIENT_SECRET']
UNSPLASH_ACCESS_KEY   = os.environ['UNSPLASH_ACCESS_KEY']
GOOGLE_INDEXING_SA    = os.environ['GOOGLE_INDEXING_SA']

HARD_BLOCKLIST = [
    'trump indictment', 'pleads not guilty', '34 felony',
    'hush money', 'stormy daniels', 'temporal javascript',
    'knitting', 'common lisp', 'amen break'
]

def is_blocked(title):
    return any(b in title.lower() for b in HARD_BLOCKLIST)

def get_indexing_token():
    sa_info = json.loads(GOOGLE_INDEXING_SA)
    credentials = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/indexing']
    )
    credentials.refresh(Request())
    return credentials.token

def auto_index_url(url):
    try:
        token = get_indexing_token()
        r = requests.post(
            'https://indexing.googleapis.com/v3/urlNotifications:publish',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'url': url, 'type': 'URL_UPDATED'}, timeout=15
        )
        print(f"Google Indexing API: {r.status_code}")
    except Exception as e:
        print(f"Auto-index failed: {e}")

def get_unsplash_image(query):
    try:
        r = requests.get(
            'https://api.unsplash.com/search/photos',
            params={'query': query, 'per_page': 1, 'orientation': 'landscape'},
            headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'}, timeout=10
        )
        data = r.json()
        if data.get('results'):
            photo = data['results'][0]
            return photo['urls']['regular'], photo['user']['name'], photo['links']['html']
    except Exception as e:
        print(f"Unsplash failed: {e}")
    return None, None, None

def get_access_token():
    r = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'refresh_token': GOOGLE_REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    }, timeout=15)
    result = r.json()
    if 'access_token' not in result:
        raise Exception(f"Token failed: {result}")
    return result['access_token']

def get_existing_post_titles():
    try:
        token = get_access_token()
        r = requests.get(
            f'https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts',
            headers={'Authorization': f'Bearer {token}'},
            params={'maxResults': 40, 'fields': 'items(title)'}, timeout=15
        )
        titles = [item['title'].lower() for item in r.json().get('items', [])]
        print(f"Existing posts: {len(titles)}")
        return titles
    except Exception as e:
        print(f"Could not fetch existing posts: {e}")
        return []

def is_duplicate(title, existing_titles):
    stopwords = {'the','a','an','is','in','on','at','to','for','of','and','or','but','what','why','how','who','when','where'}
    keywords = set(title.lower().split()) - stopwords
    for existing in existing_titles:
        if len(keywords & (set(existing.split()) - stopwords)) >= 3:
            return True
    return False

def get_trending_topics():
    topics = []
    sources = [
        ('http://feeds.bbci.co.uk/news/rss.xml', 'bbc_news', 8),
        ('https://feeds.reuters.com/reuters/topNews', 'reuters', 6),
        ('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en', 'google_news', 12),
        ('https://feeds.skynews.com/feeds/rss/world.xml', 'sky_news', 5),
        ('https://techcrunch.com/feed/', 'techcrunch', 6),
        ('https://www.theverge.com/rss/index.xml', 'theverge', 5),
        ('https://www.espn.com/espn/rss/news', 'espn', 4),
        ('https://variety.com/feed/', 'variety', 4),
    ]
    for url, source, limit in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                if not is_blocked(entry.title):
                    topics.append({"title": entry.title, "source": source})
            print(f"{source}: added")
        except Exception as e:
            print(f"{source} failed: {e}")
    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:6]:
            s = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if s.get('title') and not is_blocked(s['title']):
                topics.append({"title": s['title'], "source": "hackernews"})
        print("HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")
    print(f"\n=== FETCHED HEADLINES ===")
    for i, t in enumerate(topics):
        print(f"{i+1}. [{t['source']}] {t['title']}")
    print(f"=== TOTAL: {len(topics)} ===\n")
    return topics

def pick_topic(client, topics, existing_titles, category_name, avoid_keywords, today):
    remaining = [t for t in topics if not is_duplicate(t['title'], existing_titles)]
    if not remaining:
        # Brainstorm
        existing_str = '\n'.join(existing_titles[:15]) if existing_titles else 'none'
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Today is {today}. Brainstorm ONE trending topic for category '{category_name}'. Already covered:\n{existing_str}\nReply with topic title only."}],
            temperature=0.9, max_tokens=50
        )
        return r.choices[0].message.content.strip(), True

    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(remaining)])
    avoid_str = ', '.join(avoid_keywords) if avoid_keywords else 'none'
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Today is {today}.\nHeadlines:\n{topics_text}\nCategory: {category_name}\nAvoid: {avoid_str}\nPick ONE headline with max Google searches. Reply BRAINSTORM if nothing fits, else reply with exact headline only."}],
        temperature=0.2, max_tokens=100
    )
    chosen = r.choices[0].message.content.strip()
    if 'BRAINSTORM' in chosen or len(chosen) > 200:
        existing_str = '\n'.join(existing_titles[:15]) if existing_titles else 'none'
        r2 = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Today is {today}. Brainstorm ONE trending topic for '{category_name}'. Already covered:\n{existing_str}\nReply with topic title only."}],
            temperature=0.9, max_tokens=50
        )
        return r2.choices[0].message.content.strip(), True
    return chosen, False

def write_post(topics, existing_titles, category_name, avoid_keywords):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')
    chosen, is_brainstormed = pick_topic(client, topics, existing_titles, category_name, avoid_keywords, today)
    print(f"Writing [{category_name}]: {chosen} ({'brainstormed' if is_brainstormed else 'from news'})")

    # Step 1: Write the article as plain HTML
    article_prompt = f"""You are a Pulitzer-level journalist and SEO expert. Today is {today}.

Write a 2000-word SEO blog post about: "{chosen}"

Rules:
- Title: 55-60 chars, primary keyword, use power word (Explained/Breaking/What You Need to Know)  
- Intro: shocking fact, use "You", keyword in first 100 words, curiosity gap
- H2s: exact questions people Google
- Include: bold key facts, bullet list, What Experts Say, What Happens Next
- FAQ section: 6 Q&As, 40-60 word answers
- EEAT: specific dates, stats, named experts
- HTML tags only: h2, p, strong, ul, li

Write the full article now:"""

    article_r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": article_prompt}],
        temperature=0.7, max_tokens=3500
    )
    article_html = article_r.choices[0].message.content.strip()

    # Step 2: Extract metadata separately — much smaller JSON, no content inside
    meta_prompt = f"""For this article topic: "{chosen}"
Today is {today}.

Return ONLY this JSON (no markdown, no backticks):
{{"title":"SEO title 55-60 chars","meta_description":"155 char description","primary_keyword":"main keyword","secondary_keywords":["k1","k2","k3","k4"],"image_search_query":"3 word query","tags":["t1","t2","t3","t4","t5"],"slug":"url-slug"}}"""

    meta_r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": meta_prompt}],
        temperature=0.3, max_tokens=300
    )
    meta_raw = meta_r.choices[0].message.content.strip()
    if meta_raw.startswith('```'):
        meta_raw = meta_raw.split('```')[1]
        if meta_raw.startswith('json'):
            meta_raw = meta_raw[4:]
    meta_raw = meta_raw.strip()
    meta = json.loads(meta_raw)
    meta['content'] = article_html
    meta['chosen_topic'] = chosen
    return meta

def build_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    img_url, photographer, photo_link = get_unsplash_image(post.get('image_search_query', post['primary_keyword']))

    hero = f"""<div style="margin-bottom:24px;"><img src="{img_url}" alt="{post['title']}" style="width:100%;border-radius:8px;"/><p style="font-size:12px;color:#888;margin-top:4px;">Photo by <a href="{photo_link}" target="_blank">{photographer}</a> on <a href="https://unsplash.com" target="_blank">Unsplash</a></p></div>""" if img_url else ""

    faq = json.dumps({"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":f"What is {post['primary_keyword']}?","acceptedAnswer":{"@type":"Answer","text":post['meta_description']}},
        {"@type":"Question","name":f"Why is {post['primary_keyword']} important?","acceptedAnswer":{"@type":"Answer","text":f"{post['title']} - one of today's most searched topics. {post['meta_description']}"}},
        {"@type":"Question","name":f"What are the latest updates on {post['primary_keyword']}?","acceptedAnswer":{"@type":"Answer","text":f"As of {datetime.utcnow().strftime('%B %d, %Y')}, {post['meta_description']}"}}
    ]})

    news = json.dumps({"@context":"https://schema.org","@type":"NewsArticle","headline":post['title'],"description":post['meta_description'],"datePublished":now_iso,"dateModified":now_iso,"image":img_url or "","keywords":', '.join(post.get('secondary_keywords',[])),"author":{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"},"publisher":{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"}})

    schema = f"""<script type="application/ld+json">{news}</script>
<script type="application/ld+json">{faq}</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{post['primary_keyword']}, {', '.join(post.get('secondary_keywords',[]))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
<meta property="og:image" content="{img_url or ''}"/>
<meta property="og:type" content="article"/>
<meta name="robots" content="index, follow"/>
"""
    return schema + hero + post['content']

def ping_indexnow(url):
    try:
        r = requests.get('https://api.indexnow.org/indexnow',
            params={'url': url, 'key': '5ce0a0281fb341549bbec44bda7c063c'}, timeout=10)
        print(f"IndexNow: {r.status_code}")
    except Exception as e:
        print(f"IndexNow failed: {e}")

def publish(post, final_content):
    token = get_access_token()
    r = requests.post(
        f'https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={'title': post['title'], 'content': final_content, 'labels': post.get('tags', [])},
        timeout=30
    )
    result = r.json()
    if 'url' in result:
        print(f"PUBLISHED: {result['url']}")
        ping_indexnow(result['url'])
        auto_index_url(result['url'])
        return result['url']
    raise Exception(f"Failed: {result}")

if __name__ == '__main__':
    print(f"Starting - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    topics = get_trending_topics()
    existing_titles = get_existing_post_titles()
    all_categories = [
        {"name": "World News & Politics", "avoid": []},
        {"name": "Technology, AI & New Companies", "avoid": ["war","iran","attack","military","shooting","killed","dead"]},
        {"name": "Sports, Entertainment or Business", "avoid": ["war","iran","attack","military","shooting","killed","dead","politics"]},
    ]
    cat = all_categories[datetime.utcnow().hour % 3]
    print(f"\n--- Category: {cat['name']} ---")
    try:
        post = write_post(topics, existing_titles, cat['name'], cat['avoid'])
        final_content = build_content(post)
        publish(post, final_content)
        print("DONE!")
    except Exception as e:
        print(f"Failed: {e}")
