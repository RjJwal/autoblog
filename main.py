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
        sa_info,
        scopes=['https://www.googleapis.com/auth/indexing']
    )
    credentials.refresh(Request())
    return credentials.token

def auto_index_url(url):
    try:
        token = get_indexing_token()
        r = requests.post(
            'https://indexing.googleapis.com/v3/urlNotifications:publish',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
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

    try:
        feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in feed.entries[:8]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "bbc_news"})
        print("BBC: added")
    except Exception as e:
        print(f"BBC failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.reuters.com/reuters/topNews')
        for entry in feed.entries[:6]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "reuters"})
        print("Reuters: added")
    except Exception as e:
        print(f"Reuters failed: {e}")

    try:
        feed = feedparser.parse('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en')
        for entry in feed.entries[:12]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "google_news"})
        print("Google News: added")
    except Exception as e:
        print(f"Google News failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.skynews.com/feeds/rss/world.xml')
        for entry in feed.entries[:5]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "sky_news"})
        print("Sky News: added")
    except Exception as e:
        print(f"Sky News failed: {e}")

    try:
        feed = feedparser.parse('https://techcrunch.com/feed/')
        for entry in feed.entries[:6]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "techcrunch"})
        print("TechCrunch: added")
    except Exception as e:
        print(f"TechCrunch failed: {e}")

    try:
        feed = feedparser.parse('https://www.theverge.com/rss/index.xml')
        for entry in feed.entries[:5]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "theverge"})
        print("The Verge: added")
    except Exception as e:
        print(f"The Verge failed: {e}")

    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:6]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title') and not is_blocked(story['title']):
                topics.append({"title": story['title'], "source": "hackernews"})
        print("HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")

    try:
        feed = feedparser.parse('https://www.espn.com/espn/rss/news')
        for entry in feed.entries[:4]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "espn"})
        print("ESPN: added")
    except Exception as e:
        print(f"ESPN failed: {e}")

    try:
        feed = feedparser.parse('https://variety.com/feed/')
        for entry in feed.entries[:4]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "variety"})
        print("Variety: added")
    except Exception as e:
        print(f"Variety failed: {e}")

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

Brainstorm ONE trending topic in "{category_name}" that:
- People are actively searching for RIGHT NOW in 2026
- Has NOT been covered yet
- Could be a new AI tool, startup, product launch, viral trend, sports record, celebrity news
- Has high search volume potential

Reply with ONLY the topic title. Nothing else."""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )
    topic = response.choices[0].message.content.strip()
    print(f"AI brainstormed [{category_name}]: {topic}")
    return topic

def pick_topic_for_category(client, topics, used_topics, existing_titles, category_name, avoid_keywords, today):
    remaining = [t for t in topics if t['title'] not in used_topics and not is_duplicate(t['title'], existing_titles)]

    if not remaining:
        return brainstorm_topic(client, category_name, existing_titles, today), True

    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(remaining)])
    avoid_str = ', '.join(avoid_keywords) if avoid_keywords else 'none'

    prompt = f"""Today is {today}.

Headlines:
{topics_text}

Category: "{category_name}"
Avoid topics about: {avoid_str}

Pick ONE headline that fits "{category_name}" and would get maximum Google searches today.
If NO headline fits this category well, reply with exactly: BRAINSTORM
Otherwise reply with ONLY the exact headline text."""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    chosen = response.choices[0].message.content.strip()

    if chosen == 'BRAINSTORM' or len(chosen) > 200:
        return brainstorm_topic(client, category_name, existing_titles, today), True

    return chosen, False

def write_seo_blog_post(topics, used_topics, existing_titles, category_name, avoid_keywords):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')

    chosen, is_brainstormed = pick_topic_for_category(
        client, topics, used_topics, existing_titles,
        category_name, avoid_keywords, today
    )
    print(f"Writing [{category_name}]: {chosen} {'(brainstormed)' if is_brainstormed else '(from news)'}")

    write_prompt = f"""You are a Pulitzer-level journalist and world-class SEO expert. Today is {today}.

Write a MASTERPIECE 2000-word SEO blog post about:
"{chosen}"

=== STRICT SEO RULES ===

TITLE:
- 55-60 characters exactly
- Primary keyword included naturally
- Use power words: "Explained", "What You Need to Know", "Here's Why", "Breaking", "Everything to Know"

INTRO (first 150 words — MOST IMPORTANT):
- ONE shocking fact or bold statement to open
- Do NOT start with "In a world..." or "Did you know..."
- Use "You" to pull reader in
- Primary keyword within first 100 words
- End intro with curiosity gap

STRUCTURE:
- H2s = EXACT questions people type into Google
- Each section: 200-250 words, one clear idea
- Bold key facts with <strong>
- At least one <ul> list with 4-6 bullet points
- "What Experts Are Saying" section with realistic quotes
- "What Happens Next" section near end

KEYWORDS:
- Primary keyword: 8-12 times naturally
- 4 secondary long-tail keywords: 2-3 times each
- Semantic variations throughout

FAQ (6 Q&As for Google featured snippets):
- Exact questions people Google
- Answers: 40-60 words, direct and complete

EEAT SIGNALS:
- Specific dates, numbers, statistics
- Real organizations and experts by name
- Deep context and cause-effect reasoning

HTML tags only: <h2><p><strong><ul><li>

CRITICAL: Return ONLY single-line valid JSON. Escape ALL quotes in strings. No newlines in values. No markdown. No backslashes except for escaping quotes:

{{"chosen_topic":"topic","title":"55-60 char title","meta_description":"150-155 char description","primary_keyword":"keyword","secondary_keywords":["kw1","kw2","kw3","kw4"],"image_search_query":"3 word image search query","content":"FULL HTML","tags":["t1","t2","t3","t4","t5"],"slug":"url-slug"}}"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": write_prompt}],
        temperature=0.7,
        max_tokens=3000
    )
    raw = clean_json(response.choices[0].message.content)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find('{')
        end = raw.rfind('}') + 1
        raw = raw[start:end]
        raw = re.sub(r'"content"\s*:\s*"(.*?)"(?=\s*,\s*"tags")',
                     lambda m: '"content":"' + m.group(1).replace('\n', ' ').replace('\r', '').replace('\\', '') + '"',
                     raw, flags=re.DOTALL)
        result = json.loads(raw)

    result['_chosen_raw'] = chosen
    return result

def build_final_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    image_query = post.get('image_search_query', post['primary_keyword'])
    img_url, photographer, photo_link = get_unsplash_image(image_query)

    if img_url:
        hero_image = f"""<div style="margin-bottom:24px;">
<img src="{img_url}" alt="{post['title']}" style="width:100%;max-width:100%;border-radius:8px;"/>
<p style="font-size:12px;color:#888;margin-top:4px;">Photo by <a href="{photo_link}" target="_blank">{photographer}</a> on <a href="https://unsplash.com" target="_blank">Unsplash</a></p>
</div>"""
    else:
        hero_image = ""

    faq_entities = [
        {
            "@type": "Question",
            "name": f"What is {post['primary_keyword']}?",
            "acceptedAnswer": {"@type": "Answer", "text": post['meta_description']}
        },
        {
            "@type": "Question",
            "name": f"Why is {post['primary_keyword']} important?",
            "acceptedAnswer": {"@type": "Answer", "text": f"{post['title']} — one of today's most searched topics. {post['meta_description']}"}
        },
        {
            "@type": "Question",
            "name": f"What are the latest updates on {post['primary_keyword']}?",
            "acceptedAnswer": {"@type": "Answer", "text": f"As of {datetime.utcnow().strftime('%B %d, %Y')}, {post['meta_description']}"}
        }
    ]

    faq_schema_str = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_entities
    })

    news_schema_str = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": post['title'],
        "description": post['meta_description'],
        "datePublished": now_iso,
        "dateModified": now_iso,
        "image": img_url or "",
        "keywords": ', '.join(post.get('secondary_keywords', [])),
        "author": {"@type": "Organization", "name": "TrendExplained", "url": "https://trendexplainednow.blogspot.com"},
        "publisher": {"@type": "Organization", "name": "TrendExplained", "url": "https://trendexplainednow.blogspot.com"}
    })

    schema = f"""<script type="application/ld+json">{news_schema_str}</script>
<script type="application/ld+json">{faq_schema_str}</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{post['primary_keyword']}, {', '.join(post.get('secondary_keywords', []))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
<meta property="og:image" content="{img_url or ''}"/>
<meta property="og:type" content="article"/>
<meta name="robots" content="index, follow"/>
"""
    return schema + hero_image + post['content']

def ping_indexnow(url):
    try:
        r = requests.get(
            'https://api.indexnow.org/indexnow',
            params={'url': url, 'key': '5ce0a0281fb341549bbec44bda7c063c'},
            timeout=10
        )
        print(f"IndexNow pinged: {r.status_code}")
    except Exception as e:
        print(f"IndexNow failed: {e}")

def publish_to_blogger(post, final_content):
    token = get_access_token()
    r = requests.post(
        f'https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={'title': post['title'], 'content': final_content, 'labels': post.get('tags', [])},
        timeout=30
    )
    result = r.json()
    if 'url' in result:
        url = result['url']
        print(f"PUBLISHED: {url}")
        ping_indexnow(url)
        auto_index_url(url)
        return url
    raise Exception(f"Failed: {result}")

if __name__ == '__main__':
    print(f"Starting AutoBlog — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    topics = get_trending_topics()
    existing_titles = get_existing_post_titles()

    post_categories = [
        {"name": "World News & Politics", "avoid": []},
        {"name": "Technology, AI & New Companies", "avoid": ["war", "iran", "attack", "military", "shooting", "killed", "dead"]},
        {"name": "Sports, Entertainment or Business Trends", "avoid": ["war", "iran", "attack", "military", "shooting", "killed", "dead", "politics"]},
    ]

    used_topics = []
    posts_published = 0

    for i, cat in enumerate(post_categories):
        print(f"\n--- Writing post {i+1} of 3 [{cat['name']}] ---")
        try:
            post = write_seo_blog_post(
                topics, used_topics, existing_titles,
                cat['name'], cat['avoid']
            )
            used_topics.append(post.get('_chosen_raw', post['chosen_topic']))
            existing_titles.append(post['title'].lower())
            final_content = build_final_content(post)
            publish_to_blogger(post, final_content)
            posts_published += 1
            time.sleep(8)
        except Exception as e:
            print(f"Post {i+1} failed: {e}")
            continue

    print(f"\nDONE! Published {posts_published}/3 posts this run.")
