import os
import json
import time
import re
import requests
import feedparser
from groq import Groq
from datetime import datetime

GROQ_API_KEY         = os.environ['GROQ_API_KEY']
BLOGGER_BLOG_ID      = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID     = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']

BLOCKLIST = [
    'trump indictment', 'pleads not guilty', '34 felony',
    'hush money', 'stormy daniels', 'temporal javascript',
    '9-year journey', 'knitting', 'common lisp'
]

# Categories to rotate through for variety
CATEGORIES = [
    {'name': 'World News', 'sources': ['google_news', 'bbc_news', 'reuters'], 'keywords': ['war', 'iran', 'attack', 'military', 'strike', 'shooting', 'killed', 'dead', 'bomb']},
    {'name': 'Technology', 'sources': ['hackernews', 'google_news'], 'keywords': ['ai', 'tech', 'apple', 'google', 'microsoft', 'openai', 'software', 'app']},
    {'name': 'Economy', 'sources': ['google_news', 'reuters', 'bbc_news'], 'keywords': ['oil', 'price', 'market', 'economy', 'trade', 'inflation', 'stock', 'tariff']},
]

def is_blocked(title):
    t = title.lower()
    return any(b in t for b in BLOCKLIST)

def clean_json(raw):
    # Remove control characters that break JSON parsing
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    raw = raw.strip()
    # Remove invalid control characters
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    return raw

def get_trending_topics():
    topics = []

    try:
        feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in feed.entries[:8]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "bbc_news"})
        print(f"BBC: added")
    except Exception as e:
        print(f"BBC failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.reuters.com/reuters/topNews')
        for entry in feed.entries[:6]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "reuters"})
        print(f"Reuters: added")
    except Exception as e:
        print(f"Reuters failed: {e}")

    try:
        feed = feedparser.parse('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en')
        for entry in feed.entries[:12]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "google_news"})
        print(f"Google News: added")
    except Exception as e:
        print(f"Google News failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.skynews.com/feeds/rss/world.xml')
        for entry in feed.entries[:5]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "sky_news"})
        print(f"Sky News: added")
    except Exception as e:
        print(f"Sky News failed: {e}")

    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:6]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title') and not is_blocked(story['title']):
                topics.append({"title": story['title'], "source": "hackernews"})
        print(f"HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")

    # Entertainment/Sports RSS for variety
    try:
        feed = feedparser.parse('https://www.espn.com/espn/rss/news')
        for entry in feed.entries[:4]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "espn"})
        print(f"ESPN: added")
    except Exception as e:
        print(f"ESPN failed: {e}")

    try:
        feed = feedparser.parse('https://variety.com/feed/')
        for entry in feed.entries[:4]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "variety"})
        print(f"Variety: added")
    except Exception as e:
        print(f"Variety failed: {e}")

    print(f"\n=== FETCHED HEADLINES ===")
    for i, t in enumerate(topics):
        print(f"{i+1}. [{t['source']}] {t['title']}")
    print(f"=== TOTAL: {len(topics)} ===\n")
    return topics

def pick_topic_for_category(client, topics, used_topics, category_name, avoid_keywords):
    today = datetime.utcnow().strftime('%B %d, %Y')
    remaining = [t for t in topics if t['title'] not in used_topics]
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(remaining)])
    avoid_str = ', '.join(avoid_keywords)

    prompt = f"""Today is {today}.

Headlines:
{topics_text}

Pick ONE headline for the category: "{category_name}"
- Avoid headlines about: {avoid_str}
- Pick something that would get maximum Google searches today in this category
- Reply with ONLY the exact headline text from the list. Nothing else."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

def write_seo_blog_post(topics, used_topics, category_name, avoid_keywords):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')

    chosen = pick_topic_for_category(client, topics, used_topics, category_name, avoid_keywords)
    print(f"Chosen [{category_name}]: {chosen}")

    write_prompt = f"""You are a Pulitzer-level journalist and world-class SEO expert. Today is {today}.

Write a MASTERPIECE 2000-word SEO blog post about this story:
"{chosen}"

=== STRICT SEO RULES ===

TITLE:
- 55-60 characters exactly
- Include primary keyword naturally
- Use power words: "Explained", "What You Need to Know", "Here's Why", "Everything You Need to Know", "Breaking"

INTRO (first 150 words — MOST IMPORTANT):
- Open with ONE shocking fact or bold statement
- Do NOT start with "In a world..." or "Did you know..."
- Use "You" to pull reader in immediately
- Primary keyword within first 100 words
- End with curiosity gap — tease what they will learn

STRUCTURE:
- H2s must be EXACT questions people type into Google
- Each section: 200-250 words, one clear idea
- Bold key facts with <strong>
- At least one <ul> list with 4-6 bullet points
- "What Experts Are Saying" section with realistic expert quotes
- "What Happens Next" section near the end

KEYWORDS:
- Primary keyword: used 8-12 times naturally
- 4 secondary long-tail keywords used 2-3 times each
- Semantic variations throughout

FAQ (6 Q&As — targets Google featured snippets):
- Questions must be exactly what people Google
- Answers: 40-60 words, direct and complete

EEAT:
- Specific dates, numbers, statistics
- Real organizations and experts by name
- Deep context and cause-effect reasoning

Use only <h2><p><strong><ul><li> HTML tags.

CRITICAL: Return ONLY a single-line valid JSON. Escape ALL quotes inside strings with backslash. No newlines inside JSON string values. No markdown:

{{"chosen_topic":"headline","title":"55-60 char title","meta_description":"150-155 char description","primary_keyword":"keyword","secondary_keywords":["kw1","kw2","kw3","kw4"],"content":"FULL HTML here with all quotes escaped","tags":["t1","t2","t3","t4","t5"],"slug":"url-slug"}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": write_prompt}],
        temperature=0.7,
        max_tokens=4000
    )
    raw = clean_json(response.choices[0].message.content)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract content between first { and last }
        start = raw.find('{')
        end = raw.rfind('}') + 1
        raw = raw[start:end]
        # Aggressively clean content field
        raw = re.sub(r'"content"\s*:\s*"(.*?)"(?=\s*,\s*"tags")', 
                     lambda m: '"content":"' + m.group(1).replace('\n', ' ').replace('\r', '') + '"',
                     raw, flags=re.DOTALL)
        result = json.loads(raw)

    result['_chosen_raw'] = chosen
    return result

def build_final_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    schema = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":"{post['title']}","description":"{post['meta_description']}","datePublished":"{now_iso}","dateModified":"{now_iso}","keywords":"{', '.join(post.get('secondary_keywords',[]))}","author":{{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"}},"publisher":{{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"}}}}
</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{post['primary_keyword']}, {', '.join(post.get('secondary_keywords', []))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
<meta property="og:type" content="article"/>
<meta name="robots" content="index, follow"/>
"""
    return schema + post['content']

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
        print(f"PUBLISHED: {result['url']}")
        return result['url']
    raise Exception(f"Failed: {result}")

if __name__ == '__main__':
    print(f"Starting AutoBlog — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    topics = get_trending_topics()

    # 3 posts per run, each from a DIFFERENT category
    post_categories = [
        {"name": "World News & Politics", "avoid": []},
        {"name": "Technology & Science", "avoid": ["war", "iran", "attack", "military", "shooting"]},
        {"name": "Business, Sports or Entertainment", "avoid": ["war", "iran", "attack", "military", "shooting", "ai", "tech"]},
    ]

    used_topics = []
    posts_published = 0

    for i, cat in enumerate(post_categories):
        print(f"\n--- Writing post {i+1} of 3 [{cat['name']}] ---")
        try:
            post = write_seo_blog_post(topics, used_topics, cat['name'], cat['avoid'])
            used_topics.append(post.get('_chosen_raw', post['chosen_topic']))
            final_content = build_final_content(post)
            publish_to_blogger(post, final_content)
            posts_published += 1
            time.sleep(8)
        except Exception as e:
            print(f"Post {i+1} failed: {e}")
            continue

    print(f"\nDONE! Published {posts_published}/3 posts this run.")
