import os
import json
import time
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
    t = title.lower()
    return any(b in t for b in HARD_BLOCKLIST)

def clean_json(raw):
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    raw = raw.strip()
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    return raw

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
            json={'url': url, 'type': 'URL_UPDATED'},
            timeout=15
        )
        print(f"Google Indexing API: {r.status_code}")
    except Exception as e:
        print(f"Auto-index failed: {e}")

def get_unsplash_image(query):
    try:
        r = requests.get(
            'https://api.unsplash.com/search/photos',
            params={'query': query, 'per_page': 1, 'orientation': 'landscape'},
            headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
            timeout=10
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
            params={'maxResults': 40, 'fields': 'items(title)'},
            timeout=15
        )
        items = r.json().get('items', [])
        titles = [item['title'].lower() for item in items]
        print(f"Existing posts fetched: {len(titles)}")
        return titles
    except Exception as e:
        print(f"Could not fetch existing posts: {e}")
        return []

def is_duplicate(title, existing_titles):
    title_lower = title.lower()
    stopwords = {'the','a','an','is','in','on','at','to','for','of','and','or','but','what','why','how','who','when','where'}
    keywords = set(title_lower.split()) - stopwords
    for existing in existing_titles:
        existing_keywords = set(existing.split()) - stopwords
        if len(keywords & existing_keywords) >= 3:
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
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title') and not is_blocked(story['title']):
                topics.append({"title": story['title'], "source": "hackernews"})
        print("HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")
    print(f"\n=== FETCHED HEADLINES ===")
    for i, t in enumerate(topics):
        print(f"{i+1}. [{t['source']}] {t['title']}")
    print(f"=== TOTAL: {len(topics)} ===\n")
    return topics

def brainstorm_topic(client, category_name, existing_titles, today):
    existing_str = '\n'.join(existing_titles[:20]) if existing_titles else 'none yet'
    prompt = f"""Today is {today}. You are an expert SEO content strategist.
Category: "{category_name}"
Already covered (do NOT repeat):
{existing_str}
Brainstorm ONE trending topic in "{category_name}" that people are searching for RIGHT NOW in 2026.
Reply with ONLY the topic title. Nothing else."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )
    topic = response.choices[0].message.content.strip()
    print(f"AI brainstormed [{category_name}]: {topic}")
    return topic

def pick_topic(client, topics, existing_titles, category_name, avoid_keywords, today):
    remaining = [t for t in topics if not is_duplicate(t['title'], existing_titles)]
    if not remaining:
        return brainstorm_topic(client, category_name, existing_titles, today), True
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(remaining)])
    avoid_str = ', '.join(avoid_keywords) if avoid_keywords else 'none'
    prompt = f"""Today is {today}.
Headlines:
{topics_text}
Category: "{category_name}"
Avoid: {avoid_str}
Pick ONE headline fitting "{category_name}" with max Google searches today.
If nothing fits, reply: BRAINSTORM
Otherwise reply with ONLY the exact headline."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    chosen = response.choices[0].message.content.strip()
    if chosen == 'BRAINSTORM' or len(chosen) > 200:
        return brainstorm_topic(client, category_name, existing_titles, today), True
    return chosen, False

def write_post(topics, existing_titles, category_name, avoid_keywords):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')
    chosen, is_brainstormed = pick_topic(client, topics, existing_titles, category_name, avoid_keywords, today)
    print(f"Writing [{category_name}]: {chosen} ({'brainstormed' if is_brainstormed else 'from news'})")

    prompt = f"""You are a Pulitzer-level journalist and SEO expert. Today is {today}.
Write a 2000-word SEO blog post about: "{chosen}"

TITLE: 55-60 chars, primary keyword, power word (Explained/Breaking/What You Need to Know)
INTRO: shocking fact, use "You", primary keyword in first 100 words, curiosity gap ending
H2s: exact questions people Google
STRUCTURE: bold key facts, one ul list with 4-6 items, What Experts Say section, What Happens Next section
KEYWORDS: primary 8-12 times, 4 secondary keywords 2-3 times each
FAQ: 6 Q&As targeting featured snippets, 40-60 word answers
EEAT: specific dates, stats, named experts and organizations
HTML only: h2, p, strong, ul, li tags

Return ONLY valid single-line JSON, no markdown, escape all quotes:
{{"chosen_topic":"topic","title":"title","meta_description":"155 char description","primary_keyword":"keyword","secondary_keywords":["k1","k2","k3","k4"],"image_search_query":"3 words","content":"HTML","tags":["t1","t2","t3","t4","t5"],"slug":"slug"}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=3500
    )
    raw = clean_json(response.choices[0].message.content)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find('{')
        end = raw.rfind('}') + 1
        raw = raw[start:end]
        raw = re.sub(r'"content"\s*:\s*"(.*?)"(?=\s*,\s*"tags")',
                     lambda m: '"content":"' + m.group(1).replace('\n',' ').replace('\r','') + '"',
                     raw, flags=re.DOTALL)
        result = json.loads(raw)
    result['_chosen_raw'] = chosen
    return result

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
