import os
import json
import requests
import feedparser
from groq import Groq
from datetime import datetime

GROQ_API_KEY         = os.environ['GROQ_API_KEY']
BLOGGER_BLOG_ID      = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID     = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']

# Topics to skip — stale stories AI keeps picking
BLOCKLIST = ['trump indictment', 'pleads not guilty', '34 felony', 'hush money', 'stormy daniels']

def is_blocked(title):
    t = title.lower()
    return any(b in t for b in BLOCKLIST)

def get_trending_topics():
    topics = []

    try:
        feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in feed.entries[:6]:
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

    # Google News — most current, highest priority
    try:
        feed = feedparser.parse('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en')
        for entry in feed.entries[:10]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "google_news"})
        print(f"Google News: added")
    except Exception as e:
        print(f"Google News failed: {e}")

    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:5]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title') and not is_blocked(story['title']):
                topics.append({"title": story['title'], "source": "hackernews"})
        print(f"HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")

    print(f"\n=== FETCHED HEADLINES ===")
    for i, t in enumerate(topics):
        print(f"{i+1}. [{t['source']}] {t['title']}")
    print(f"=== TOTAL: {len(topics)} ===\n")
    return topics

def write_seo_blog_post(topics):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')
    
    # Prioritize google_news topics
    google_topics = [t for t in topics if t['source'] == 'google_news']
    other_topics = [t for t in topics if t['source'] != 'google_news']
    ordered_topics = google_topics + other_topics
    
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(ordered_topics)])

    pick_prompt = f"""Today is {today}.

Here are TODAY'S real headlines:
{topics_text}

Pick the single headline that would get the most Google searches TODAY.
Prefer topics from [google_news] as they are most current.
Reply with ONLY the exact headline text. Nothing else."""

    pick_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": pick_prompt}],
        temperature=0.1
    )
    chosen = pick_response.choices[0].message.content.strip()
    print(f"AI chose topic: {chosen}")

    write_prompt = f"""You are a world-class SEO journalist. Today is {today}.

Write a complete 1800-word SEO blog post about this breaking news story:
"{chosen}"

STRICT RULES:
- Only write about THIS story
- Title: 55-60 characters with primary keyword
- First 100 words MUST contain the primary keyword
- H2 subheadings must be questions people Google about this topic
- FAQ section at the end with 5 Q&As
- Write like a human journalist — engaging, clear, no fluff
- Strong surprising intro hook
- Strong conclusion

Return ONLY valid JSON, no markdown, no backticks:

{{
  "chosen_topic": "the headline",
  "title": "SEO title",
  "meta_description": "155 char meta description",
  "primary_keyword": "main keyword",
  "secondary_keywords": ["kw1", "kw2", "kw3", "kw4"],
  "content": "FULL HTML using <h2><p><strong><ul><li> tags only",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "slug": "url-slug"
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": write_prompt}],
        temperature=0.7
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'): raw = raw[4:]
    return json.loads(raw.strip())

def build_final_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    schema = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":"{post['title']}","description":"{post['meta_description']}","datePublished":"{now_iso}","dateModified":"{now_iso}","author":{{"@type":"Organization","name":"TrendExplained"}},"publisher":{{"@type":"Organization","name":"TrendExplained"}}}}
</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{', '.join(post.get('secondary_keywords', []))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
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
    post = write_seo_blog_post(topics)
    print(f"Writing about: {post['chosen_topic']}")
    final_content = build_final_content(post)
    publish_to_blogger(post, final_content)
    print("DONE!")
